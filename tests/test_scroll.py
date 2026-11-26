"""The Scroll (issue #14): the two-finger pose, rate-based from an anchor, in both modes.

Every test drives the Controller with synthetic Hands and a fake output that records
each command, so the direction, speed, deadzone and every conflict are checked without
a Mac. Real scroll events and their feel need the user's Mac.
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
from airmouse.controller import Controller, State, scroll_speed
from airmouse.gestures import Landmarks, fist_score, is_open_palm, two_finger_score
from airmouse.mapping import make_cursor_path
from airmouse.output import OutputError, QuartzOutput
from airmouse.pipeline import ControllerStatus, ShutdownOutput
from anatomy import synthetic_hand
from hands import open_hand, pinched
from modes import base_config, clutch_for
from test_pinch import DISPLAY, FRAME_S, RecordingOutput, Window, run_app

# Every Controller test here runs in both control modes.
pytestmark = pytest.mark.usefixtures("control_mode")

SIZE = 0.2  # the synthetic Hands' size in frame heights: one hand size of movement is 0.2
WRIST_Y = 0.8
DEFAULT = ScrollConfig()
TWO_FINGER_POSES = ["two fingers", "two fingers relaxed"]
NOT_TWO_FINGER_POSES = [
    "fist",
    "pointing",
    "pointing relaxed",
    "half-open fingers",
    "open together",
    "open relaxed curl",
    "open fanned",
    "open thumb tucked",
    "pinch fingers curled",
    "pinch others open",
]
VIEWS = [(pitch, roll) for pitch in (-20.0, 0.0, 20.0) for roll in (-20.0, 0.0, 20.0)]


def pose(name: str, *, up: float = 0.0, dx: float = 0.0) -> Landmarks:
    """`name` with its wrist `up` hand sizes above the start (negative: below)."""
    return synthetic_hand(name, size=SIZE, centre=(0.5 + dx, WRIST_Y - SIZE * up))


def two(up: float = 0.0) -> Landmarks:
    return pose("two fingers", up=up)


def pointer(dx: float = 0.0) -> Landmarks:
    return pose("pointing", dx=dx)


class Rig:
    """A Controller with the app's wiring, fed at 30 fps; active unless told otherwise."""

    def __init__(self, config: Config | None = None, *, active: bool = True) -> None:
        config = config or base_config()
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

    def kinds(self) -> list[str]:
        return self.output.kinds()

    def scrolled(self) -> int:
        """Total pixels scrolled since the events were last cleared; positive is up."""
        return sum(event[1] for event in self.output.events if event[0] == "scroll")


def with_scroll(**changes: Any) -> Config:
    return dataclasses.replace(base_config(), scroll=dataclasses.replace(DEFAULT, **changes))


# --- the two-finger pose ---


@pytest.mark.parametrize("name", TWO_FINGER_POSES)
@pytest.mark.parametrize(("pitch", "roll"), VIEWS)
def test_a_relaxed_two_finger_pose_counts(name: str, pitch: float, roll: float) -> None:
    for seed in range(5):
        hand = synthetic_hand(name, pitch=pitch, roll=roll, jitter=0.004, seed=seed)

        assert two_finger_score(hand) >= DEFAULT.score_threshold + 0.1


@pytest.mark.parametrize("name", NOT_TWO_FINGER_POSES)
@pytest.mark.parametrize(("pitch", "roll"), VIEWS)
def test_the_pointer_an_open_palm_a_fist_and_a_pinch_never_count(
    name: str, pitch: float, roll: float
) -> None:
    for seed in range(5):
        hand = synthetic_hand(name, pitch=pitch, roll=roll, jitter=0.004, seed=seed)

        # "half-open fingers" (the middle half folded) is the closest call: below, but
        # with less than the margin the poses that count have.
        assert two_finger_score(hand) < DEFAULT.score_threshold


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


def test_an_unmeasurable_hand_scores_0_and_the_reach_range_comes_from_config() -> None:
    hand = synthetic_hand("two fingers")
    demanding = dataclasses.replace(DEFAULT, finger_curled=1.9, finger_extended=2.5)

    assert two_finger_score(hand[:20]) == 0.0
    assert two_finger_score([hand[0]] * 21) == 0.0
    assert two_finger_score(hand, demanding) < DEFAULT.score_threshold


# --- speed from the offset ---


def test_the_speed_is_zero_in_the_deadzone_then_ramps_linearly_up_to_the_cap() -> None:
    assert scroll_speed(0.0, DEFAULT) == 0.0
    assert scroll_speed(0.15, DEFAULT) == 0.0
    assert scroll_speed(-0.15, DEFAULT) == 0.0
    assert scroll_speed(0.25, DEFAULT) == pytest.approx(250.0)
    assert scroll_speed(0.35, DEFAULT) == pytest.approx(500.0)
    assert scroll_speed(-0.35, DEFAULT) == pytest.approx(-500.0)
    assert scroll_speed(5.0, DEFAULT) == 1500.0
    assert scroll_speed(-5.0, DEFAULT) == -1500.0


def test_invert_flips_the_direction_and_nothing_else() -> None:
    inverted = dataclasses.replace(DEFAULT, invert=True)

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


def test_the_offset_sets_a_steady_speed_in_pixels_per_second() -> None:
    rig = Rig()
    rig.start_scroll()

    rig.feed(1.0, two(up=0.35))  # 0.2 hand sizes past the deadzone: 500 pixels per second

    assert 498 <= rig.scrolled() <= 500
    assert rig.controller.scroll_reading.speed == pytest.approx(500.0, rel=0.02)


def test_the_speed_ramps_with_the_offset_and_is_capped() -> None:
    def pixels_in_one_second(up: float) -> int:
        rig = Rig()
        rig.start_scroll()
        rig.feed(1.0, two(up=up))
        return rig.scrolled()

    small, larger, huge = (pixels_in_one_second(up) for up in (0.25, 0.45, 3.0))

    assert 0 < small < larger < huge
    assert 1498 <= huge <= 1500  # the cap


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
    rig.output.events.clear()

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
    rig = Rig(with_scroll(invert=True))
    rig.start_scroll()

    rig.feed(0.5, two(up=0.5))

    assert rig.scrolled() < 0


def test_the_speed_settings_come_from_config() -> None:
    rig = Rig(with_scroll(deadzone=0.5, gain=1000.0, max_speed=200.0))
    rig.start_scroll()

    rig.feed(0.5, two(up=0.45))
    assert rig.output.events == []  # inside the wider deadzone

    rig.feed(1.0, two(up=3.0))
    assert 198 <= rig.scrolled() <= 200  # the lower cap


# --- entering and leaving the pose ---


def test_the_pose_must_be_held_for_the_debounce_before_scrolling_starts() -> None:
    rig = Rig()

    rig.frame(two())
    rig.frame(two(up=0.5))
    rig.frame(two(up=0.5))
    assert not rig.controller.scrolling
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


def test_leaving_the_pose_stops_the_scroll_at_once() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.6))

    rig.frame(pose("pointing", up=0.6))
    rig.output.events.clear()
    rig.feed(0.5, pose("pointing", up=0.6))

    assert not rig.controller.scrolling
    assert "scroll" not in rig.kinds()


def test_a_new_pose_scrolls_from_a_new_anchor() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.6))
    rig.feed(0.2, pose("pointing", up=0.6))
    rig.output.events.clear()

    rig.feed(0.5, two(up=0.6))  # the same height as before: the new anchor, so no scroll

    assert "scroll" not in rig.kinds()
    assert rig.controller.scrolling


def test_the_debounce_comes_from_config() -> None:
    rig = Rig(with_scroll(debounce_ms=500.0))

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
    rig = Rig()
    rig.feed(0.3, two())

    for up in (0.5, 1.0, -1.0, 0.0, 2.0, -2.0):
        rig.feed(0.2, two(up=up))
    rig.feed(0.3, pointer())

    assert not {"press", "drag", "release"} & set(rig.kinds())
    assert not rig.output.down


def test_the_cursor_follows_again_after_the_scroll_without_a_click() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))
    rig.feed(0.3, pointer())
    rig.output.events.clear()

    for step in range(10):
        rig.frame(pointer(dx=0.01 * step))

    assert set(rig.kinds()) == {"move"}


# --- conflicts: Pinch, pause, Fist, No hand ---


def test_a_pinch_closing_while_scrolling_stops_it_and_never_clicks() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))

    rig.feed(0.3, pinched(two(up=0.5), 0.05))
    rig.output.events.clear()
    rig.feed(0.3, pinched(two(up=0.5), 0.05))
    rig.feed(0.3, pointer())  # the Pinch opens

    assert not rig.controller.scrolling
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
    rig = Rig(active=False)

    rig.feed(0.5, two())
    rig.feed(1.0, two(up=1.0))

    assert rig.output.events == []
    assert not rig.controller.scrolling


def test_a_fist_ends_the_scroll_at_once() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))
    rig.output.events.clear()

    rig.frame(pose("fist", up=0.5))
    assert not rig.controller.scrolling
    rig.feed(0.5, pose("fist", up=0.5))

    assert "scroll" not in rig.kinds()


def test_a_short_dropout_keeps_the_scroll_without_a_burst() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.35))
    rig.output.events.clear()

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
    assert "scroll" not in rig.kinds()


def test_a_returning_hand_never_scrolls_on_its_own() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))
    rig.feed(0.5, None)
    rig.output.events.clear()

    for step in range(30):  # back in the pose, and moving
        rig.frame(two(up=0.5 + 0.05 * step))

    assert not rig.controller.scrolling
    assert "scroll" not in rig.kinds()

    rig.feed(0.2, pointer())  # leave the pose, then form it again
    rig.feed(0.2, two())
    rig.feed(0.5, two(up=0.5))
    assert rig.scrolled() > 0


# --- the readout ---


def test_the_reading_shows_the_score_offset_and_speed() -> None:
    rig = Rig()

    rig.frame(pointer())
    idle = rig.controller.scroll_reading
    rig.start_scroll()
    rig.feed(0.3, two(up=-0.35))
    scrolling = rig.controller.scroll_reading

    assert idle.score is not None and idle.score < idle.threshold
    assert not idle.counts and not idle.scrolling
    assert idle.offset is None and idle.speed == 0.0
    assert scrolling.counts and scrolling.scrolling
    assert scrolling.offset == pytest.approx(-0.35, abs=0.01)
    assert scrolling.speed == pytest.approx(-500.0, rel=0.05)
    assert (scrolling.threshold, scrolling.deadzone, scrolling.max_speed) == (0.5, 0.15, 1500.0)


def test_the_reading_with_no_hand_has_no_score() -> None:
    rig = Rig()

    rig.feed(0.5, None)

    reading = rig.controller.scroll_reading
    assert reading.score is None and not reading.counts and not reading.scrolling


# --- through the whole app, on the worker thread ---


def scroll_script(frame: int) -> Landmarks:
    """Unpause (30 frames), point, form the pose, then raise the Hand."""
    if frame < 30:
        return open_hand()
    if frame < 36:
        return pointer()
    if frame < 44:
        return two()
    return two(up=0.6)


def test_the_app_posts_scroll_events_through_the_output() -> None:
    output = RecordingOutput()

    run_app(output, Window(frames=70), scroll_script)

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


def test_a_refused_scroll_event_is_a_clear_error() -> None:
    with pytest.raises(OutputError, match="Accessibility"):
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


def test_the_snapshot_status_carries_the_scroll_for_the_preview() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))

    status = ControllerStatus.of(rig.controller)

    assert status.scroll is not None
    assert status.scroll.scrolling
    assert status.scroll == rig.controller.scroll_reading


# --- config ---


@pytest.fixture
def no_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


@pytest.mark.usefixtures("no_user_config")
def test_the_scroll_defaults_match_the_approved_proposal() -> None:
    scroll = load_config().scroll

    assert (scroll.deadzone, scroll.max_speed, scroll.invert) == (0.15, 1500.0, False)
    assert scroll.debounce_ms == 120.0
    assert "[scroll]" in format_config(Config())
    assert "invert = false" in format_config(Config())


@pytest.mark.usefixtures("no_user_config")
@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"deadzone": -0.1}, "scroll.deadzone: -0.1 is out of range"),
        ({"max_speed": 0}, "scroll.max_speed: 0.0 is out of range"),
        ({"gain": "fast"}, "scroll.gain: expected float"),
        ({"invert": 1}, "scroll.invert: expected bool"),
        ({"score_threshold": 1.5}, "scroll.score_threshold: 1.5 is out of range"),
        ({"score_threshold": 0}, "scroll.score_threshold: 0.0 is out of range"),
        ({"debounce_ms": -1}, "scroll.debounce_ms: -1.0 is out of range"),
        ({"finger_curled": 1.5, "finger_extended": 1.4}, "scroll.finger_curled: must be below"),
        ({"speed": 3}, "scroll.speed: unknown key"),
    ],
)
def test_bad_scroll_values_are_errors_naming_the_key(values: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(overrides={"scroll": values})


@pytest.mark.usefixtures("no_user_config")
def test_scroll_values_are_read_from_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[scroll]\ninvert = true\ngain = 4000\n")

    scroll = load_config(path).scroll

    assert scroll.invert is True
    assert scroll.gain == 4000.0
