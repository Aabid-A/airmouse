import importlib
from typing import Any

import numpy as np

from airmouse.camera import OpenCvCamera, frame_to_image
from airmouse.renderer import HEIGHT, WIDTH

cv2: Any = importlib.import_module("cv2")


class FakeCapture:
    """A cv2.VideoCapture stand-in that returns one scripted BGR frame."""

    def __init__(self, frame: Any = None) -> None:
        self.frame = frame
        self.released = False

    def read(self) -> tuple[bool, Any]:
        return (self.frame is not None, self.frame)

    def release(self) -> None:
        self.released = True


def bgr_frame() -> Any:
    """2 rows x 3 columns; the pixel at row 0, column 0 is pure blue in BGR order."""
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    frame[0, 0] = (255, 0, 0)
    frame[1, 2] = (0, 0, 255)  # pure red
    return frame


def camera(frame: Any = None) -> tuple[OpenCvCamera, FakeCapture]:
    capture = FakeCapture(frame)
    return OpenCvCamera(capture, cv2), capture


def test_frames_are_converted_from_bgr_to_rgb() -> None:
    opened, _ = camera(bgr_frame())

    frame = opened.read()
    assert frame is not None

    assert tuple(frame[0, 0]) == (0, 0, 255)  # blue, now in RGB order
    assert frame.shape == (2, 3, 3)


def test_frames_come_out_unrotated_and_unmirrored() -> None:
    opened, _ = camera(bgr_frame())

    frame = opened.read()
    assert frame is not None

    assert tuple(frame[1, 2]) == (255, 0, 0)  # the red pixel is still at row 1, column 2


def test_a_missed_read_gives_none() -> None:
    opened, _ = camera()

    assert opened.read() is None


def test_release_releases_the_capture() -> None:
    opened, capture = camera()

    opened.release()

    assert capture.released


def test_a_frame_becomes_a_preview_sized_image() -> None:
    frame = np.full((480, 640, 3), 200, dtype=np.uint8)

    image = frame_to_image(frame)

    assert (image.width, image.height) == (WIDTH, HEIGHT)
    assert image.get(10, 10) == (200, 200, 200)
