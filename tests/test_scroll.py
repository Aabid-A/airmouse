"""The Scroll (issue #14): the two-finger pose, the Controller's rules, config and output.

Every test drives the Controller with synthetic Hands and a fake output that records
each command, so direction, speed, deadzone and every conflict are checked without a
Mac. Smoothing, the grace period and the flick are in test_scroll_motion.py. Real
scroll events and their feel need the user's Mac.
"""

import dataclasses
import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from airmouse.app import NoOutput
from airmouse.config import (
    ClutchConfig,
    Config,
    ConfigError,
    ScrollConfig,
    format_config,
    load_config,
)
from airmouse.controller import Controller, State
from airmouse.gestures import Landmarks, fist_score, hand_size, is_open_palm, two_finger_score
from airmouse.mapping import make_cursor_path
from airmouse.output import OutputError, QuartzOutput
from airmouse.pipeline import ControllerStatus, ShutdownOutput
from airmouse.scroll import ScrollState, scroll_speed
from anatomy import POSES, blend, seen_hand, synthetic_hand
from hands import open_hand, pinched
from modes import base_config, clutch_for
from test_pinch import DISPLAY, FRAME_S, RecordingOutput, Window, run_app

# Every Controller test here runs in both control modes.
pytestmark = pytest.mark.usefixtures("control_mode")

SIZE = 0.2  # the synthetic Hands' size in frame heights: one hand size of movement is 0.2
WRIST_Y = 0.8
DEFAULT = ScrollConfig()
CONTINUOUS = ScrollConfig(mode="continuous")
MARGIN = 0.1
TWO_FINGER_POSES = ["two fingers", "two fingers relaxed"]
NOT_TWO_FINGER_POSES = [
    "fist",
    "pointing",
    "pointing relaxed",
    "half-open fingers",
    "three fingers",
    "index and pinky",
    "thumbs up",
    "open together",
    "open relaxed curl",
    "open fanned",
    "open thumb tucked",
    "pinch fingers curled",
    "pinch others open",
]
VIEWS = [(pitch, roll) for pitch in (-20.0, 0.0, 20.0) for roll in (-20.0, 0.0, 20.0)]
PITCH_SWEEP = [float(pitch) for pitch in range(-30, 80, 5)]
TOWARDS_CAMERA = [40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0]


def pose(name: str, *, up: float = 0.0, dx: float = 0.0, pitch: float = 0.0) -> Landmarks:
    """`name` with its wrist `up` hand sizes above the start (negative: below)."""
    return synthetic_hand(name, size=SIZE, centre=(0.5 + dx, WRIST_Y - SIZE * up), pitch=pitch)


def two(up: float = 0.0) -> Landmarks:
    return pose("two fingers", up=up)


def pointer(dx: float = 0.0) -> Landmarks:
    return pose("pointing", dx=dx)


def overlapped(hand: Landmarks) -> Landmarks:
    """The middle fingertip drawn right on the index tip, as when both point at the lens."""
    size = hand_size(hand)
    result = list(hand)
    result[12] = (hand[8][0] + 0.03 * size, hand[8][1] + 0.02 * size)
    return result


def occluded(hand: Landmarks) -> Landmarks:
    """The middle fingertip pulled back towards its last joint, as when hidden behind the index."""
    result = list(hand)
    (jx, jy), (tx, ty) = hand[11], hand[12]
    result[12] = (jx + 0.4 * (tx - jx), jy + 0.4 * (ty - jy))
    return result


class Rig:
    """A Controller with the app's wiring, fed at 30 fps; active unless told otherwise.

    The Scroll is continuous unless `scroll` says otherwise, so a sudden move in a test
    is never taken for a flick."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        scroll: ScrollConfig | None = None,
        active: bool = True,
    ) -> None:
        config = config or base_config()
        config = dataclasses.replace(config, scroll=scroll or CONTINUOUS)
        self.output = RecordingOutput()
        self.controller = Controller(
            config.timing,
            self.output,
            make_cursor_path(config, DISPLAY),
            config.open_palm,
            config.pinch,
            clutch_for(config),
            config.scroll,
        )
        self.time = 0.0
        if active:
            self.feed(1.0, open_hand())
            assert self.controller.state is State.ACTIVE
            self.feed(0.3, pointer())
            self.output.events.clear()

    def feed(self, seconds: float, landmarks: Landmarks | None) -> None:
        for _ in range(round(seconds / FRAME_S)):
            self.frame(landmarks)

    def frame(self, landmarks: Landmarks | None) -> None:
        self.controller.update(self.time, landmarks)
        self.time += FRAME_S

    def start_scroll(self) -> None:
        """Form the two-finger pose at the start height and hold it past the debounce."""
        self.feed(0.2, two())
        assert self.controller.scrolling
        self.output.events.clear()

    def settle(self, landmarks: Landmarks) -> None:
        """Hold `landmarks` long enough for the smoothing to settle, then forget the events."""
        self.feed(1.0, landmarks)
        self.output.events.clear()

    def kinds(self) -> list[str]:
        return self.output.kinds()

    def scrolled(self) -> int:
        """Total pixels scrolled since the events were last cleared; positive is up."""
        return sum(event[1] for event in self.output.events if event[0] == "scroll")

    @property
    def state(self) -> ScrollState:
        return self.controller.scroll_reading.state


def scroll_with(**changes: Any) -> ScrollConfig:
    return dataclasses.replace(CONTINUOUS, **changes)


# --- the two-finger pose ---


@pytest.mark.parametrize("name", TWO_FINGER_POSES)
@pytest.mark.parametrize(("pitch", "roll"), VIEWS)
def test_a_relaxed_two_finger_pose_counts(name: str, pitch: float, roll: float) -> None:
    for seed in range(5):
        hand = synthetic_hand(name, pitch=pitch, roll=roll, jitter=0.004, seed=seed)

        assert two_finger_score(hand) >= DEFAULT.score_threshold + MARGIN


@pytest.mark.parametrize("name", NOT_TWO_FINGER_POSES)
@pytest.mark.parametrize("pitch", PITCH_SWEEP)
def test_no_other_hand_shape_comes_near_the_thresholds_at_any_tilt(name: str, pitch: float) -> None:
    for roll in (-20.0, 0.0, 20.0):
        for seed in range(3):
            hand = synthetic_hand(name, pitch=pitch, roll=roll, jitter=0.004, seed=seed)

            # Below the exit threshold with a margin, so none of them can start a scroll
            # or keep one going.
            assert two_finger_score(hand) <= DEFAULT.exit_threshold - MARGIN


@pytest.mark.parametrize("pitch", TOWARDS_CAMERA)
def test_two_fingers_pointing_at_the_camera_still_count_even_overlapping(pitch: float) -> None:
    for seed in range(5):
        hand = synthetic_hand("two fingers", pitch=pitch, jitter=0.004, seed=seed)

        for seen in (hand, overlapped(hand), occluded(hand)):
            assert two_finger_score(seen) >= DEFAULT.score_threshold + MARGIN


@pytest.mark.parametrize("pitch", [40.0, 45.0, 50.0, 55.0, 60.0])
def test_relaxed_two_fingers_pointing_at_the_camera_stay_above_the_exit(pitch: float) -> None:
    for seed in range(5):
        hand = synthetic_hand("two fingers relaxed", pitch=pitch, jitter=0.004, seed=seed)

        for seen in (hand, overlapped(hand), occluded(hand)):
            assert two_finger_score(seen) >= DEFAULT.exit_threshold + MARGIN


def test_the_pair_takes_the_better_finger_only_when_the_tips_are_together() -> None:
    hand = synthetic_hand("two fingers", pitch=60.0)
    hidden = list(hand)
    hidden[12] = hand[16]  # the middle tip misread down by the curled ring: reads folded
    together = list(hidden)
    together[12] = hand[8]  # ...but drawn on the index tip instead: the pair still counts

    assert two_finger_score(hidden) < DEFAULT.exit_threshold
    assert two_finger_score(together) >= DEFAULT.score_threshold


@pytest.mark.parametrize("name", TWO_FINGER_POSES)
def test_the_two_finger_pose_is_never_an_open_palm_or_a_fist(name: str) -> None:
    for pitch, roll in VIEWS:
        hand = synthetic_hand(name, pitch=pitch, roll=roll)

        assert not is_open_palm(hand)
        assert fist_score(hand) < ClutchConfig().score_threshold


def test_the_two_finger_score_reads_the_same_near_or_far_and_stays_in_range() -> None:
    near = synthetic_hand("two fingers relaxed", size=0.35)
    far = synthetic_hand("two fingers relaxed", size=0.12)

    assert two_finger_score(near) == pytest.approx(two_finger_score(far), abs=1e-6)
    for name in [*TWO_FINGER_POSES, *NOT_TWO_FINGER_POSES]:
        assert 0.0 <= two_finger_score(synthetic_hand(name, jitter=0.01, seed=2)) <= 1.0


def test_an_unmeasurable_hand_scores_0_and_the_pose_thresholds_come_from_config() -> None:
    hand = synthetic_hand("two fingers")
    far_apart = dataclasses.replace(DEFAULT, separation=3.0)
    strict_tips = dataclasses.replace(
        DEFAULT, tip_curled=1.0, tip_open=1.5, finger_curled=2.5, finger_open=3.0
    )

    assert two_finger_score(hand[:20]) == 0.0
    assert two_finger_score([hand[0]] * 21) == 0.0
    assert two_finger_score(hand, far_apart) < DEFAULT.exit_threshold
    assert two_finger_score(hand, strict_tips) < DEFAULT.exit_threshold


def between_the_thresholds() -> Landmarks:
    """A Hand partway from two fingers to the Pointer pose, whose score lies between the
    exit and the entry thresholds."""
    for step in range(101):
        hand = seen_hand(blend(POSES["two fingers"], POSES["pointing"], step / 100), size=SIZE)
        score = two_finger_score(hand)
        if DEFAULT.exit_threshold + 0.05 < score < DEFAULT.score_threshold - 0.05:
            return [(x, y - (0.75 - WRIST_Y)) for x, y in hand]
    raise AssertionError("no blend scores between the thresholds")


# --- speed from the offset ---


def test_the_speed_is_zero_in_the_deadzone_then_eases_into_the_linear_rate_up_to_the_cap() -> None:
    assert scroll_speed(0.0, DEFAULT) == 0.0
    assert scroll_speed(0.15, DEFAULT) == 0.0
    assert scroll_speed(-0.15, DEFAULT) == 0.0
    assert 0 < scroll_speed(0.16, DEFAULT) < 0.05 * 2500 * 0.01  # eased: far below linear
    assert scroll_speed(0.25, DEFAULT) == pytest.approx(250.0 * (20 / 27))  # smoothstep(2/3)
    assert scroll_speed(0.35, DEFAULT) == pytest.approx(500.0)  # past the ease: linear
    assert scroll_speed(-0.35, DEFAULT) == pytest.approx(-500.0)
    assert scroll_speed(5.0, DEFAULT) == 1500.0
    assert scroll_speed(-5.0, DEFAULT) == -1500.0


def test_the_speed_rises_without_a_step_at_the_deadzone_edge() -> None:
    offsets = [0.15 + step * 0.001 for step in range(400)]
    speeds = [scroll_speed(offset, DEFAULT) for offset in offsets]

    steps = [b - a for a, b in zip(speeds, speeds[1:], strict=False)]
    assert all(step >= 0 for step in steps)
    assert max(steps) <= 2500 * 0.001 * 1.8  # the ease is never much steeper than linear
    assert steps[0] < 0.01


def test_no_ease_gives_the_plain_linear_rate_and_invert_flips_the_direction() -> None:
    linear = dataclasses.replace(DEFAULT, ease=0.0)
    inverted = dataclasses.replace(DEFAULT, invert=True)

    assert scroll_speed(0.25, linear) == pytest.approx(250.0)
    assert scroll_speed(0.35, inverted) == pytest.approx(-500.0)
    assert scroll_speed(-5.0, inverted) == 1500.0
    assert scroll_speed(0.1, inverted) == 0.0


# --- the Controller: direction, speed, deadzone ---


def test_holding_the_pose_still_scrolls_nothing_and_moves_nothing() -> None:
    rig = Rig()
    rig.start_scroll()

    rig.feed(1.0, two())

    assert rig.output.events == []
    assert rig.controller.scrolling


def test_hand_up_scrolls_up_and_hand_down_scrolls_down() -> None:
    rig = Rig()
    rig.start_scroll()

    rig.feed(0.5, two(up=0.5))
    up = rig.scrolled()
    rig.output.events.clear()
    rig.feed(0.5, two(up=-0.5))

    assert up > 0
    assert rig.scrolled() < 0
    assert set(rig.kinds()) == {"scroll"}


def test_a_held_offset_settles_to_a_steady_speed_in_pixels_per_second() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.settle(two(up=0.35))  # 0.2 hand sizes past the deadzone: 500 pixels per second

    rig.feed(1.0, two(up=0.35))

    assert 495 <= rig.scrolled() <= 500
    assert rig.controller.scroll_reading.speed == pytest.approx(500.0, rel=0.01)


def test_the_speed_ramps_with_the_offset_and_is_capped() -> None:
    def pixels_in_one_second(up: float) -> int:
        rig = Rig()
        rig.start_scroll()
        rig.settle(two(up=up))
        rig.feed(1.0, two(up=up))
        return rig.scrolled()

    small, larger, huge = (pixels_in_one_second(up) for up in (0.25, 0.45, 3.0))

    assert 0 < small < larger < huge
    assert 1495 <= huge <= 1500  # the cap


def test_an_offset_inside_the_deadzone_scrolls_nothing() -> None:
    rig = Rig()
    rig.start_scroll()

    rig.feed(0.5, two(up=0.1))
    rig.feed(0.5, two(up=-0.1))

    assert rig.output.events == []


def test_returning_to_the_anchor_stops_the_scroll() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.6))
    rig.settle(two())

    rig.feed(0.5, two())

    assert rig.output.events == []
    assert rig.controller.scrolling


def test_the_anchor_is_where_the_pose_started_not_the_screen() -> None:
    rig = Rig()
    rig.feed(0.2, two(up=1.0))  # the pose starts high in the frame
    rig.output.events.clear()

    rig.feed(0.5, two(up=1.0))
    assert rig.output.events == []

    rig.feed(0.5, two(up=0.5))
    assert rig.scrolled() < 0  # below the anchor: down, though still high in the frame


def test_invert_in_config_flips_the_scroll() -> None:
    rig = Rig(scroll=scroll_with(invert=True))
    rig.start_scroll()

    rig.feed(0.5, two(up=0.5))

    assert rig.scrolled() < 0


def test_the_speed_settings_come_from_config() -> None:
    rig = Rig(scroll=scroll_with(deadzone=0.5, gain=1000.0, max_speed=200.0))
    rig.start_scroll()

    rig.feed(0.5, two(up=0.45))
    assert rig.output.events == []  # inside the wider deadzone

    rig.settle(two(up=3.0))
    rig.feed(1.0, two(up=3.0))
    assert 198 <= rig.scrolled() <= 200  # the lower cap


def test_a_stalled_worker_never_posts_one_huge_burst() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.settle(two(up=3.0))  # 1500 pixels per second

    rig.time += 2.0  # two seconds with no frame at all
    rig.frame(two(up=3.0))

    assert 0 < rig.scrolled() <= 1500 * 0.1


# --- entering and leaving the pose ---


def test_the_pose_must_be_held_for_the_debounce_before_scrolling_starts() -> None:
    rig = Rig()

    rig.frame(two())
    rig.frame(two(up=0.5))
    rig.frame(two(up=0.5))
    assert not rig.controller.scrolling
    assert rig.state is ScrollState.ARMING
    assert "scroll" not in rig.kinds()

    rig.feed(0.2, two(up=0.5))
    assert rig.controller.scrolling


def test_passing_through_the_pose_never_scrolls() -> None:
    rig = Rig()

    for _ in range(5):
        rig.frame(two(up=0.6))
        rig.frame(two(up=0.6))
        rig.frame(pointer())

    assert "scroll" not in rig.kinds()


def test_entry_needs_the_entry_threshold_but_staying_needs_only_the_exit_one() -> None:
    middling = between_the_thresholds()
    rig = Rig()

    rig.feed(0.5, middling)
    assert not rig.controller.scrolling  # never enough to start

    rig.start_scroll()
    rig.feed(1.0, middling)
    assert rig.controller.scrolling  # enough to stay
    assert rig.state is ScrollState.SCROLLING


def test_relaxing_to_a_pointer_ends_the_scroll_within_the_grace_period() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.6))
    grace_frames = round(DEFAULT.grace_ms / 1000 / FRAME_S)

    rig.frame(pose("pointing", up=0.6))
    assert rig.state is ScrollState.GRACE
    rig.feed(DEFAULT.grace_ms / 1000, pose("pointing", up=0.6))
    rig.output.events.clear()
    rig.feed(0.5, pose("pointing", up=0.6))

    assert grace_frames > 1
    assert not rig.controller.scrolling
    assert "scroll" not in rig.kinds()


def test_a_new_pose_scrolls_from_a_new_anchor() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.6))
    rig.feed(0.5, pose("pointing", up=0.6))
    rig.output.events.clear()

    rig.feed(0.5, two(up=0.6))  # the same height as before: the new anchor, so no scroll

    assert "scroll" not in rig.kinds()
    assert rig.controller.scrolling


def test_the_debounce_comes_from_config() -> None:
    rig = Rig(scroll=scroll_with(debounce_ms=500.0))

    rig.feed(0.3, two())
    assert not rig.controller.scrolling

    rig.feed(0.3, two())
    assert rig.controller.scrolling


# --- the cursor and the button ---


def test_the_cursor_holds_still_while_scrolling() -> None:
    rig = Rig()
    rig.start_scroll()

    for step in range(30):
        rig.frame(pose("two fingers", up=0.5, dx=0.01 * step))  # sideways too

    assert "move" not in rig.kinds()


def test_scrolling_never_presses_drags_or_releases_the_button() -> None:
    rig = Rig(scroll=DEFAULT)  # auto: flicks too
    rig.feed(0.3, two())

    for up in (0.5, 1.0, -1.0, 0.0, 2.0, -2.0):
        rig.feed(0.2, two(up=up))
    rig.feed(0.5, pointer())

    assert not {"press", "drag", "release"} & set(rig.kinds())
    assert not rig.output.down


def test_the_cursor_follows_again_after_the_scroll_without_a_click() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))
    rig.feed(0.5, pointer())
    rig.output.events.clear()

    for step in range(10):
        rig.frame(pointer(dx=0.01 * step))

    assert set(rig.kinds()) == {"move"}


# --- conflicts: Pinch, pause, Fist, No hand ---


def test_a_pinch_closing_while_scrolling_stops_it_at_once_and_never_clicks() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))
    rig.output.events.clear()

    rig.frame(pinched(two(up=0.5), 0.05))
    assert not rig.controller.scrolling  # no grace for a Pinch
    rig.feed(0.3, pinched(two(up=0.5), 0.05))
    rig.feed(0.3, pointer())  # the Pinch opens

    assert not {"press", "release", "drag", "scroll"} & set(rig.kinds())


def test_a_pinch_is_never_the_two_finger_pose() -> None:
    rig = Rig()

    rig.feed(0.5, pinched(two(), 0.05))

    assert not rig.controller.scrolling
    assert rig.controller.scroll_reading.score == 0.0


def test_opening_a_drag_into_the_pose_lifts_the_button_before_any_scroll() -> None:
    rig = Rig()
    rig.feed(0.2, pinched(pointer(), 0.05))
    for step in range(10):
        rig.frame(pinched(pointer(dx=0.02 * step), 0.05))
    assert rig.output.down

    rig.feed(0.5, two(up=0.0))
    rig.feed(0.5, two(up=0.6))

    kinds = rig.kinds()
    assert not rig.output.down
    assert "scroll" in kinds
    assert kinds.index("release") < kinds.index("scroll")


def test_an_open_palm_stops_the_scroll_at_once_and_pauses() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))
    rig.output.events.clear()

    rig.frame(open_hand())
    assert not rig.controller.scrolling
    rig.feed(0.3, open_hand())

    assert rig.controller.state is State.PAUSED
    assert "scroll" not in rig.kinds()


def test_nothing_happens_while_paused() -> None:
    rig = Rig(scroll=DEFAULT, active=False)

    rig.feed(0.5, two())
    rig.feed(1.0, two(up=1.0))
    rig.feed(0.2, two())
    for up in (0.3, 0.6, 0.9):
        rig.frame(two(up=up))  # a flick

    assert rig.output.events == []
    assert not rig.controller.scrolling


def test_a_fist_ends_the_scroll_within_the_grace_period_and_at_once_with_the_clutch() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))
    rig.output.events.clear()

    rig.frame(pose("fist", up=0.5))
    if rig.controller.fist_reading is not None:  # relative mode: the Fist counts at once
        assert not rig.controller.scrolling
    rig.feed(DEFAULT.grace_ms / 1000 + FRAME_S, pose("fist", up=0.5))
    assert not rig.controller.scrolling
    rig.output.events.clear()
    rig.feed(0.5, pose("fist", up=0.5))

    assert "scroll" not in rig.kinds()


def test_a_short_dropout_keeps_the_scroll_without_a_burst() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.settle(two(up=0.35))

    rig.feed(0.1, None)  # shorter than the No hand timeout
    assert rig.output.events == []
    rig.frame(two(up=0.35))

    assert rig.controller.scrolling
    assert 0 < rig.scrolled() <= 17  # one frame's share of 500 pixels per second


def test_no_hand_ends_the_scroll() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))
    rig.output.events.clear()

    rig.feed(0.5, None)

    assert rig.controller.no_hand
    assert not rig.controller.scrolling
    assert rig.state is ScrollState.BLOCKED
    assert "scroll" not in rig.kinds()


def test_a_returning_hand_never_scrolls_on_its_own() -> None:
    rig = Rig(scroll=DEFAULT)  # auto: neither continuous nor flick
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))
    rig.feed(0.5, None)
    rig.output.events.clear()

    for step in range(30):  # back in the pose, and moving fast
        rig.frame(two(up=0.5 + 0.1 * step))

    assert not rig.controller.scrolling
    assert rig.state is ScrollState.BLOCKED
    assert "scroll" not in rig.kinds()

    rig.feed(0.2, pointer())  # leave the pose, then form it again
    rig.feed(0.3, two())
    for step in range(30):
        rig.frame(two(up=0.02 * step))
    rig.feed(0.5, two(up=0.6))
    assert rig.scrolled() > 0


# --- the readout ---


def test_the_reading_shows_the_score_thresholds_offset_and_speed() -> None:
    rig = Rig()

    rig.frame(pointer())
    idle = rig.controller.scroll_reading
    rig.start_scroll()
    rig.settle(two(up=-0.35))
    scrolling = rig.controller.scroll_reading

    assert idle.state is ScrollState.IDLE
    assert idle.score is not None and idle.score < idle.threshold
    assert not idle.counts and not idle.scrolling
    assert idle.offset is None and idle.speed == 0.0 and idle.flick is None
    assert scrolling.state is ScrollState.SCROLLING
    assert scrolling.counts and scrolling.scrolling
    assert scrolling.offset == pytest.approx(-0.35, abs=0.01)
    assert scrolling.speed == pytest.approx(-500.0, rel=0.02)
    assert scrolling.flick == pytest.approx(0.0, abs=0.01)
    assert (scrolling.threshold, scrolling.exit_threshold) == (0.5, 0.3)
    assert (scrolling.deadzone, scrolling.max_speed, scrolling.flick_speed) == (0.15, 1500.0, 3.0)


def test_the_reading_with_no_hand_has_no_score() -> None:
    rig = Rig()

    rig.feed(0.5, None)

    reading = rig.controller.scroll_reading
    assert reading.score is None and not reading.counts and not reading.scrolling


def test_the_snapshot_status_carries_the_scroll_for_the_preview() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))

    status = ControllerStatus.of(rig.controller)

    assert status.scroll is not None
    assert status.scroll.scrolling
    assert status.scroll == rig.controller.scroll_reading


# --- through the whole app, on the worker thread ---


def scroll_script(frame: int) -> Landmarks:
    """Unpause (30 frames), point, form the pose, then raise the Hand slowly."""
    if frame < 30:
        return open_hand()
    if frame < 36:
        return pointer()
    if frame < 44:
        return two()
    return two(up=min(0.8, 0.03 * (frame - 44)))


def test_the_app_posts_scroll_events_through_the_output() -> None:
    output = RecordingOutput()

    run_app(output, Window(frames=90), scroll_script)

    assert output.kinds().count("scroll") > 10
    assert sum(event[1] for event in output.events if event[0] == "scroll") > 0
    assert "press" not in output.kinds()


# --- the outputs ---


class FakeQuartz:
    kCGScrollEventUnitPixel = 0
    kCGHIDEventTap = 0

    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse
        self.bounds = SimpleNamespace(
            origin=SimpleNamespace(x=0, y=0), size=SimpleNamespace(width=1440.0, height=900.0)
        )
        self.posted: list[Any] = []

    def CGMainDisplayID(self) -> int:
        return 1

    def CGDisplayBounds(self, display: int) -> Any:
        return self.bounds

    def CGEventCreateScrollWheelEvent(self, source: Any, unit: int, wheels: int, dy: int) -> Any:
        return None if self.refuse else ("scroll", unit, wheels, dy)

    def CGEventPost(self, tap: int, event: Any) -> None:
        self.posted.append(event)


def test_quartz_posts_a_pixel_scroll_wheel_event() -> None:
    quartz = FakeQuartz()

    QuartzOutput(quartz).scroll(-12)

    assert quartz.posted == [("scroll", quartz.kCGScrollEventUnitPixel, 1, -12)]


def test_a_refused_scroll_event_is_a_clear_error_naming_it() -> None:
    with pytest.raises(OutputError, match="refused to create a scroll event.*Accessibility"):
        QuartzOutput(FakeQuartz(refuse=True)).scroll(3)


def test_the_shutdown_output_forwards_scroll_and_ignores_it_after_close() -> None:
    output = RecordingOutput()
    guarded = ShutdownOutput(output, io.StringIO())

    guarded.scroll(5)
    guarded.close()
    guarded.scroll(7)

    assert output.events == [("scroll", 5), ("release_drag",)]


def test_no_output_ignores_scroll() -> None:
    NoOutput().scroll(10)


# --- config ---


@pytest.fixture
def no_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


EXPECTED_DEFAULTS: dict[str, Any] = {
    "mode": "auto",
    "invert": False,
    "deadzone": 0.15,
    "ease": 0.15,
    "gain": 2500.0,
    "max_speed": 1500.0,
    "min_cutoff": 0.5,
    "beta": 0.3,
    "score_threshold": 0.5,
    "exit_threshold": 0.3,
    "debounce_ms": 120.0,
    "grace_ms": 250.0,
    "tip_curled": -0.5,
    "tip_open": 0.0,
    "finger_curled": 1.0,
    "finger_open": 1.4,
    "pair_gap": 0.3,
    "separation": 0.5,
    "flick_speed": 3.0,
    "flick_min_travel": 0.3,
    "flick_window_ms": 150.0,
    "flick_pixels": 600,
    "flick_cooldown_ms": 500.0,
}


@pytest.mark.usefixtures("no_user_config")
def test_every_scroll_default_is_as_documented_and_printed() -> None:
    scroll = load_config().scroll
    printed = format_config(Config())

    assert dataclasses.asdict(scroll) == EXPECTED_DEFAULTS
    assert "[scroll]" in printed
    for key in EXPECTED_DEFAULTS:
        assert f"\n{key} = " in printed.split("[scroll]")[1]


@pytest.mark.usefixtures("no_user_config")
@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"mode": "page"}, "scroll.mode: 'page' is not valid; valid values are auto"),
        ({"deadzone": -0.1}, "scroll.deadzone: -0.1 is out of range"),
        ({"ease": 3}, "scroll.ease: 3.0 is out of range"),
        ({"max_speed": 0}, "scroll.max_speed: 0.0 is out of range"),
        ({"gain": "fast"}, "scroll.gain: expected float"),
        ({"invert": 1}, "scroll.invert: expected bool"),
        ({"min_cutoff": 0}, "scroll.min_cutoff: 0.0 is out of range"),
        ({"beta": -1}, "scroll.beta: -1.0 is out of range"),
        ({"score_threshold": 1.5}, "scroll.score_threshold: 1.5 is out of range"),
        ({"score_threshold": 0}, "scroll.score_threshold: 0.0 is out of range"),
        ({"exit_threshold": 0.6}, "scroll.exit_threshold: must be at most"),
        ({"debounce_ms": -1}, "scroll.debounce_ms: -1.0 is out of range"),
        ({"grace_ms": 3000}, "scroll.grace_ms: 3000.0 is out of range"),
        ({"tip_curled": 0.1, "tip_open": 0.0}, "scroll.tip_curled: must be below"),
        ({"finger_curled": 1.5, "finger_open": 1.4}, "scroll.finger_curled: must be below"),
        ({"pair_gap": -0.1}, "scroll.pair_gap: -0.1 is out of range"),
        ({"separation": 0}, "scroll.separation: 0.0 is out of range"),
        ({"flick_speed": 0}, "scroll.flick_speed: 0.0 is out of range"),
        ({"flick_min_travel": 0}, "scroll.flick_min_travel: 0.0 is out of range"),
        ({"flick_window_ms": 5}, "scroll.flick_window_ms: 5.0 is out of range"),
        ({"flick_pixels": 600.5}, "scroll.flick_pixels: expected int"),
        ({"flick_pixels": 0}, "scroll.flick_pixels: 0 is out of range"),
        ({"flick_cooldown_ms": -1}, "scroll.flick_cooldown_ms: -1.0 is out of range"),
        ({"speed": 3}, "scroll.speed: unknown key"),
    ],
)
def test_bad_scroll_values_are_errors_naming_the_key(values: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(overrides={"scroll": values})


@pytest.mark.usefixtures("no_user_config")
def test_scroll_values_are_read_from_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[scroll]\nmode = "continuous"\ninvert = true\ngain = 4000\n')

    scroll = load_config(path).scroll

    assert scroll.mode == "continuous"
    assert scroll.invert is True
    assert scroll.gain == 4000.0
