import dataclasses
from collections.abc import Callable
from pathlib import Path

import pytest

from airmouse.config import OpenPalmConfig, TimingConfig
from airmouse.controller import Controller, State
from airmouse.gestures import Landmarks, Point, is_open_palm
from airmouse.renderer import (
    BACKGROUND,
    RING_CENTRE,
    RING_FILLED,
    RING_INNER,
    render_preview,
)
from anatomy import synthetic_hand
from png import decode_png

FRAME_S = 1 / 30
SNAPSHOTS = Path(__file__).parent / "snapshots"


class FakeOutput:
    def __init__(self) -> None:
        self.commands: list[str] = []
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
        self.commands.append("release_drag")


def hand(*, palm: bool, dx: float = 0.0) -> Landmarks:
    """A synthetic Hand, hand size 0.2, shifted sideways by `dx`."""
    points: list[Point] = [(0.5, 0.7)] * 21
    points[0] = (0.5, 0.8)  # wrist
    points[9] = (0.5, 0.6)  # middle MCP
    points[5] = (0.45, 0.62)  # index MCP
    if palm:
        points[4] = (0.28, 0.62)
        points[8], points[12], points[16], points[20] = (
            (0.40, 0.40),
            (0.50, 0.36),
            (0.60, 0.40),
            (0.68, 0.48),
        )
    else:  # a fist
        points[4] = (0.47, 0.64)
        points[8], points[12], points[16], points[20] = (
            (0.45, 0.66),
            (0.50, 0.65),
            (0.55, 0.66),
            (0.58, 0.68),
        )
    return [(x + dx, y) for x, y in points]


class Rig:
    """Feeds frames at 30 fps and keeps the clock."""

    def __init__(self, open_palm: OpenPalmConfig | None = None) -> None:
        self.output = FakeOutput()
        self.controller = Controller(TimingConfig(), self.output, open_palm=open_palm)
        self.time = 0.0

    def feed(self, seconds: float, landmarks: Landmarks | None, *, sway: float = 0.0) -> None:
        """Hold a pose for `seconds`; `sway` shifts the Hand sideways each frame."""
        frames = round(seconds / FRAME_S)
        for index in range(frames):
            shifted = None if landmarks is None else _shift(landmarks, sway * index)
            self.controller.update(self.time, shifted)
            self.time += FRAME_S

    def unpause(self) -> None:
        self.feed(1.0, hand(palm=True))

    def feed_frames(self, seconds: float, make: Callable[[int], Landmarks | None]) -> None:
        """Like `feed`, but `make(frame)` builds each frame (jitter, drift, a changing pose)."""
        for index in range(round(seconds / FRAME_S)):
            self.controller.update(self.time, make(index))
            self.time += FRAME_S


def _shift(landmarks: Landmarks, dx: float) -> Landmarks:
    return [(x + dx, y) for x, y in landmarks]


def test_hand_fixtures_are_what_they_say() -> None:
    assert is_open_palm(hand(palm=True))
    assert not is_open_palm(hand(palm=False))


def test_starts_paused_with_an_empty_hold_ring() -> None:
    rig = Rig()

    assert rig.controller.state is State.PAUSED
    assert rig.controller.hold_progress == 0.0


def test_a_steady_open_palm_held_unpauses_after_the_hold_time() -> None:
    rig = Rig()

    rig.feed(0.7, hand(palm=True))
    assert rig.controller.state is State.PAUSED
    assert 0.8 < rig.controller.hold_progress < 1.0

    rig.feed(0.2, hand(palm=True))
    assert rig.controller.state is State.ACTIVE
    assert rig.controller.hold_progress == 0.0


def test_the_hold_ring_fills_while_the_palm_is_held_and_empties_when_it_drops() -> None:
    rig = Rig()

    rig.feed(0.4, hand(palm=True))
    assert 0.4 < rig.controller.hold_progress < 0.6

    rig.feed(FRAME_S, hand(palm=False))
    assert rig.controller.hold_progress == 0.0


def test_an_unsteady_open_palm_does_not_unpause() -> None:
    rig = Rig()

    rig.feed(2.0, hand(palm=True), sway=0.02)  # 0.6 per second, 3 hand sizes per second

    assert rig.controller.state is State.PAUSED
    assert rig.controller.hold_progress < 0.2


def test_the_unpause_hold_time_comes_from_config() -> None:
    output = FakeOutput()
    controller = Controller(TimingConfig(unpause_hold_s=0.3), output)

    for frame in range(12):
        controller.update(frame * FRAME_S, hand(palm=True))

    assert controller.state is State.ACTIVE


def test_one_frame_of_open_palm_does_not_pause() -> None:
    rig = Rig()
    rig.unpause()
    rig.feed(0.3, hand(palm=False))

    rig.feed(FRAME_S, hand(palm=True))
    rig.feed(0.3, hand(palm=False))

    assert rig.controller.state is State.ACTIVE
    assert rig.output.commands == []


def test_an_open_palm_held_past_the_debounce_pauses() -> None:
    rig = Rig()
    rig.unpause()
    rig.feed(0.3, hand(palm=False))

    rig.feed(0.1, hand(palm=True))
    assert rig.controller.state is State.ACTIVE

    rig.feed(0.1, hand(palm=True))
    assert rig.controller.state is State.PAUSED


def test_pausing_releases_any_drag() -> None:
    rig = Rig()
    rig.unpause()
    rig.feed(0.3, hand(palm=False))

    rig.feed(0.3, hand(palm=True))

    assert rig.output.commands == ["release_drag"]


def test_the_open_palm_that_unpaused_cannot_pause_until_the_hand_leaves_the_pose() -> None:
    rig = Rig()
    rig.unpause()

    rig.feed(2.0, hand(palm=True))  # the same palm, still up
    assert rig.controller.state is State.ACTIVE
    assert rig.output.commands == []

    rig.feed(FRAME_S, hand(palm=False))  # the Hand leaves the pose
    rig.feed(0.3, hand(palm=True))
    assert rig.controller.state is State.PAUSED


def test_losing_the_hand_also_clears_the_latch() -> None:
    rig = Rig()
    rig.unpause()

    rig.feed(FRAME_S, None)
    rig.feed(0.3, hand(palm=True))

    assert rig.controller.state is State.PAUSED


@pytest.mark.parametrize(
    ("name", "state", "progress"),
    [("paused", State.PAUSED, 0.0), ("charging", State.PAUSED, 0.6), ("active", State.ACTIVE, 0.0)],
)
def test_preview_snapshots(name: str, state: State, progress: float) -> None:
    expected = decode_png((SNAPSHOTS / f"{name}.png").read_bytes())

    assert render_preview(state, progress).pixels == expected.pixels


def test_the_hold_ring_fills_clockwise_from_the_top() -> None:
    cx, cy = RING_CENTRE
    middle = RING_INNER + 5
    image = render_preview(State.PAUSED, 0.5)

    assert image.get(cx, cy - middle) == RING_FILLED  # top
    assert image.get(cx + middle, cy) == RING_FILLED  # right
    assert image.get(cx - middle, cy) != RING_FILLED  # left, not yet
    assert image.get(cx, cy) == BACKGROUND


def test_the_preview_is_only_background_ring_and_label() -> None:
    image = render_preview(State.PAUSED, 0.5)
    colours = {image.get(x, y) for x in range(0, 320, 3) for y in range(240)}

    assert len(colours) <= 4


HAND_SIZE = 0.3  # wrist to middle finger base in `real` hands, in frame heights


# A Hand as a camera sees it: fingers upright and together, small landmark jitter.
def real(pose: str, frame: int = 0, *, dx: float = 0.0, pitch: float = 0.0) -> Landmarks:
    return synthetic_hand(pose, pitch=pitch, jitter=0.003, seed=frame, centre=(0.5 + dx, 0.75))


def test_a_close_fingered_open_hand_unpauses_and_then_pauses() -> None:
    rig = Rig()

    rig.feed_frames(1.0, lambda frame: real("open together", frame))
    assert rig.controller.state is State.ACTIVE

    rig.feed_frames(0.3, lambda frame: real("pointing", frame))
    rig.feed_frames(0.3, lambda frame: real("open together", frame))
    assert rig.controller.state is State.PAUSED
    assert rig.output.commands == ["release_drag"]


@pytest.mark.parametrize("pose", ["open together", "open relaxed curl", "open thumb tucked"])
def test_the_hold_ring_fills_for_a_tilted_open_hand(pose: str) -> None:
    rig = Rig()

    rig.feed_frames(0.4, lambda frame: real(pose, frame, pitch=20.0))
    assert 0.4 < rig.controller.hold_progress < 0.6

    rig.feed_frames(0.5, lambda frame: real(pose, frame, pitch=20.0))
    assert rig.controller.state is State.ACTIVE


def test_a_hand_that_drifts_slowly_and_jitters_still_unpauses() -> None:
    rig = Rig()
    drift_per_frame = 0.3 * HAND_SIZE * FRAME_S  # 0.3 hand sizes per second

    rig.feed_frames(1.2, lambda frame: real("open together", frame, dx=drift_per_frame * frame))

    assert rig.controller.state is State.ACTIVE


def test_a_waving_open_hand_does_not_unpause() -> None:
    rig = Rig()
    sweep = 5.0 * HAND_SIZE * FRAME_S  # 5 hand sizes per second

    rig.feed_frames(2.0, lambda frame: real("open together", frame, dx=sweep * frame))

    assert rig.controller.state is State.PAUSED


@pytest.mark.parametrize("pose", ["pointing", "pointing relaxed", "fist"])
def test_a_pointing_hand_or_a_fist_never_unpauses(pose: str) -> None:
    rig = Rig()

    rig.feed_frames(3.0, lambda frame: real(pose, frame))

    assert rig.controller.state is State.PAUSED
    assert rig.controller.hold_progress == 0.0
    assert not rig.controller.reading.counts


@pytest.mark.parametrize("pose", ["pointing", "pointing relaxed", "fist"])
def test_a_pointing_hand_or_a_fist_never_pauses(pose: str) -> None:
    rig = Rig()
    rig.unpause()
    rig.feed(FRAME_S, None)

    rig.feed_frames(3.0, lambda frame: real(pose, frame))

    assert rig.controller.state is State.ACTIVE
    assert rig.output.commands == []


def test_a_pinch_never_pauses_even_with_the_other_fingers_open() -> None:
    rig = Rig()
    rig.unpause()
    rig.feed(FRAME_S, None)

    rig.feed_frames(2.0, lambda frame: real("pinch others open", frame))

    assert rig.controller.state is State.ACTIVE


def test_one_misread_frame_of_a_close_fingered_open_hand_does_not_pause() -> None:
    rig = Rig()
    rig.feed_frames(1.0, lambda frame: real("open together", frame))
    rig.feed_frames(0.3, lambda frame: real("pointing", frame))

    rig.feed_frames(FRAME_S, lambda frame: real("open together", frame))
    rig.feed_frames(0.3, lambda frame: real("pointing", frame))

    assert rig.controller.state is State.ACTIVE
    assert rig.output.commands == []


def test_the_unpausing_palm_cannot_pause_until_the_hand_leaves_the_pose() -> None:
    rig = Rig()
    rig.feed_frames(1.0, lambda frame: real("open together", frame))

    rig.feed_frames(2.0, lambda frame: real("open together", frame))

    assert rig.controller.state is State.ACTIVE
    assert rig.output.commands == []


def test_the_steadiness_tolerance_comes_from_config() -> None:
    sway = 0.3 * HAND_SIZE * FRAME_S  # 0.3 hand sizes per second
    strict = Rig(OpenPalmConfig(steady_max_speed=0.05))
    default = Rig()

    strict.feed_frames(2.0, lambda frame: real("open together", frame, dx=sway * frame))
    default.feed_frames(2.0, lambda frame: real("open together", frame, dx=sway * frame))

    assert strict.controller.state is State.PAUSED
    assert default.controller.state is State.ACTIVE


def test_the_open_palm_threshold_comes_from_config() -> None:
    impossible = dataclasses.replace(OpenPalmConfig(), score_threshold=1.0)
    rig = Rig(impossible)

    rig.feed_frames(2.0, lambda frame: real("open together", frame))

    assert rig.controller.state is State.PAUSED


def test_the_reading_reports_score_speed_and_whether_they_pass() -> None:
    rig = Rig()
    assert rig.controller.reading.score is None
    assert rig.controller.reading.speed is None
    assert not rig.controller.reading.counts

    rig.feed_frames(0.5, lambda frame: real("open together", frame))
    steady = rig.controller.reading
    assert steady.score is not None
    assert steady.score >= steady.threshold
    assert steady.counts
    assert steady.steady
    assert steady.speed is not None
    assert steady.speed < steady.speed_limit

    rig.feed_frames(0.5, lambda frame: real("pointing", frame))
    assert not rig.controller.reading.counts
    assert rig.controller.reading.speed is not None  # the wrist is still followed

    rig.feed(FRAME_S, None)
    assert rig.controller.reading.score is None
    assert rig.controller.reading.speed is None
