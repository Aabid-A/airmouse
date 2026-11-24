"""The camera, behind a small adapter.

Frames are RGB numpy arrays (height, width, 3, uint8), already mirrored and
rotated as the config says, so everything downstream (the tracker, the
Preview) sees the Hand the way the user does. Frames live in memory only: no
frame is ever written to disk (ADR 0001).

`cv2` comes from the `opencv-contrib-python` that `mediapipe` installs; it is
imported on use so the pure modules and the tests load without it.
"""

import importlib
import sys
from typing import Any, Protocol

from airmouse.config import CameraConfig
from airmouse.renderer import HEIGHT, WIDTH, Image

type Frame = Any  # an RGB numpy array, shape (height, width, 3), dtype uint8

CAMERA_SETTINGS_PATH = "System Settings > Privacy & Security > Camera"
SETTLE_READS = 3  # the first frames of some cameras are dark while exposure settles


class CameraError(Exception):
    """The camera could not be opened."""


class Camera(Protocol):
    def read(self) -> Frame | None:
        """The next frame, or None if the camera gave none this time."""
        ...

    def release(self) -> None: ...


class OpenCvCamera:
    """A cv2 capture device that mirrors and rotates each frame per the config."""

    def __init__(self, capture: Any, config: CameraConfig, cv2: Any) -> None:
        self._capture = capture
        self._config = config
        self._cv2 = cv2

    @classmethod
    def open(cls, config: CameraConfig) -> "OpenCvCamera":
        cv2: Any = importlib.import_module("cv2")
        backend = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY
        capture = cv2.VideoCapture(config.index, backend)
        if not capture.isOpened():
            capture.release()
            raise CameraError(
                f"camera {config.index} did not open. If macOS asked for camera access, "
                f"approve it and run again; otherwise check {CAMERA_SETTINGS_PATH}, "
                "or pick another camera with --camera N."
            )
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        capture.set(cv2.CAP_PROP_FPS, config.fps)
        camera = cls(capture, config, cv2)
        for _ in range(SETTLE_READS):
            capture.read()
        return camera

    def read(self) -> Frame | None:
        ok, bgr = self._capture.read()
        if not ok or bgr is None:
            return None
        cv2 = self._cv2
        frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        rotation = {
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }.get(self._config.rotate)
        if rotation is not None:
            frame = cv2.rotate(frame, rotation)
        if self._config.mirror:
            frame = cv2.flip(frame, 1)
        return frame

    def release(self) -> None:
        self._capture.release()


def frame_to_image(frame: Frame) -> Image:
    """A frame shrunk to the Preview's size. Used only for the opt-in camera image."""
    cv2: Any = importlib.import_module("cv2")
    small = cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
    return Image(WIDTH, HEIGHT, bytearray(small.tobytes()))
