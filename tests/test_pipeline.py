"""The two threads: the worker's cursor path and the Preview on the main thread.

Deterministic: fakes coordinate with events, never sleeps, and every wait has a
timeout (`WAIT_S`) so a bug fails the test instead of hanging it.
"""

import dataclasses
import gc
import io
import threading
import weakref
from typing import Any

import numpy as np
import pytest

import airmouse.app
from airmouse.app import DEFAULT_DISPLAY, run_live_preview, run_preview
from airmouse.camera import CameraError
from airmouse.config import Config
from airmouse.controller import Controller, State
from airmouse.frame import active_region
from airmouse.gestures import Landmarks, Point
from airmouse.mapping import make_cursor_path, mapped_region
from airmouse.output import OutputError
from airmouse.pipeline import WORKER_NAME, LatestSlot, Snapshot, Worker
from airmouse.renderer import DebugReadout, Image
from airmouse.tracker import TrackerError
from hands import open_hand, pointing_hand
from lockstep import WAIT_S, ThreadClock, lockstep
from test_pinch import AIM, Clock, RecordingOutput, Script, drag_script, hand

FRAME_S = 1 / 30


def worker_thread() -> threading.Thread | None:
    return next((t for t in threading.enumerate() if t.name == WORKER_NAME), None)


def frame() -> Any:
    return np.zeros((480, 640, 3), dtype=np.uint8)


# --- the latest-value slot ---


def test_the_slot_keeps_only_the_latest_value_and_counts_versions() -> None:
    slot = LatestSlot[int]()

    for value in range(1000):
        slot.publish(value)

    assert slot.latest() == (1000, 999)


def test_an_overwritten_value_is_dropped_not_queued() -> None:
    class Value:
        pass

    slot = LatestSlot[Value]()
    first = Value()
    gone = weakref.ref(first)
    slot.publish(first)
    del first

    slot.publish(Value())
    gc.collect()

    assert gone() is None  # nothing holds the old value: there is no backlog


def test_waiting_returns_at_once_when_there_is_something_newer() -> None:
    slot = LatestSlot[str]()
    slot.publish("a")
    slot.publish("b")

    assert slot.wait_for_newer(0, WAIT_S) == (2, "b")


def test_waiting_with_nothing_newer_gives_up_after_the_timeout() -> None:
    slot = LatestSlot[str]()
    slot.publish("a")

    assert slot.wait_for_newer(1, 0.001) == (1, "a")


def test_a_publish_wakes_a_waiting_reader() -> None:
    slot = LatestSlot[str]()
    seen: list[tuple[int, str | None]] = []
    reader = threading.Thread(target=lambda: seen.append(slot.wait_for_newer(0, WAIT_S)))
    reader.start()

    slot.publish("new")
    reader.join(WAIT_S)

    assert seen == [(1, "new")]


def test_closing_the_slot_wakes_a_waiting_reader() -> None:
    slot = LatestSlot[str]()
    seen: list[tuple[int, str | None]] = []
    reader = threading.Thread(target=lambda: seen.append(slot.wait_for_newer(0, WAIT_S)))
    reader.start()

    slot.close()
    reader.join(WAIT_S)

    assert seen == [(0, None)]
    assert slot.closed


# --- the worker, one step at a time on this thread ---


class ListTracker:
    """Gives the same list of landmarks every time (so a test can change it after)."""

    def __init__(self, landmarks: Landmarks | None) -> None:
        self.landmarks = landmarks

    def track(self, frame: Any, time_s: float) -> Landmarks | None:
        return self.landmarks

    def close(self) -> None:
        pass


class FrameCamera:
    def read(self) -> Any:
        return frame()

    def release(self) -> None:
        pass


def make_worker(
    tracker: Any,
    output: RecordingOutput | None,
    *,
    camera: Any = None,
    show_camera_image: bool = False,
) -> tuple[Worker, LatestSlot[Snapshot]]:
    config = Config()
    controller = (
        None
        if output is None
        else Controller(
            config.timing,
            output,
            make_cursor_path(config, DEFAULT_DISPLAY),
            config.open_palm,
            config.pinch,
        )
    )
    slot = LatestSlot[Snapshot]()
    worker = Worker(
        config,
        camera or FrameCamera(),
        tracker,
        slot,
        controller=controller,
        output=output,
        region=mapped_region(config, DEFAULT_DISPLAY),
        show_camera_image=show_camera_image,
        clock=Clock(),
        timer=Clock(),
        out=io.StringIO(),
    )
    return worker, slot


def test_each_step_publishes_a_numbered_snapshot() -> None:
    worker, slot = make_worker(ListTracker(open_hand()), RecordingOutput())

    first = worker.step()
    second = worker.step()

    assert first is not None and second is not None
    assert (first.number, second.number) == (1, 2)
    assert slot.latest() == (2, second)
    assert second.controller is not None
    assert second.controller.state is State.PAUSED
    assert second.fps == pytest.approx(30.0)


def test_the_snapshot_cannot_be_changed_and_does_not_follow_the_tracker() -> None:
    landmarks: list[Point] = list(open_hand())
    worker, _ = make_worker(ListTracker(landmarks), RecordingOutput(), show_camera_image=True)
    snapshot = worker.step()
    assert snapshot is not None and snapshot.controller is not None

    landmarks[0] = (0.0, 0.0)  # the tracker's own list changes after the snapshot

    assert snapshot.landmarks == tuple(open_hand())
    for target, field in ((snapshot, "number"), (snapshot.controller, "no_hand")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(target, field, 5)
    assert snapshot.camera_frame is not None
    with pytest.raises(ValueError, match="read-only"):
        snapshot.camera_frame[0, 0, 0] = 1
    assert isinstance(snapshot.timings, tuple)


def test_nothing_moves_while_paused() -> None:
    output = RecordingOutput()
    worker, _ = make_worker(ListTracker(pointing_hand()), output)

    for _ in range(90):
        worker.step()

    assert output.events == []


def test_calibrate_mode_has_no_controller_and_outlines_the_active_region() -> None:
    worker, _ = make_worker(ListTracker(open_hand()), None)

    snapshot = worker.step()

    assert snapshot is not None
    assert snapshot.controller is None
    assert snapshot.view.region == active_region(640, 480, 0.6)


def test_an_empty_read_publishes_nothing() -> None:
    class EmptyCamera(FrameCamera):
        def read(self) -> Any:
            return None

    worker, slot = make_worker(ListTracker(None), RecordingOutput(), camera=EmptyCamera())

    assert worker.step() is None
    assert slot.latest() == (0, None)


# --- the two threads together ---


class ThreadRecordingOutput(RecordingOutput):
    """Records which thread made each call, and lets a test wait for the Nth move."""

    def __init__(self, *, wait_for_moves: int = 0) -> None:
        super().__init__()
        self.threads: list[threading.Thread] = []
        self.wait_for_moves = wait_for_moves
        self.moved_enough = threading.Event()

    def _record(self, name: str, *point: float) -> None:
        self.threads.append(threading.current_thread())
        super()._record(name, *point)
        if self.kinds().count("move") >= self.wait_for_moves:
            self.moved_enough.set()


class ThreadRecordingTracker(Script):
    def __init__(self, make: Any) -> None:
        super().__init__(make)
        self.threads: set[threading.Thread] = set()

    def track(self, frame: Any, time_s: float) -> Landmarks | None:
        self.threads.add(threading.current_thread())
        return super().track(frame, time_s)


def palm_then_pointing(index: int) -> Landmarks:
    """Unpause (30 frames), then a Pointer that keeps moving, so every frame moves the cursor."""
    return open_hand() if index < 30 else hand(AIM, dx=0.001 * (index % 50))


class BlockingWindow:
    """A Preview stuck in its first `show` until the worker has moved the cursor a lot."""

    def __init__(self, output: ThreadRecordingOutput) -> None:
        self.output = output
        self.images: list[Image] = []
        self.moved_while_blocked = False

    def show(self, image: Image) -> None:
        self.images.append(image)
        if len(self.images) == 1:
            self.moved_while_blocked = self.output.moved_enough.wait(WAIT_S)

    def quit_requested(self) -> bool:
        return bool(self.images)

    def close(self) -> None:
        pass


def test_a_blocked_preview_never_slows_the_cursor_path() -> None:
    output = ThreadRecordingOutput(wait_for_moves=40)
    window = BlockingWindow(output)

    run_preview(
        Config(),
        FrameCamera(),
        Script(palm_then_pointing),
        window,
        output=output,
        clock=Clock(),
        out=io.StringIO(),
    )

    assert window.moved_while_blocked  # 40 moves while the Preview was stuck in one draw
    assert len(window.images) == 1


class StallingCamera:
    """Gives `frames` frames, then blocks in `read` until it is released."""

    def __init__(self, frames: int) -> None:
        self.frames = frames
        self.reads = 0
        self.stalled = threading.Event()
        self.unblocked = threading.Event()
        self.releases = 0

    def read(self) -> Any:
        self.reads += 1
        if self.reads <= self.frames:
            return frame()
        self.stalled.set()
        self.unblocked.wait(WAIT_S)
        return None

    def release(self) -> None:
        self.releases += 1
        self.unblocked.set()


class RecordingWindow:
    """Records the images and which threads call it; quits after `frames` images."""

    def __init__(self, frames: int) -> None:
        self.frames = frames
        self.images: list[Image] = []
        self.threads: set[threading.Thread] = set()
        self.closed = False

    def show(self, image: Image) -> None:
        self.threads.add(threading.current_thread())
        self.images.append(image)

    def quit_requested(self) -> bool:
        self.threads.add(threading.current_thread())
        return len(self.images) >= self.frames

    def close(self) -> None:
        self.threads.add(threading.current_thread())
        self.closed = True


class QuitWhenStalledWindow(RecordingWindow):
    """Keeps checking for `q` while the worker is stalled, then quits (or gets Ctrl-C)."""

    def __init__(self, camera: StallingCamera, *, checks: int = 3, interrupt: bool = False) -> None:
        super().__init__(frames=0)
        self.camera = camera
        self.checks = checks
        self.interrupt = interrupt
        self.checks_while_stalled = 0

    def quit_requested(self) -> bool:
        if not self.camera.stalled.is_set():
            return False
        self.checks_while_stalled += 1
        if self.checks_while_stalled < self.checks:
            return False
        if self.interrupt:
            raise KeyboardInterrupt
        return True


def test_a_stalled_camera_never_freezes_the_preview_and_it_invents_no_state() -> None:
    camera = StallingCamera(frames=1)
    window = QuitWhenStalledWindow(camera, checks=5)

    status = run_preview(
        Config(),
        camera,
        Script(lambda _: open_hand()),
        window,
        clock=Clock(),
        out=io.StringIO(),
        stop_timeout_s=0.01,
    )

    assert status == 0
    assert window.checks_while_stalled == 5  # it kept answering `q` while the worker was stuck
    assert len(window.images) == 1  # only the one state the worker reported
    assert camera.releases == 1
    assert window.closed


@pytest.mark.parametrize("interrupt", [False, True], ids=["q", "ctrl-c"])
def test_quitting_while_the_worker_is_stuck_mid_drag_lifts_the_button_once(
    interrupt: bool,
) -> None:
    output = ThreadRecordingOutput()
    camera = StallingCamera(frames=60)  # dragging by then (see drag_script)
    window = QuitWhenStalledWindow(camera, interrupt=interrupt)
    out = io.StringIO()

    status = run_preview(
        Config(),
        camera,
        Script(drag_script),
        window,
        output=output,
        clock=Clock(),
        out=out,
        stop_timeout_s=0.01,
    )
    worker = worker_thread()
    if worker is not None:
        worker.join(WAIT_S)  # the released camera let the stuck read return

    assert status == 0
    assert "drag" in output.kinds()
    assert output.kinds().count("release_drag") == 1
    assert output.threads[-1] is threading.current_thread()  # lifted from the main thread
    assert not output.down
    assert camera.releases == 1
    assert out.getvalue().splitlines()[-1] == "camera off"


def test_on_a_normal_quit_only_the_worker_touches_the_output_and_the_tracker() -> None:
    output = ThreadRecordingOutput()
    tracker = ThreadRecordingTracker(drag_script)
    window = RecordingWindow(frames=60)
    camera, stepped_window = lockstep(FrameCamera(), window)

    run_preview(
        Config(),
        camera,
        tracker,
        stepped_window,
        output=output,
        clock=Clock(),
        timer=ThreadClock(FRAME_S),
        out=io.StringIO(),
    )

    assert "press" in output.kinds()
    assert output.kinds()[-1] == "release_drag"
    assert {thread.name for thread in output.threads} == {WORKER_NAME}
    assert {thread.name for thread in tracker.threads} == {WORKER_NAME}
    assert window.threads == {threading.current_thread()}  # the worker never touches the window


# --- errors cross from the worker to the main thread ---


class FailingTracker(Script):
    def __init__(self, error: BaseException, at: int) -> None:
        super().__init__(drag_script)
        self.error = error
        self.at = at

    def track(self, frame: Any, time_s: float) -> Landmarks | None:
        if self.frame >= self.at:
            raise self.error
        return super().track(frame, time_s)


class EndlessWindow:
    def show(self, image: Image) -> None:
        pass

    def quit_requested(self) -> bool:
        return False

    def close(self) -> None:
        pass


@pytest.mark.parametrize(
    "error",
    [TrackerError("the Hand model crashed"), RuntimeError("a bug on the worker")],
    ids=["tracker", "unexpected"],
)
def test_a_worker_error_is_raised_on_the_main_thread_after_a_clean_stop(
    error: BaseException,
) -> None:
    output = ThreadRecordingOutput()
    out = io.StringIO()

    with pytest.raises(type(error), match=str(error)):
        run_preview(
            Config(),
            FrameCamera(),
            FailingTracker(error, at=60),  # mid-drag
            EndlessWindow(),
            output=output,
            clock=Clock(),
            out=out,
        )

    assert "press" in output.kinds()
    assert output.kinds()[-1] == "release_drag"
    assert not output.down
    assert out.getvalue().splitlines()[-1] == "camera off"


class FakeQuartzOutput(RecordingOutput):
    display_size = DEFAULT_DISPLAY

    @classmethod
    def open(cls) -> "FakeQuartzOutput":
        return cls()


class UnpluggedCamera(FrameCamera):
    def __init__(self) -> None:
        self.reads = 0

    def read(self) -> Any:
        self.reads += 1
        if self.reads > 3:
            raise CameraError("the camera was unplugged")
        return frame()


class OutputFailingTracker(ListTracker):
    def track(self, frame: Any, time_s: float) -> Landmarks | None:
        raise OutputError("macOS refused to create a mouse event")


@pytest.mark.parametrize(
    ("camera", "tracker", "message"),
    [
        (UnpluggedCamera(), ListTracker(None), "the camera was unplugged"),
        (FrameCamera(), OutputFailingTracker(None), "macOS refused to create a mouse event"),
    ],
    ids=["camera", "output"],
)
def test_the_live_preview_turns_worker_errors_into_the_same_message_and_exit_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    camera: Any,
    tracker: Any,
    message: str,
) -> None:
    monkeypatch.setattr(airmouse.app.HandLandmarkerTracker, "open", lambda: tracker)
    monkeypatch.setattr(airmouse.app.OpenCvCamera, "open", lambda config: camera)
    monkeypatch.setattr(airmouse.app, "QuartzOutput", FakeQuartzOutput)
    monkeypatch.setattr(airmouse.app, "OpenCvWindow", EndlessWindow)

    status = run_live_preview(Config())

    assert status == 1
    assert capsys.readouterr().err == f"airmouse: {message}\n"


# --- the readout ---


def test_the_readout_has_worker_and_window_stages_and_both_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readouts: list[DebugReadout] = []
    render = airmouse.app.render_preview

    def recording_render(*args: Any, debug: DebugReadout | None = None, **kwargs: Any) -> Image:
        assert debug is not None
        readouts.append(debug)
        return render(*args, debug=debug, **kwargs)

    monkeypatch.setattr(airmouse.app, "render_preview", recording_render)
    camera, window = lockstep(FrameCamera(), RecordingWindow(frames=5))

    run_preview(
        Config(),
        camera,
        ListTracker(open_hand()),
        window,
        debug_gestures=True,
        clock=Clock(),
        timer=ThreadClock(FRAME_S),
        out=io.StringIO(),
    )

    last = readouts[4]
    names = [name for name, _ in last.timings]
    assert names == ["CAM", "PREP", "TRACK", "CTRL", "FRAME", "DRAW", "WIN", "TRACK FPS", "UI FPS"]
    rows = dict(last.timings)
    assert rows["TRACK FPS"] == pytest.approx(30.0)  # the tracking rate, from the frame clock
    assert rows["CAM"] == pytest.approx(FRAME_S * 1000)
    assert rows["FRAME"] == pytest.approx(5 * FRAME_S * 1000)  # five timer reads per frame here
    assert rows["UI FPS"] == pytest.approx(1 / (3 * FRAME_S))  # three per drawn image


def test_the_worker_thread_is_a_daemon_so_a_stuck_read_cannot_keep_the_process_alive() -> None:
    camera = StallingCamera(frames=0)
    daemon: list[bool] = []

    class CheckingWindow(QuitWhenStalledWindow):
        def quit_requested(self) -> bool:
            thread = worker_thread()
            daemon.append(thread is not None and thread.daemon)
            return super().quit_requested()

    run_preview(
        Config(),
        camera,
        ListTracker(None),
        CheckingWindow(camera, checks=1),
        out=io.StringIO(),
        stop_timeout_s=0.01,
    )

    assert daemon and all(daemon)
