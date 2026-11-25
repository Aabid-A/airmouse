import importlib
import sys
from typing import Any

import numpy as np
import pytest

from airmouse.camera import CameraError, OpenCvCamera, frame_to_image
from airmouse.config import CameraConfig

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


def test_a_frame_becomes_an_image_of_its_own_size() -> None:
    frame = np.zeros((640, 480, 3), dtype=np.uint8)  # a prepared frame after a quarter turn
    frame[5, 7] = (1, 2, 3)

    image = frame_to_image(frame)

    assert (image.width, image.height) == (480, 640)
    assert image.get(7, 5) == (1, 2, 3)
    assert image.get(10, 10) == (0, 0, 0)


class FakeVideoCapture(FakeCapture):
    """Records how cv2.VideoCapture was built and which properties were set."""

    def __init__(self, index: int, backend: int, opened: bool) -> None:
        super().__init__()
        self.index = index
        self.backend = backend
        self.opened = opened
        self.props: dict[int, float] = {}

    def isOpened(self) -> bool:
        return self.opened

    def set(self, prop: int, value: float) -> bool:
        self.props[prop] = value
        return True


class FakeCv2:
    """A stand-in for the cv2 module: distinct constants and a recording VideoCapture."""

    CAP_ANY = 0
    CAP_AVFOUNDATION = 1200
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5

    def __init__(self, opened: bool = True) -> None:
        self.opened = opened
        self.captures: list[FakeVideoCapture] = []

    def VideoCapture(self, index: int, backend: int) -> FakeVideoCapture:
        capture = FakeVideoCapture(index, backend, self.opened)
        self.captures.append(capture)
        return capture


def test_open_passes_the_camera_settings_to_cv2(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCv2()
    monkeypatch.setitem(sys.modules, "cv2", fake)

    OpenCvCamera.open(CameraConfig(index=2, width=1280, height=720, fps=60))

    (capture,) = fake.captures
    assert capture.index == 2
    assert capture.props == {
        FakeCv2.CAP_PROP_FRAME_WIDTH: 1280,
        FakeCv2.CAP_PROP_FRAME_HEIGHT: 720,
        FakeCv2.CAP_PROP_FPS: 60,
    }


def test_a_camera_that_does_not_open_raises_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeCv2(opened=False)
    monkeypatch.setitem(sys.modules, "cv2", fake)

    with pytest.raises(CameraError, match=r"camera 3 did not open.*--camera N"):
        OpenCvCamera.open(CameraConfig(index=3))

    (capture,) = fake.captures
    assert capture.released
    assert capture.props == {}
