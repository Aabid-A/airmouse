"""The live Preview: camera in, tracked Hand out, drawn as the Privacy preview.

`run_preview` is the loop, written against small adapters (camera, tracker,
window) so tests drive it with fakes. `run_live_preview` wires the real ones.
There is no cursor output yet: the controller gets a no-op output. In calibrate
mode (`--calibrate`) the loop shows the Hand and the Active region instead and
never builds a controller at all, so it can make no cursor input.
Frames are rotated and mirrored by `prepare_frame` before tracking.
"""

import sys
import time
from collections.abc import Callable
from typing import TextIO

from airmouse.calibrate import render_calibration
from airmouse.camera import Camera, CameraError, OpenCvCamera, frame_to_image
from airmouse.config import CameraConfig, Config
from airmouse.controller import Controller
from airmouse.frame import prepare_frame
from airmouse.renderer import render_preview
from airmouse.tracker import HandLandmarkerTracker, Tracker, TrackerError
from airmouse.window import OpenCvWindow, Window

MAX_MISSED_FRAMES = 100  # this many empty reads in a row means the camera has gone
FPS_SMOOTHING = 0.1  # weight of the newest frame in the FPS readout


class NoOutput:
    """The cursor output does not exist yet; Paused and active still show in the Preview."""

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


def camera_on_line(camera: CameraConfig) -> str:
    return (
        f"camera on: camera {camera.index}, {camera.width}x{camera.height} at {camera.fps} fps. "
        "Press q in the Preview or Ctrl-C to quit."
    )


def run_preview(
    config: Config,
    camera: Camera,
    tracker: Tracker,
    window: Window,
    *,
    show_camera_image: bool = False,
    calibrate: bool = False,
    clock: Callable[[], float] = time.monotonic,
    out: TextIO = sys.stdout,
) -> int:
    """Run until `q` or Ctrl-C, then release everything. Raises CameraError if frames stop."""
    controller = None if calibrate else Controller(config.timing, NoOutput())
    meter = FpsMeter()
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
            raw = camera.read()
            if raw is None:
                missed += 1
                if missed >= MAX_MISSED_FRAMES:
                    raise CameraError("the camera stopped delivering frames")
                if window.quit_requested():
                    break
                continue
            missed = 0
            now = clock()
            frame = prepare_frame(raw, config.camera.rotate, config.camera.mirror)
            landmarks = tracker.track(frame, now)
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
                image = render_preview(
                    controller.state,
                    controller.hold_progress,
                    landmarks=landmarks,
                    camera_on=True,
                    fps=meter.tick(now),
                    camera_image=camera_image,
                    show_camera_image=show_camera_image,
                )
            window.show(image)
            if window.quit_requested():
                break
    except KeyboardInterrupt:
        pass
    finally:
        window.close()
        tracker.close()
        camera.release()
        print("camera off", file=out)
    return 0


def run_live_preview(
    config: Config, *, show_camera_image: bool = False, calibrate: bool = False
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
        )
    except CameraError as error:
        print(f"airmouse: {error}", file=sys.stderr)
        return 1
