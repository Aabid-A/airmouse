import io
import os
import threading
from pathlib import Path
from typing import Any, NoReturn

import numpy as np
import pytest

from airmouse.app import DEFAULT_DISPLAY, camera_on_line, run_preview
from airmouse.camera import CameraError
from airmouse.config import CameraConfig, Config
from airmouse.controller import State
from airmouse.frame import active_region
from airmouse.gestures import Landmarks
from airmouse.mapping import mapped_region
from airmouse.pipeline import MAX_MISSED_FRAMES, FpsMeter, StageTimes
from airmouse.renderer import (
    BACKGROUND,
    CAMERA_ON_DOT,
    DEBUG_BAR_OFFSET,
    DEBUG_BAR_WIDTH,
    DEBUG_LEFT,
    DEBUG_TOP,
    HEIGHT,
    JOINT_PAUSED,
    REGION_OUTLINE,
    STATUS_TEXT,
    TEXT_ACTIVE,
    WIDTH,
    FrameView,
    Image,
    render_calibrate,
    render_preview,
)
from hands import open_hand, pointing_hand
from lockstep import WAIT_S, ThreadClock, join_worker, lockstep

FRAME_S = 1 / 30


class FakeCamera:
    def __init__(self, frames: int | None = None) -> None:
        self.frames = frames  # None: frames forever
        self.reads = 0
        self.released = False

    def read(self) -> Any:
        self.reads += 1
        if self.frames is not None and self.reads > self.frames:
            return None
        return np.full((480, 640, 3), 123, dtype=np.uint8)

    def release(self) -> None:
        self.released = True


class NoisyCamera(FakeCamera):
    """A camera whose frames are random pixels: anything of them in the Preview would show."""

    def read(self) -> Any:
        flat = super().read()
        if flat is None:
            return None
        return np.random.default_rng(self.reads).integers(0, 256, flat.shape, dtype=np.uint8)


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
    debug_gestures: bool = False,
    config: Config | None = None,
) -> tuple[int, str]:
    out = io.StringIO()
    stepped_camera, stepped_window = lockstep(camera, window)
    status = run_preview(
        config or Config(),
        stepped_camera,
        tracker or FakeTracker(open_hand()),
        stepped_window,
        show_camera_image=show_camera_image,
        calibrate=calibrate,
        debug_gestures=debug_gestures,
        clock=Clock(),
        timer=ThreadClock(FRAME_S),
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


class InterruptedWindow(FakeWindow):
    """Ctrl-C arrives on the main thread, which is the one showing the window."""

    def show(self, image: Image) -> None:
        super().show(image)
        if len(self.images) >= self.quit_after:
            raise KeyboardInterrupt


def test_ctrl_c_quits_cleanly_and_releases_the_camera() -> None:
    camera = FakeCamera()
    tracker, window = FakeTracker(None), InterruptedWindow(frames=3)

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
    assert (last.width, last.height) == (WIDTH, HEIGHT)
    # The red Camera-on dot is drawn, and the Hand's joints are drawn (greys: it starts Paused).
    assert CAMERA_ON_DOT in {last.get(x, y) for x in range(40) for y in range(40)}
    assert any(last.get(x, y) == JOINT_PAUSED for x in range(WIDTH) for y in range(HEIGHT))


def same_images(first: FakeWindow, second: FakeWindow) -> bool:
    return [image.pixels for image in first.images] == [image.pixels for image in second.images]


def test_the_default_preview_never_contains_camera_pixels() -> None:
    flat, noisy = FakeWindow(frames=4), FakeWindow(frames=4)

    run(FakeCamera(), flat)
    run(NoisyCamera(), noisy)

    assert same_images(flat, noisy)  # the frame's pixels change nothing in the Preview


def test_the_preview_fits_the_prepared_frame_and_outlines_the_mapped_region() -> None:
    config = Config(camera=CameraConfig(rotate=90))
    window = FakeWindow(frames=1)

    run(FakeCamera(), window, config=config)

    view = FrameView(480, 640, mapped_region(config, DEFAULT_DISPLAY))
    expected = render_preview(State.PAUSED, landmarks=open_hand(), camera_on=True, view=view)
    assert window.images[0].pixels == expected.pixels


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

    assert tracker.times[:3] == pytest.approx([FRAME_S, 2 * FRAME_S, 3 * FRAME_S])
    # The worker may track a frame more while the Preview quits; every one is the next tick.
    expected = [FRAME_S * (index + 1) for index in range(len(tracker.times))]
    assert tracker.times == pytest.approx(expected)


def test_a_camera_that_stops_delivering_frames_is_an_error_and_is_released() -> None:
    camera, window = FakeCamera(frames=1), FakeWindow(frames=100)

    with pytest.raises(CameraError, match="stopped delivering"):
        run(camera, window)

    assert camera.reads == 1 + MAX_MISSED_FRAMES
    assert camera.released


class SilentCamera(FakeCamera):
    """A camera that gives no frame: each read waits until the test lets it return."""

    def __init__(self) -> None:
        super().__init__(frames=0)
        self.unblocked = threading.Event()

    def read(self) -> Any:
        self.unblocked.wait(WAIT_S)
        return super().read()


def test_q_works_while_the_camera_is_giving_no_frames() -> None:
    camera, window = SilentCamera(), FakeWindow(frames=0)

    status = run_preview(
        Config(), camera, FakeTracker(None), window, out=io.StringIO(), stop_timeout_s=0.01
    )

    assert status == 0
    assert window.images == []
    assert not camera.released  # never released under the read still waiting in it
    camera.unblocked.set()
    join_worker()
    assert camera.released  # the worker released it once the read returned


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

    assert tracker.shapes[0] == (640, 480, 3)
    assert set(tracker.shapes) == {(640, 480, 3)}


def test_calibrate_shows_the_hand_and_the_active_region() -> None:
    window = FakeWindow(frames=2)

    status, output = run(FakeCamera(), window, calibrate=True)

    assert status == 0
    assert len(window.images) == 2
    view = FrameView(640, 480, active_region(640, 480, 0.6))
    expected = render_calibrate(view, landmarks=open_hand(), camera_on=True, fps=None)
    assert expected.pixels == window.images[0].pixels
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
        FrameView(480, 640, active_region(480, 640, 0.6)),
        landmarks=open_hand(),
        camera_on=True,
        fps=None,
    )
    assert window.images[0].pixels == expected.pixels


class RecordingOutput:
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []

    def move_cursor(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    def press(self, x: float, y: float) -> None:
        pass

    def drag_to(self, x: float, y: float) -> None:
        pass

    def release(self, x: float, y: float) -> None:
        pass

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


class MoveCountingWindow(FakeWindow):
    """Notes how many cursor moves there were when the Preview quit."""

    def __init__(self, frames: int, output: RecordingOutput) -> None:
        super().__init__(frames)
        self.output = output
        self.moves_at_quit: int | None = None

    def quit_requested(self) -> bool:
        quit_requested = super().quit_requested()
        if quit_requested and self.moves_at_quit is None:
            self.moves_at_quit = len(self.output.moves)
        return quit_requested


def test_the_cursor_moves_only_once_the_open_palm_has_unpaused() -> None:
    output = RecordingOutput()
    window = MoveCountingWindow(frames=90, output=output)
    camera, stepped_window = lockstep(FakeCamera(), window)

    run_preview(
        Config(),
        camera,
        PalmThenPointing(palm_s=1.5),
        stepped_window,
        output=output,
        display=(1600.0, 1000.0),
        clock=Clock(),
        out=io.StringIO(),
    )

    # Counted up to the 90th frame: the worker may move once more while the Preview quits.
    assert window.moves_at_quit is not None
    assert 0 < window.moves_at_quit < 90 - 40


def test_the_default_preview_has_no_gesture_readout() -> None:
    plain, flagged = FakeWindow(frames=5), FakeWindow(frames=5)

    run(FakeCamera(), plain)
    run(FakeCamera(), flagged, debug_gestures=False)

    assert same_images(plain, flagged)
    # Nothing is drawn under the Camera-on indicator where the readout would start.
    row = range(DEBUG_LEFT, DEBUG_LEFT + DEBUG_BAR_WIDTH)
    assert {plain.images[-1].get(x, DEBUG_TOP + 2) for x in row} == {BACKGROUND}


def test_debug_gestures_draws_the_readout_on_every_frame() -> None:
    plain, debug = FakeWindow(frames=6), FakeWindow(frames=6)

    run(FakeCamera(), plain)
    run(FakeCamera(), debug, debug_gestures=True)

    for before, after in zip(plain.images, debug.images, strict=True):
        assert before.pixels != after.pixels


def test_the_readout_shows_the_open_palm_score_and_the_stage_timings() -> None:
    window = FakeWindow(frames=8)

    run(FakeCamera(), window, debug_gestures=True)

    image = window.images[-1]
    # The open hand counts: the score bar is green (the readout is not a mock-up).
    bar_row = DEBUG_TOP + DEBUG_BAR_OFFSET + 2
    row = range(DEBUG_LEFT, DEBUG_LEFT + DEBUG_BAR_WIDTH)
    assert any(image.get(x, bar_row) == TEXT_ACTIVE for x in row)
    # Five timing rows are drawn at the right.
    rows = {
        y
        for y in range(DEBUG_TOP, DEBUG_TOP + 60)
        for x in range(WIDTH - 100, WIDTH - DEBUG_LEFT)
        if image.get(x, y) == STATUS_TEXT
    }
    assert len(rows) >= 5 * 5


def test_the_readout_never_contains_camera_pixels_without_the_opt_in() -> None:
    flat, noisy = FakeWindow(frames=4), FakeWindow(frames=4)

    run(FakeCamera(), flat, debug_gestures=True)
    run(NoisyCamera(), noisy, debug_gestures=True)

    assert same_images(flat, noisy)


def test_calibrate_ignores_debug_gestures() -> None:
    plain, debug = FakeWindow(frames=3), FakeWindow(frames=3)

    run(FakeCamera(), plain, calibrate=True)
    run(FakeCamera(), debug, calibrate=True, debug_gestures=True)

    assert [image.pixels for image in plain.images] == [image.pixels for image in debug.images]


def test_q_still_quits_and_releases_everything_with_the_readout_on() -> None:
    camera, tracker, window = FakeCamera(), FakeTracker(open_hand()), FakeWindow(frames=2)

    status, output = run(camera, window, tracker, debug_gestures=True)

    assert status == 0
    assert (camera.released, tracker.closed, window.closed) == (True, True, True)
    assert output.splitlines()[-1] == "camera off"


def test_stage_times_are_smoothed_and_keep_their_order() -> None:
    stages = StageTimes()

    stages.record("CAM", 0.030)
    stages.record("TRACK", 0.010)
    stages.record("CAM", 0.050)

    (cam, cam_ms), (track, track_ms) = stages.readings()
    assert (cam, track) == ("CAM", "TRACK")
    assert track_ms == pytest.approx(10.0)
    assert 30.0 < cam_ms < 40.0  # moves a tenth of the way to the new 50 ms
