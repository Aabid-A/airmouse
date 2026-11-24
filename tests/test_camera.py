import importlib
from typing import Any

import numpy as np
import pytest

from airmouse.camera import OpenCvCamera, frame_to_image
from airmouse.config import CameraConfig
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


def camera(config: CameraConfig, frame: Any = None) -> tuple[OpenCvCamera, FakeCapture]:
    capture = FakeCapture(frame)
    return OpenCvCamera(capture, config, cv2), capture


def test_frames_are_converted_from_bgr_to_rgb() -> None:
    opened, _ = camera(CameraConfig(mirror=False), bgr_frame())

    frame = opened.read()
    assert frame is not None

    assert tuple(frame[0, 0]) == (0, 0, 255)  # blue, now in RGB order
    assert frame.shape == (2, 3, 3)


def test_mirror_flips_the_frame_left_to_right() -> None:
    opened, _ = camera(CameraConfig(mirror=True), bgr_frame())

    frame = opened.read()
    assert frame is not None

    assert tuple(frame[0, 2]) == (0, 0, 255)  # the blue pixel moved from column 0 to 2


@pytest.mark.parametrize(("degrees", "shape"), [(0, (2, 3, 3)), (90, (3, 2, 3)), (180, (2, 3, 3))])
def test_rotate_turns_the_frame(degrees: int, shape: tuple[int, int, int]) -> None:
    opened, _ = camera(CameraConfig(rotate=degrees, mirror=False), bgr_frame())

    frame = opened.read()
    assert frame is not None
    assert frame.shape == shape


def test_rotating_90_degrees_turns_clockwise() -> None:
    opened, _ = camera(CameraConfig(rotate=90, mirror=False), bgr_frame())

    frame = opened.read()
    assert frame is not None

    assert tuple(frame[0, 1]) == (0, 0, 255)  # top-left blue moves to the top-right


def test_a_missed_read_gives_none() -> None:
    opened, _ = camera(CameraConfig())

    assert opened.read() is None


def test_release_releases_the_capture() -> None:
    opened, capture = camera(CameraConfig())

    opened.release()

    assert capture.released


def test_a_frame_becomes_a_preview_sized_image() -> None:
    frame = np.full((480, 640, 3), 200, dtype=np.uint8)

    image = frame_to_image(frame)

    assert (image.width, image.height) == (WIDTH, HEIGHT)
    assert image.get(10, 10) == (200, 200, 200)
