"""The camera, behind a small adapter.

Frames are RGB numpy arrays (height, width, 3, uint8), as the camera gives
them. Rotate and mirror are applied after, by `frame.prepare_frame`. Frames
live in memory only: no frame is ever written to disk (ADR 0001).

`cv2` comes from the `opencv-contrib-python` that `mediapipe` installs; it is
imported on use so the pure modules and the tests load without it.
"""

import importlib
import sys
from typing import Any, Protocol

from airmouse.config import CameraConfig
from airmouse.frame import Frame
from airmouse.renderer import Image

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
    """A cv2 capture device that gives RGB frames, unrotated."""

    def __init__(self, capture: Any, cv2: Any) -> None:
        self._capture = capture
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
        camera = cls(capture, cv2)
        for _ in range(SETTLE_READS):
            capture.read()
        return camera

    def read(self) -> Frame | None:
        ok, bgr = self._capture.read()
        if not ok or bgr is None:
            return None
        return self._cv2.cvtColor(bgr, self._cv2.COLOR_BGR2RGB)

    def release(self) -> None:
        self._capture.release()


def frame_to_image(frame: Frame) -> Image:
    """A prepared frame as an Image at its own size. Used only for the opt-in camera image.

    The renderer fits it into the Preview without stretching it.
    """
    height, width = frame.shape[:2]
    return Image(width, height, bytearray(frame.tobytes()))
