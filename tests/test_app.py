import io
import os
from pathlib import Path
from typing import Any, NoReturn

import numpy as np
import pytest

from airmouse.app import (
    MAX_MISSED_FRAMES,
    FpsMeter,
    camera_on_line,
    run_preview,
)
from airmouse.camera import CameraError
from airmouse.config import CameraConfig, Config
from airmouse.frame import active_region
from airmouse.gestures import Landmarks
from airmouse.renderer import PALETTE, REGION_OUTLINE, WIDTH, Image, render_calibrate
from hands import open_hand, pointing_hand

FRAME_S = 1 / 30


class FakeCamera:
    def __init__(self, frames: int | None = None, error: BaseException | None = None) -> None:
        self.frames = frames  # None: frames forever
        self.error = error
        self.reads = 0
        self.released = False

    def read(self) -> Any:
        self.reads += 1
        if self.error is not None and self.reads > 2:
            raise self.error
        if self.frames is not None and self.reads > self.frames:
            return None
        return np.full((480, 640, 3), 123, dtype=np.uint8)

    def release(self) -> None:
        self.released = True


class FakeTracker:
    def __init__(self, landmarks: Landmarks | None) -> None:
        self.landmarks = landmarks
        self.times: list[float] = []
        self.shapes: list[tuple[int, ...]] = []
        self.closed = False

    def track(self, frame: Any, time_s: float) -> Landmarks | None:
        self.times.append(time_s)
        self.shapes.append(frame.shape)
        return self.landmarks

    def close(self) -> None:
        self.closed = True


class FakeWindow:
    """Records every shown image and asks to quit after `frames` of them."""

    def __init__(self, frames: int) -> None:
        self.quit_after = frames
        self.images: list[Image] = []
        self.closed = False

    def show(self, image: Image) -> None:
        self.images.append(image)

    def quit_requested(self) -> bool:
        return len(self.images) >= self.quit_after

    def close(self) -> None:
        self.closed = True


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += FRAME_S
        return self.now


def run(
    camera: FakeCamera,
    window: FakeWindow,
    tracker: FakeTracker | None = None,
    *,
    show_camera_image: bool = False,
    calibrate: bool = False,
    config: Config | None = None,
) -> tuple[int, str]:
    out = io.StringIO()
    status = run_preview(
        config or Config(),
        camera,
        tracker or FakeTracker(open_hand()),
        window,
        show_camera_image=show_camera_image,
        calibrate=calibrate,
        clock=Clock(),
        out=out,
    )
    return status, out.getvalue()


def test_q_quits_and_everything_is_released() -> None:
    camera, tracker, window = FakeCamera(), FakeTracker(open_hand()), FakeWindow(frames=3)

    status, _ = run(camera, window, tracker)

    assert status == 0
    assert len(window.images) == 3
    assert camera.released
    assert tracker.closed
    assert window.closed


def test_ctrl_c_quits_cleanly_and_releases_the_camera() -> None:
    camera = FakeCamera(error=KeyboardInterrupt())
    tracker, window = FakeTracker(None), FakeWindow(frames=100)

    status, output = run(camera, window, tracker)

    assert status == 0
    assert camera.released
    assert tracker.closed
    assert window.closed
    assert output.splitlines()[-1] == "camera off"


def test_the_cli_says_camera_on_while_capturing() -> None:
    _, output = run(FakeCamera(), FakeWindow(frames=1))

    first, *_ = output.splitlines()
    assert first.startswith("camera on: camera 0, 640x480 at 30 fps")
    assert "q" in first
    assert "Ctrl-C" in first


def test_the_status_line_follows_the_camera_config() -> None:
    line = camera_on_line(CameraConfig(index=2, width=1280, height=720, fps=60))

    assert line.startswith("camera on: camera 2, 1280x720 at 60 fps")


def test_each_frame_is_drawn_with_the_hand_the_indicator_and_fps() -> None:
    window = FakeWindow(frames=5)

    run(FakeCamera(), window)

    last = window.images[-1]
    assert (last.width, last.height) == (WIDTH, 240)
    # The red Camera-on dot is drawn, and the Hand's joints are drawn.
    assert last.get(14, 17) == (235, 70, 70)
    assert any(last.get(x, y) == (210, 225, 240) for x in range(WIDTH) for y in range(240))


def test_the_default_preview_never_contains_camera_pixels() -> None:
    window = FakeWindow(frames=4)

    run(FakeCamera(), window)

    for image in window.images:
        assert {image.get(x, y) for x in range(0, WIDTH, 3) for y in range(240)} <= PALETTE


def test_the_camera_image_is_shown_only_with_the_opt_in_flag() -> None:
    opted_in, plain = FakeWindow(frames=2), FakeWindow(frames=2)

    _, output = run(FakeCamera(), opted_in, show_camera_image=True)
    run(FakeCamera(), plain)

    assert opted_in.images[-1].get(300, 150) == (123, 123, 123)
    assert plain.images[-1].get(300, 150) not in {(123, 123, 123)}
    assert "--show-camera-image" in output


def test_the_tracker_is_fed_the_clock_time() -> None:
    tracker = FakeTracker(None)

    run(FakeCamera(), FakeWindow(frames=3), tracker)

    assert tracker.times == pytest.approx([FRAME_S, 2 * FRAME_S, 3 * FRAME_S])


def test_a_camera_that_stops_delivering_frames_is_an_error_and_is_released() -> None:
    camera, window = FakeCamera(frames=1), FakeWindow(frames=100)

    with pytest.raises(CameraError, match="stopped delivering"):
        run(camera, window)

    assert camera.reads == 1 + MAX_MISSED_FRAMES
    assert camera.released


def test_q_works_while_the_camera_is_giving_no_frames() -> None:
    camera, window = FakeCamera(frames=0), FakeWindow(frames=0)

    status, _ = run(camera, window)

    assert status == 0
    assert camera.released


def test_no_file_is_written_while_the_preview_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    run(FakeCamera(), FakeWindow(frames=5), show_camera_image=True)

    assert list(tmp_path.iterdir()) == []
    assert os.getcwd() == str(tmp_path)


def test_the_fps_meter_reads_the_frame_rate_and_smooths_it() -> None:
    meter = FpsMeter()

    assert meter.tick(0.0) is None
    assert meter.tick(0.1) == pytest.approx(10.0)
    second = meter.tick(0.15)  # a quick frame nudges, not jumps, the reading
    assert second is not None
    assert 10.0 < second < 20.0


def test_frames_are_rotated_before_the_tracker_sees_them() -> None:
    config = Config(camera=CameraConfig(rotate=90))
    tracker = FakeTracker(open_hand())

    run(FakeCamera(), FakeWindow(frames=1), tracker, config=config)

    assert tracker.shapes == [(640, 480, 3)]


def test_calibrate_shows_the_hand_and_the_active_region() -> None:
    window = FakeWindow(frames=2)

    status, output = run(FakeCamera(), window, calibrate=True)

    assert status == 0
    assert len(window.images) == 2
    assert (
        render_calibrate(
            active_region(640, 480, 0.6), landmarks=open_hand(), camera_on=True, fps=None
        ).pixels
        == window.images[0].pixels
    )
    assert REGION_OUTLINE in {
        window.images[1].get(x, y) for x in range(WIDTH) for y in range(window.images[1].height)
    }
    assert "calibrate mode: no cursor input" in output


def test_calibrate_never_builds_a_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("calibrate mode built a Controller, which is where cursor input comes from")

    monkeypatch.setattr("airmouse.app.Controller", fail)

    status, _ = run(FakeCamera(), FakeWindow(frames=2), calibrate=True)

    assert status == 0


def test_calibrate_follows_the_rotated_frame() -> None:
    config = Config(camera=CameraConfig(rotate=270))
    window = FakeWindow(frames=1)

    run(FakeCamera(), window, calibrate=True, config=config)

    expected = render_calibrate(
        active_region(480, 640, 0.6), landmarks=open_hand(), camera_on=True, fps=None
    )
    assert window.images[0].pixels == expected.pixels


class RecordingOutput:
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []

    def move_cursor(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    def release_drag(self) -> None:
        pass


class PalmThenPointing:
    """An open palm for the first `palm_s` seconds, then a pointing Hand."""

    def __init__(self, palm_s: float) -> None:
        self.palm_s = palm_s
        self.closed = False

    def track(self, frame: Any, time_s: float) -> Landmarks | None:
        return open_hand() if time_s < self.palm_s else pointing_hand()

    def close(self) -> None:
        self.closed = True


def test_the_cursor_moves_only_once_the_open_palm_has_unpaused() -> None:
    output = RecordingOutput()

    run_preview(
        Config(),
        FakeCamera(),
        PalmThenPointing(palm_s=1.5),
        FakeWindow(frames=90),
        output=output,
        display=(1600.0, 1000.0),
        clock=Clock(),
        out=io.StringIO(),
    )

    assert 0 < len(output.moves) < 90 - 40
