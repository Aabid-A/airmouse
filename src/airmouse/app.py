"""The live Preview: camera in, tracked Hand out, drawn as the Privacy preview.

`run_preview` is the loop, written against small adapters (camera, tracker,
window) so tests drive it with fakes. `run_live_preview` wires the real ones.
The controller gets the real Quartz cursor output on macOS and a no-op output
elsewhere (and in tests). In calibrate mode (`--calibrate`) the loop shows the
Hand and the Active region instead and never builds a controller at all, so it
can make no cursor input. With `--debug-gestures` the Preview also draws the Open
palm score, the wrist speed and per-stage timings (see `StageTimes`).
Frames are rotated and mirrored by `prepare_frame` before tracking.
"""

import sys
import time
from collections.abc import Callable
from typing import TextIO

from airmouse.calibrate import render_calibration
from airmouse.camera import Camera, CameraError, OpenCvCamera, frame_to_image
from airmouse.config import CameraConfig, Config
from airmouse.controller import Controller, Output
from airmouse.frame import prepare_frame
from airmouse.mapping import make_cursor_path
from airmouse.output import OutputError, QuartzOutput
from airmouse.renderer import DebugReadout, render_preview
from airmouse.tracker import HandLandmarkerTracker, Tracker, TrackerError
from airmouse.window import OpenCvWindow, Window

MAX_MISSED_FRAMES = 100  # this many empty reads in a row means the camera has gone
FPS_SMOOTHING = 0.1  # weight of the newest frame in the FPS readout
TIMING_SMOOTHING = 0.1  # weight of the newest frame in each stage timing


# The display size the mapping assumes when there is no real output (a 16:10 laptop screen).
DEFAULT_DISPLAY = (1440.0, 900.0)


class NoOutput:
    """No cursor input at all: Paused and active still show in the Preview."""

    def move_cursor(self, x: float, y: float) -> None:
        pass

    def press(self, x: float, y: float) -> None:
        pass

    def drag_to(self, x: float, y: float) -> None:
        pass

    def release(self, x: float, y: float) -> None:
        pass

    def release_drag(self) -> None:
        pass


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


def camera_on_line(camera: CameraConfig) -> str:
    return (
        f"camera on: camera {camera.index}, {camera.width}x{camera.height} at {camera.fps} fps. "
        "Press q in the Preview or Ctrl-C to quit."
    )


def _release_drag(controller: Controller, out: TextIO) -> None:
    """On the way out, never leave the mouse button down. Says so if it cannot be lifted."""
    try:
        controller.release_drag()
    except OutputError as error:
        print(f"airmouse: could not release the mouse button: {error}", file=out)


def run_preview(
    config: Config,
    camera: Camera,
    tracker: Tracker,
    window: Window,
    *,
    show_camera_image: bool = False,
    calibrate: bool = False,
    debug_gestures: bool = False,
    output: Output | None = None,
    display: tuple[float, float] = DEFAULT_DISPLAY,
    clock: Callable[[], float] = time.monotonic,
    timer: Callable[[], float] = time.perf_counter,
    out: TextIO = sys.stdout,
) -> int:
    """Run until `q` or Ctrl-C, then release everything. Raises CameraError if frames stop.

    `output` takes cursor moves, clicks and drags (default: none); `display` is its size in pixels.
    `debug_gestures` draws the gesture readout and stage timings (`timer` measures them).
    """
    controller = (
        None
        if calibrate
        else Controller(
            config.timing,
            output or NoOutput(),
            make_cursor_path(config, display),
            config.open_palm,
            config.pinch,
        )
    )
    meter = FpsMeter()
    stages = StageTimes()
    missed = 0
    print(camera_on_line(config.camera), file=out)
    if calibrate:
        print(
            "calibrate mode: no cursor input. Adjust rotate and mirror until the "
            "skeleton moves as your hand does.",
            file=out,
        )
    if show_camera_image:
        print("warning: the Preview shows the camera image (--show-camera-image).", file=out)
    try:
        while True:
            started = timer()
            raw = camera.read()
            read_s = timer() - started
            if raw is None:
                missed += 1
                if missed >= MAX_MISSED_FRAMES:
                    raise CameraError("the camera stopped delivering frames")
                if window.quit_requested():
                    break
                continue
            missed = 0
            now = clock()
            started = timer()
            frame = prepare_frame(raw, config.camera.rotate, config.camera.mirror)
            prepared = timer()
            landmarks = tracker.track(frame, now)
            tracked = timer()
            camera_image = frame_to_image(frame) if show_camera_image else None
            if controller is None:
                image = render_calibration(
                    config,
                    frame,
                    landmarks,
                    fps=meter.tick(now),
                    camera_image=camera_image,
                    show_camera_image=show_camera_image,
                )
            else:
                controller.update(now, landmarks)
                debug = (
                    DebugReadout(controller.reading, stages.readings()) if debug_gestures else None
                )
                image = render_preview(
                    controller.state,
                    controller.hold_progress,
                    landmarks=landmarks,
                    camera_on=True,
                    fps=meter.tick(now),
                    camera_image=camera_image,
                    show_camera_image=show_camera_image,
                    debug=debug,
                    no_hand=controller.no_hand,
                )
            drawn = timer()
            window.show(image)
            quit_requested = window.quit_requested()
            if debug_gestures:
                shown = timer()
                stages.record("CAM", read_s)
                stages.record("PREP", prepared - started)
                stages.record("TRACK", tracked - prepared)
                stages.record("DRAW", drawn - tracked)
                stages.record("WIN", shown - drawn)
            if quit_requested:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if controller is not None:
            _release_drag(controller, out)
        window.close()
        tracker.close()
        camera.release()
        print("camera off", file=out)
    return 0


def run_live_preview(
    config: Config,
    *,
    show_camera_image: bool = False,
    calibrate: bool = False,
    debug_gestures: bool = False,
) -> int:
    """The real camera, Hand tracker and window. Returns the exit status."""
    try:
        tracker = HandLandmarkerTracker.open()
    except TrackerError as error:
        print(f"airmouse: {error}", file=sys.stderr)
        return 1
    try:
        camera = OpenCvCamera.open(config.camera)
    except CameraError as error:
        tracker.close()
        print(f"airmouse: {error}", file=sys.stderr)
        return 1
    try:
        output = QuartzOutput.open() if sys.platform == "darwin" and not calibrate else None
    except OutputError as error:
        camera.release()
        tracker.close()
        print(f"airmouse: {error}", file=sys.stderr)
        return 1
    try:
        window = OpenCvWindow()
    except Exception:
        camera.release()
        tracker.close()
        raise
    try:
        return run_preview(
            config,
            camera,
            tracker,
            window,
            show_camera_image=show_camera_image,
            calibrate=calibrate,
            debug_gestures=debug_gestures,
            output=output,
            display=output.display_size if output else DEFAULT_DISPLAY,
        )
    except (CameraError, OutputError) as error:
        print(f"airmouse: {error}", file=sys.stderr)
        return 1
