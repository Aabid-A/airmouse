"""The cursor path on its own thread, and the latest-value slot it publishes into.

The `Worker` owns the camera read, frame preparation, the Hand tracker, the
Controller and, through the Controller, the cursor output. Each tracked frame
ends in an immutable `Snapshot` that it publishes into a `LatestSlot`: a single
value that each publish overwrites, so there is no queue and no backlog. The
Preview (on the main thread, see `app.run_preview`) draws whatever is latest and
never holds the worker up; the worker never waits for the Preview.

Only the worker thread touches the Controller, the tracker and the camera; it
also closes the tracker and releases the camera itself once its loop has ended,
so neither is ever closed under a call still running on it. The cursor output
reaches the Controller through a `ShutdownOutput`. The one exception to "only the
worker touches the output" is `Worker.stop`: if the worker does not stop in time
(stuck in a camera read, the tracker or the output), the main thread closes the
`ShutdownOutput`, which lifts a held button once and then ignores every later
call, so a worker that wakes up afterwards can never press the button again.

The worker is a daemon thread only so that a camera read stuck in native code
can never keep the process alive after the main thread has finished shutting
down. It is always stopped explicitly (`stop`, which waits with a timeout). A
worker that never comes back leaves the camera and tracker to the process exit.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO

from airmouse.calibrate import region_for
from airmouse.camera import Camera, CameraError
from airmouse.config import Config
from airmouse.controller import Controller, Output, PalmReading, Phase, State
from airmouse.frame import Frame, Region, prepare_frame
from airmouse.gestures import Point
from airmouse.output import OutputError
from airmouse.renderer import FrameView
from airmouse.tracker import Tracker

MAX_MISSED_FRAMES = 100  # this many empty reads in a row means the camera has gone
FPS_SMOOTHING = 0.1  # weight of the newest frame in the FPS readout
TIMING_SMOOTHING = 0.1  # weight of the newest frame in each stage timing
WORKER_NAME = "airmouse-worker"


class FpsMeter:
    """A smoothed frames-per-second reading, so the number does not flicker."""

    def __init__(self) -> None:
        self._last: float | None = None
        self._fps: float | None = None

    def tick(self, now: float) -> float | None:
        last, self._last = self._last, now
        if last is None or now <= last:
            return self._fps
        instant = 1 / (now - last)
        self._fps = (
            instant if self._fps is None else self._fps + FPS_SMOOTHING * (instant - self._fps)
        )
        return self._fps


class StageTimes:
    """Smoothed milliseconds each stage of the loop takes, in the order first recorded.

    CAM is the wait for the camera's next frame, so it is long whenever the camera
    delivers slowly. The other stages are real work.
    """

    def __init__(self) -> None:
        self._ms: dict[str, float] = {}

    def record(self, name: str, seconds: float) -> None:
        milliseconds = seconds * 1000
        old = self._ms.get(name)
        self._ms[name] = (
            milliseconds if old is None else old + TIMING_SMOOTHING * (milliseconds - old)
        )

    def readings(self) -> tuple[tuple[str, float], ...]:
        return tuple(self._ms.items())


class ShutdownOutput:
    """The cursor output as the Controller sees it, closed for good on the way out.

    Every call goes through one lock. `close` lifts a held button exactly once,
    from whichever thread closes first, and every call after it is ignored, so a
    press that arrives after shutdown never reaches the Mac. If `close` cannot get
    the lock in time (the worker is inside an output call), it leaves a flag, and
    the worker lifts the button as soon as that call returns.
    """

    def __init__(self, output: Output, out: TextIO) -> None:
        self._output = output
        self._out = out
        self._lock = threading.Lock()
        self._closing = threading.Event()
        self._closed = False

    def move_cursor(self, x: float, y: float) -> None:
        self._forward(lambda: self._output.move_cursor(x, y))

    def press(self, x: float, y: float) -> None:
        self._forward(lambda: self._output.press(x, y))

    def drag_to(self, x: float, y: float) -> None:
        self._forward(lambda: self._output.drag_to(x, y))

    def release(self, x: float, y: float) -> None:
        self._forward(lambda: self._output.release(x, y))

    def release_drag(self) -> None:
        self._forward(self._output.release_drag)

    def close(self, timeout: float = -1) -> None:
        """Lift a held button once and ignore everything after. `timeout` < 0 waits as long
        as it takes; otherwise, if the lock is busy, the call holding it lifts the button."""
        self._closing.set()
        if not self._lock.acquire(timeout=timeout):
            return
        try:
            self._close_locked()
        finally:
            self._lock.release()

    def _forward(self, call: Callable[[], None]) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                call()
            finally:
                if self._closing.is_set():
                    self._close_locked()

    def _close_locked(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._output.release_drag()
        except OutputError as error:
            print(f"airmouse: could not release the mouse button: {error}", file=self._out)


class LatestSlot[T]:
    """The latest value only, with a version that goes up by one on each publish.

    Publishing overwrites: a value nobody read is dropped, never queued. The lock
    is held only to swap the reference and bump the version, so a publisher never
    waits for a reader.
    """

    def __init__(self) -> None:
        self._changed = threading.Condition()
        self._value: T | None = None
        self._version = 0
        self._closed = False

    def publish(self, value: T) -> None:
        with self._changed:
            self._value = value
            self._version += 1
            self._changed.notify_all()

    def close(self) -> None:
        """No more values will come. Wakes anyone waiting."""
        with self._changed:
            self._closed = True
            self._changed.notify_all()

    @property
    def closed(self) -> bool:
        return self._closed

    def latest(self) -> tuple[int, T | None]:
        with self._changed:
            return self._version, self._value

    def wait_for_newer(self, version: int, timeout: float) -> tuple[int, T | None]:
        """The latest (version, value) once it is newer than `version`, or after `timeout`
        seconds, or once the slot is closed, whichever comes first."""
        with self._changed:
            self._changed.wait_for(lambda: self._version > version or self._closed, timeout)
            return self._version, self._value


@dataclass(frozen=True)
class ControllerStatus:
    """What the Preview shows of the Controller, copied on the worker thread."""

    state: State
    phase: Phase
    hold_progress: float
    no_hand: bool
    reading: PalmReading

    @classmethod
    def of(cls, controller: Controller) -> "ControllerStatus":
        return cls(
            controller.state,
            controller.phase,
            controller.hold_progress,
            controller.no_hand,
            controller.reading,
        )


@dataclass(frozen=True, eq=False)
class Snapshot:
    """The worker's latest state, everything the Preview needs to draw one frame.

    Immutable: tuples, frozen dataclasses and a read-only frame, so the Preview
    cannot change what the worker sees. `controller` is None in calibrate mode.
    `camera_frame` is the prepared frame, kept only with `--show-camera-image`.
    """

    number: int  # tracked frames so far, 1 for the first
    view: FrameView
    landmarks: tuple[Point, ...] | None
    fps: float | None  # the tracking rate
    controller: ControllerStatus | None
    timings: tuple[tuple[str, float], ...]  # worker stages in ms, and FRAME (camera interval)
    camera_frame: Frame | None = None


def _read_only_copy(frame: Frame) -> Frame:
    copy = frame.copy()
    copy.flags.writeable = False
    return copy


class Worker:
    """Runs the cursor path on its own thread and publishes a Snapshot per tracked frame.

    `step` is one trip round the loop, run on the calling thread; the thread runs
    `step` until `stop`. Any exception ends the thread and is kept in `error` for
    the main thread to re-raise. On its way out the worker lifts a held button.
    """

    def __init__(
        self,
        config: Config,
        camera: Camera,
        tracker: Tracker,
        slot: LatestSlot[Snapshot],
        *,
        controller: Controller | None,
        output: ShutdownOutput | None,
        region: Region,
        show_camera_image: bool,
        clock: Callable[[], float],
        timer: Callable[[], float],
    ) -> None:
        self._config = config
        self._camera = camera
        self._tracker = tracker
        self._slot = slot
        self._controller = controller
        self._output = output
        self._region = region  # the mapped region the Preview outlines
        self._show_camera_image = show_camera_image
        self._clock = clock
        self._timer = timer
        self._meter = FpsMeter()
        self._stages = StageTimes()
        self._missed = 0
        self._number = 0
        self._last_delivery: float | None = None
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name=WORKER_NAME, daemon=True)
        self.error: BaseException | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float) -> bool:
        """Ask the worker to stop and wait up to `timeout` seconds. True if it stopped.

        If it is still running (stuck in a camera read, the tracker or the output),
        close the output from this thread: a held button is lifted and nothing
        reaches the Mac after. The worker still closes the tracker and the camera
        itself if it ever comes back.
        """
        self._stopping.set()
        self._thread.join(timeout)
        if not self._thread.is_alive():
            return True
        if self._output is not None:
            self._output.close(timeout)
        return False

    def step(self) -> Snapshot | None:
        """One trip: read, prepare, track, update the Controller, publish. None if no frame."""
        timer = self._timer
        started = timer()
        raw = self._camera.read()
        delivered = timer()
        if self._stopping.is_set():
            return None  # quitting: the tracker may already be closed
        if raw is None:
            self._missed += 1
            if self._missed >= MAX_MISSED_FRAMES:
                raise CameraError("the camera stopped delivering frames")
            return None
        self._missed = 0
        now = self._clock()
        frame = prepare_frame(raw, self._config.camera.rotate, self._config.camera.mirror)
        prepared = timer()
        landmarks = self._tracker.track(frame, now)
        tracked = timer()
        status = None
        if self._controller is not None:
            self._controller.update(now, landmarks)
            status = ControllerStatus.of(self._controller)
        updated = timer()
        self._record(started, delivered, prepared, tracked, updated)
        self._number += 1
        snapshot = Snapshot(
            number=self._number,
            view=self._view(frame),
            landmarks=None if landmarks is None else tuple((x, y) for x, y in landmarks),
            fps=self._meter.tick(now),
            controller=status,
            timings=self._stages.readings(),
            camera_frame=_read_only_copy(frame) if self._show_camera_image else None,
        )
        self._slot.publish(snapshot)
        return snapshot

    def _view(self, frame: Frame) -> FrameView:
        height, width = frame.shape[:2]
        if self._controller is None:  # calibrate mode outlines the Active region
            return FrameView(width, height, region_for(self._config, frame))
        return FrameView(width, height, self._region)

    def _record(
        self, started: float, delivered: float, prepared: float, tracked: float, updated: float
    ) -> None:
        stages = self._stages
        stages.record("CAM", delivered - started)
        stages.record("PREP", prepared - delivered)
        stages.record("TRACK", tracked - prepared)
        if self._controller is not None:
            stages.record("CTRL", updated - tracked)
        if self._last_delivery is not None:
            stages.record("FRAME", delivered - self._last_delivery)  # the camera's own interval
        self._last_delivery = delivered

    def _run(self) -> None:
        try:
            while not self._stopping.is_set():
                self.step()
        except BaseException as error:  # kept for the main thread to re-raise
            self.error = error
        finally:
            try:
                self._shut_down()
            except BaseException as error:
                self.error = self.error or error
            self._slot.close()

    def _shut_down(self) -> None:
        """On this thread, once the loop has ended: lift the button, close the tracker, camera."""
        try:
            if self._output is not None:
                self._output.close()
        finally:
            try:
                self._tracker.close()
            finally:
                self._camera.release()
