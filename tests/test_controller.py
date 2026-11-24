from pathlib import Path

import pytest

from airmouse.config import TimingConfig
from airmouse.controller import Controller, State
from airmouse.gestures import Landmarks, Point, is_open_palm
from airmouse.renderer import (
    BACKGROUND,
    RING_CENTRE,
    RING_FILLED,
    RING_INNER,
    render_preview,
)
from png import decode_png

FRAME_S = 1 / 30
SNAPSHOTS = Path(__file__).parent / "snapshots"


class FakeOutput:
    def __init__(self) -> None:
        self.commands: list[str] = []

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

    def __init__(self) -> None:
        self.output = FakeOutput()
        self.controller = Controller(TimingConfig(), self.output)
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

    rig.feed(2.0, hand(palm=True), sway=0.01)  # 0.3 per second, 1.5 hand sizes per second

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
