"""The Fist clutch and relative control mode at the Controller seam, with a fake Mac.

The fake output is also the Screen: like Quartz, it reports the cursor where the last
event put it, and a display list a test can change. Closing-hand sequences come from
`anatomy.fist_sequence`: Pointer pose, half closed, fist, held, and reopening.
"""

import dataclasses
import io
import math
from typing import Any

import pytest

from airmouse.app import run_preview
from airmouse.config import ClutchConfig, Config, ControlConfig
from airmouse.controller import Controller, Phase, State
from airmouse.displays import Display
from airmouse.gestures import (
    Landmarks,
    Point,
    finger_curl,
    fist_score,
    is_open_palm,
    open_palm_score,
    pinch_ratio,
)
from airmouse.mapping import make_cursor_path
from airmouse.renderer import (
    DEBUG_BAR_OFFSET,
    DEBUG_BAR_WIDTH,
    DEBUG_FIST_TOP,
    DEBUG_LEFT,
    TEXT_ACTIVE,
    render_preview,
)
from anatomy import POSES, bent_pointer, closing_fist, fist_sequence, synthetic_hand, tucked_fist
from hands import open_hand, pinched, placed, pointing_hand
from lockstep import lockstep
from test_app import FakeCamera, FakeWindow
from test_pinch import Clock, Script
from test_renderer import label_band

FRAME_S = 1 / 30
MAIN = Display(0, 0, 1440, 900)
RIGHT = Display(1440, -180, 1920, 1080)
CLUTCH = ClutchConfig()
DEBOUNCE_FRAMES = math.ceil(CLUTCH.debounce_ms / 1000 / FRAME_S)


class FakeMac:
    """Records every command; the cursor is where the last event put it."""

    def __init__(self, displays: tuple[Display, ...] = (MAIN,), cursor: Point = (700, 400)):
        self.events: list[tuple[Any, ...]] = []
        self.down = False
        self.cursor = cursor
        self.list = displays

    def displays(self) -> tuple[Display, ...]:
        return self.list

    def cursor_position(self) -> Point | None:
        return self.cursor

    def _at(self, name: str, x: float, y: float) -> None:
        self.events.append((name, x, y))
        self.cursor = (x, y)

    def move_cursor(self, x: float, y: float) -> None:
        self._at("move", x, y)

    def press(self, x: float, y: float) -> None:
        self.down = True
        self._at("press", x, y)

    def drag_to(self, x: float, y: float) -> None:
        self._at("drag", x, y)

    def release(self, x: float, y: float) -> None:
        self.down = False
        self._at("release", x, y)

    def release_drag(self) -> None:
        self.down = False
        self.events.append(("release_drag",))

    def kinds(self) -> list[str]:
        return [event[0] for event in self.events]

    def moves(self) -> list[Point]:
        return [(event[1], event[2]) for event in self.events if event[0] == "move"]


class Rig:
    """A relative-mode Controller (unless told otherwise) fed at 30 fps; active by default."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        active: bool = True,
        mac: FakeMac | None = None,
    ) -> None:
        config = config or Config()
        self.mac = mac or FakeMac()
        self.controller = Controller(
            config.timing,
            self.mac,
            make_cursor_path(config, (1440.0, 900.0), self.mac),
            config.open_palm,
            config.pinch,
            config.clutch if config.control.mode == "relative" else None,  # as the app does
        )
        self.frame_number = 0
        if active:
            self.feed(1.0, open_hand())
            assert self.controller.state is State.ACTIVE
            self.feed(0.2, pointing_hand())
            self.mac.events.clear()

    def frame(self, landmarks: Landmarks | None) -> None:
        self.controller.update(self.frame_number * FRAME_S, landmarks)
        self.frame_number += 1

    def feed(self, seconds: float, landmarks: Landmarks | None) -> None:
        for _ in range(round(seconds / FRAME_S)):
            self.frame(landmarks)

    def play(self, hands: list[Landmarks]) -> list[bool]:
        """Feed each Hand in turn; returns whether the clutch was held after each."""
        held = []
        for hand in hands:
            self.frame(hand)
            held.append(self.controller.clutch)
        return held


def fist(dx: float = 0.0, dy: float = 0.0) -> Landmarks:
    return placed(synthetic_hand("fist"), dx=dx, dy=dy)


def pointer(dx: float = 0.0, dy: float = 0.0) -> Landmarks:
    return placed(pointing_hand(), dx=dx, dy=dy)


# --- the Fist score ---


@pytest.mark.parametrize("pitch", [-30.0, 0.0, 30.0])
@pytest.mark.parametrize("roll", [-20.0, 0.0, 20.0])
def test_a_fist_scores_as_a_fist_whatever_its_tilt(pitch: float, roll: float) -> None:
    hand = synthetic_hand("fist", pitch=pitch, roll=roll, jitter=0.003, seed=4)

    assert fist_score(hand) >= CLUTCH.score_threshold


@pytest.mark.parametrize(
    "pose",
    [
        "open together",
        "open relaxed curl",
        "open fanned",
        "open thumb tucked",
        "pointing",
        "pointing relaxed",
        "half-open fingers",
        "pinch fingers curled",
        "pinch others open",
    ],
)
@pytest.mark.parametrize("pitch", [-30.0, 0.0, 30.0])
def test_no_other_pose_reads_as_a_fist(pose: str, pitch: float) -> None:
    assert fist_score(synthetic_hand(pose, pitch=pitch)) < CLUTCH.score_threshold


def test_the_hands_used_elsewhere_are_not_fists() -> None:
    for hand in (open_hand(), pointing_hand(), pinched(pointing_hand(), 0.05)):
        assert fist_score(hand) == 0.0


def test_a_thumb_on_the_index_tip_is_a_pinch_never_a_fist() -> None:
    hand = list(synthetic_hand("fist"))
    assert finger_curl(hand) == 1.0
    size = math.dist(hand[0], hand[9])
    hand[4] = (hand[8][0] + 0.05 * size, hand[8][1])

    assert fist_score(hand) == 0.0


def test_a_fist_is_never_an_open_palm() -> None:
    for pitch in (-30.0, 0.0, 30.0):
        hand = synthetic_hand("fist", pitch=pitch)
        assert not is_open_palm(hand)
        assert open_palm_score(hand) < 0.6 / 2


def test_the_fist_score_rises_as_the_hand_closes() -> None:
    scores = [fist_score(closing_fist(step / 10)) for step in range(11)]

    assert scores[0] == 0.0
    assert scores[-1] == 1.0
    assert scores == sorted(scores)


def test_the_brushing_sequence_really_passes_through_a_pinch() -> None:
    """The worst-case closing hand does read as a closed Pinch for a few frames."""
    ratios = [pinch_ratio(hand) for hand in fist_sequence(brush=True)]

    assert min(r for r in ratios if r is not None) < Config().pinch.close_threshold


def test_the_fist_values_come_from_config() -> None:
    hand = synthetic_hand("fist")
    strict = dataclasses.replace(CLUTCH, finger_curled=0.2, finger_open=0.3)

    assert fist_score(hand, strict) == 0.0


# --- the clutch ---


def test_a_fist_held_past_the_debounce_is_the_clutch() -> None:
    rig = Rig()

    held = rig.play([fist()] * (DEBOUNCE_FRAMES + 2))

    assert held[: DEBOUNCE_FRAMES - 1] == [False] * (DEBOUNCE_FRAMES - 1)
    assert held[-1]
    reading = rig.controller.fist_reading
    assert reading is not None
    assert reading.counts and reading.clutch
    assert reading.score == pytest.approx(1.0)
    assert reading.threshold == CLUTCH.score_threshold


def test_one_misread_frame_of_fist_is_not_a_clutch() -> None:
    rig = Rig()

    held = rig.play([pointer(), fist(), pointer(), pointer()])

    assert not any(held)


def test_the_debounce_comes_from_config() -> None:
    config = Config(clutch=dataclasses.replace(CLUTCH, debounce_ms=500.0))
    rig = Rig(config)

    held = rig.play([fist()] * 10)

    assert not any(held)
    rig.feed(0.3, fist())
    assert rig.controller.clutch


def test_while_clutched_hand_movement_moves_nothing() -> None:
    rig = Rig()
    rig.feed(0.3, fist())
    assert rig.controller.clutch
    rig.mac.events.clear()

    for step in range(20):
        rig.frame(fist(dx=0.01 * step, dy=-0.005 * step))

    assert rig.mac.events == []


@pytest.mark.parametrize("brush", [False, True])
def test_resuming_after_a_clutch_never_jumps(brush: bool) -> None:
    rig = Rig()
    rig.feed(0.2, closing_fist(0.0))
    before = rig.mac.cursor
    rig.mac.events.clear()
    hands = fist_sequence(brush=brush)

    rig.play(hands[:20])  # close and hold
    assert rig.controller.clutch
    for step in range(15):  # reposition the hand while clutched
        rig.frame(placed(hands[19], dx=0.01 * step, dy=-0.007 * step))
    rig.play([placed(hand, dx=0.15, dy=-0.1) for hand in hands[20:]])  # reopen over there
    rig.feed(0.2, placed(closing_fist(0.0), dx=0.15, dy=-0.1))

    assert not rig.controller.clutch
    moves = rig.mac.moves()
    assert moves, "following resumed"
    # The hand moved a long way while clutched; the cursor did not follow it.
    assert math.dist(moves[-1], before) < 40
    assert all(math.dist(a, b) < 40 for a, b in zip(moves, moves[1:], strict=False))


def test_after_the_clutch_the_cursor_follows_the_hand_again() -> None:
    rig = Rig()
    rig.play(fist_sequence())
    start = rig.mac.cursor

    for step in range(10):
        rig.frame(pointer(dx=0.01 * step))

    assert rig.mac.cursor[0] > start[0] + 100


def test_a_clutch_releases_a_held_drag_where_the_cursor_was() -> None:
    rig = Rig()
    rig.feed(0.1, pinched(pointer(), 0.1))
    for step in range(9):
        rig.frame(pinched(pointer(dx=0.02 * step), 0.1))
    assert rig.mac.down and rig.controller.phase is Phase.DRAGGING

    # A fist whose thumb rests just off the index tip: the Pinch stays closed (between its
    # thresholds), so only the clutch can end this drag.
    closed = list(fist(dx=0.16))
    size = math.dist(closed[0], closed[9])
    closed[4] = (closed[8][0] - 0.35 * size, closed[8][1])
    assert rig.controller.phase is Phase.DRAGGING
    rig.feed(0.3, closed)

    assert rig.controller.clutch
    assert not rig.mac.down
    assert rig.mac.events[-1] == ("release_drag",)
    assert rig.controller.phase is Phase.IDLE


def test_no_click_or_drag_can_start_while_clutched() -> None:
    rig = Rig()
    rig.feed(0.3, fist())
    rig.mac.events.clear()

    # A thumb on the index tip of a closed hand is a Pinch pose, but it never presses.
    for step in range(10):
        hand = list(fist(dx=0.01 * step))
        hand[4] = hand[8]
        rig.frame(hand)

    assert "press" not in rig.mac.kinds()


# --- a closing hand is never a Pinch, never an Open palm ---


SEQUENCES = [
    pytest.param(start, brush, pitch, id=f"{start}-{'brush' if brush else 'clean'}-{pitch:+.0f}")
    for start in ("pointing", "pointing relaxed", "half-open fingers")
    for brush in (False, True)
    for pitch in (-30.0, 0.0, 30.0)
]


@pytest.mark.parametrize(("start", "brush", "pitch"), SEQUENCES)
def test_closing_and_reopening_a_fist_never_clicks_drags_or_pauses(
    start: str, brush: bool, pitch: float
) -> None:
    rig = Rig()
    hands = fist_sequence(start=start, brush=brush, pitch=pitch, jitter=0.002)

    for _ in range(3):  # three clutches in a row
        held = rig.play(hands)
        assert any(held)

    kinds = rig.mac.kinds()
    assert "press" not in kinds
    assert "release" not in kinds
    assert "drag" not in kinds
    assert rig.controller.state is State.ACTIVE
    assert not rig.mac.down


# Not from "half-open fingers": tilted back, that start pose itself scores as an Open palm.
@pytest.mark.parametrize(
    ("start", "brush", "pitch"), [case for case in SEQUENCES if "half" not in str(case.id)]
)
def test_a_closing_fist_never_unpauses(start: str, brush: bool, pitch: float) -> None:
    rig = Rig(active=False)

    for hand in fist_sequence(start=start, brush=brush, pitch=pitch, jitter=0.002) * 2:
        rig.frame(hand)
        assert rig.controller.state is State.PAUSED
        assert rig.controller.hold_progress == 0.0

    assert rig.mac.events == []


@pytest.mark.parametrize("pitch", [-30.0, 0.0, 30.0])
def test_closing_a_fist_barely_moves_the_cursor(pitch: float) -> None:
    rig = Rig()
    rig.feed(0.2, closing_fist(0.0, pitch=pitch))
    before = rig.mac.cursor

    rig.play(fist_sequence(pitch=pitch, jitter=0.002)[:20])

    assert math.dist(rig.mac.cursor, before) < 40


def test_a_real_pinch_still_clicks_with_the_other_fingers_curled() -> None:
    for pitch in (-30.0, 0.0):
        rig = Rig()
        aim = synthetic_hand("pointing relaxed", pitch=pitch)
        rig.feed(0.3, aim)
        rig.mac.events.clear()

        rig.feed(0.1, synthetic_hand("pinch fingers curled", pitch=pitch))
        rig.feed(0.1, aim)

        assert rig.mac.kinds()[:2] == ["press", "release"], pitch


def test_a_pinch_still_drags_when_the_whole_hand_moves() -> None:
    rig = Rig()
    rig.feed(0.1, pinched(pointer(), 0.1))

    for step in range(9):
        rig.frame(pinched(pointer(dx=0.02 * step), 0.1))

    assert rig.mac.kinds().count("press") == 1
    assert rig.mac.kinds().count("drag") >= 5


def test_a_pinch_whose_fingertip_curls_without_the_hand_moving_is_no_drag() -> None:
    rig = Rig()
    rig.feed(0.3, pointer())
    rig.mac.events.clear()
    pinch = list(pinched(pointer(), 0.1))
    rig.feed(0.1, pinch)

    for step in range(1, 7):  # only the index tip (and the thumb on it) moves, down a lot
        curling = list(pinch)
        curling[8] = (pinch[8][0], pinch[8][1] + 0.02 * step)
        curling[4] = (curling[8][0] - 0.02, curling[8][1])
        rig.frame(curling)

    assert "press" not in rig.mac.kinds()


# --- No hand is a clutch too; relative mode never jumps when the Hand returns ---


def test_a_hand_that_leaves_and_returns_elsewhere_resumes_without_a_jump() -> None:
    rig = Rig()
    rig.feed(0.3, pointer())
    before = rig.mac.cursor

    rig.feed(0.5, None)
    assert rig.controller.no_hand
    rig.frame(pointer(dx=0.2, dy=-0.1))  # back, far from where it left

    assert rig.mac.cursor == pytest.approx(before)
    rig.frame(pointer(dx=0.21, dy=-0.1))
    assert rig.mac.cursor[0] > before[0]


def test_the_cursor_starts_from_where_it_really_is() -> None:
    mac = FakeMac(cursor=(1234.0, 567.0))
    rig = Rig(mac=mac, active=False)
    rig.feed(1.0, open_hand())
    rig.feed(0.1, pointer(dx=-0.2))

    assert mac.moves()[0] == (1234.0, 567.0)


# --- displays ---


def test_the_cursor_crosses_to_another_display_and_back() -> None:
    mac = FakeMac((MAIN, RIGHT), cursor=(1300.0, 300.0))
    rig = Rig(mac=mac)

    for step in range(15):
        rig.frame(pointer(dx=0.01 * step))
    assert mac.cursor[0] > 1440  # on the right-hand display

    for step in range(15):
        rig.frame(pointer(dx=0.14 - 0.01 * step))
    assert mac.cursor[0] < 1440


def test_the_cursor_never_leaves_the_displays() -> None:
    mac = FakeMac((MAIN, RIGHT), cursor=(1300.0, 300.0))
    rig = Rig(mac=mac)

    for step in range(60):
        angle = step / 4
        rig.frame(pointer(dx=0.2 * math.cos(angle), dy=0.15 * math.sin(angle)))

    for x, y in mac.moves():
        assert (MAIN.x <= x <= MAIN.right and MAIN.y <= y <= MAIN.bottom) or (
            RIGHT.x <= x <= RIGHT.right and RIGHT.y <= y <= RIGHT.bottom
        )


def test_a_display_unplugged_under_the_cursor_moves_it_onto_the_remaining_one() -> None:
    mac = FakeMac((MAIN, RIGHT), cursor=(2500.0, -100.0))
    rig = Rig(mac=mac)
    rig.feed(0.2, pointer())

    mac.list = (MAIN,)
    rig.feed(1.2, pointer())

    x, y = mac.cursor
    assert MAIN.x <= x <= MAIN.right and MAIN.y <= y <= MAIN.bottom


# --- safety, as in absolute mode ---


def test_relative_mode_starts_paused_and_moves_nothing_while_paused() -> None:
    rig = Rig(active=False)

    for step in range(30):
        rig.frame(pointer(dx=0.01 * step))
    rig.feed(0.5, fist())
    rig.feed(0.5, None)

    assert rig.controller.state is State.PAUSED
    assert not rig.controller.clutch
    assert set(rig.mac.kinds()) <= {"release_drag"}  # No hand lifts the (already up) button
    assert not rig.mac.down


def test_an_open_palm_still_pauses_and_releases_a_drag_in_relative_mode() -> None:
    rig = Rig()
    rig.feed(0.1, pinched(pointer(), 0.1))
    for step in range(9):
        rig.frame(pinched(pointer(dx=0.02 * step), 0.1))
    assert rig.mac.down

    rig.feed(0.6, open_hand())

    assert rig.controller.state is State.PAUSED
    assert not rig.mac.down
    rig.mac.events.clear()
    rig.feed(0.5, pointer(dx=0.1))
    assert rig.mac.events == []


def test_absolute_mode_has_no_clutch_and_a_fist_moves_the_cursor_as_before() -> None:
    """Absolute mode is unchanged: the hand's position is the cursor, so there is nothing
    to clutch, and none of the relative-mode guards apply."""
    rig = Rig(Config(control=ControlConfig(mode="absolute")))
    rig.feed(0.3, fist())
    rig.mac.events.clear()

    for step in range(10):
        rig.frame(fist(dx=0.01 * step))

    assert not rig.controller.clutch
    assert not rig.controller.holding
    assert rig.controller.fist_reading is None
    assert rig.mac.kinds() == ["move"] * 10


def test_the_anatomy_poses_are_left_as_they_were() -> None:
    """`closing_fist` builds its blends without adding them to the shared pose table."""
    names = set(POSES)
    fist_sequence(brush=True)

    assert set(POSES) == names


# --- the app: the Preview shows the clutch; relative mode reads the screen it is given ---


def clutch_script(frame: int) -> Landmarks:
    """Unpause (30 frames), point (10 frames), then make a fist and hold it."""
    if frame < 30:
        return open_hand()
    if frame < 40:
        return pointer()
    return fist()


def run_app(mac: FakeMac, frames: int, *, debug_gestures: bool = False) -> FakeWindow:
    window = FakeWindow(frames=frames)
    camera, stepped_window = lockstep(FakeCamera(), window)
    run_preview(
        Config(),
        camera,
        Script(clutch_script),
        stepped_window,
        debug_gestures=debug_gestures,
        output=mac,
        screen=mac,
        clock=Clock(),
        timer=Clock(),
        out=io.StringIO(),
    )
    return window


def test_the_preview_says_clutch_while_the_fist_is_held() -> None:
    mac = FakeMac(cursor=(321.0, 123.0))

    window = run_app(mac, frames=50)

    clutch = render_preview(State.ACTIVE, landmarks=fist(), clutch=True)
    active = render_preview(State.ACTIVE, landmarks=fist())
    assert label_band(window.images[-1]).tobytes() == label_band(clutch).tobytes()
    assert label_band(window.images[38]).tobytes() == label_band(active).tobytes()
    assert mac.moves()[0] == (321.0, 123.0)  # relative mode started from the real cursor


def test_the_debug_readout_shows_the_fist_bar_counting() -> None:
    window = run_app(FakeMac(), frames=50, debug_gestures=True)

    image = window.images[-1]
    bar_row = DEBUG_FIST_TOP + DEBUG_BAR_OFFSET + 2
    row = range(DEBUG_LEFT, DEBUG_LEFT + DEBUG_BAR_WIDTH)
    assert any(image.get(x, bar_row) == TEXT_ACTIVE for x in row)


# --- a Pointer pose held at an angle to the camera is a Pointer, not a Fist ---


TILTED_POINTERS = [
    pytest.param(bend, pitch, id=f"{bend}-{pitch:+.0f}")
    for bend, pitches in (
        ((4.0, 6.0, 4.0), (-20.0, 0.0, 20.0, 40.0, 60.0)),
        ((15.0, 20.0, 10.0), (-20.0, 0.0, 20.0, 40.0, 60.0)),
        ((25.0, 30.0, 15.0), (-20.0, 0.0, 20.0, 40.0)),
        ((35.0, 45.0, 25.0), (-20.0, 0.0, 20.0)),
    )
    for pitch in pitches
]


@pytest.mark.parametrize(("bend", "pitch"), TILTED_POINTERS)
def test_a_tilted_or_bent_pointer_never_clutches_holds_or_stops_the_cursor(
    bend: tuple[float, float, float], pitch: float
) -> None:
    rig = Rig()
    start = (0.5, 0.75)
    rig.feed(0.2, bent_pointer(bend, pitch=pitch, centre=start))
    rig.mac.events.clear()
    before = rig.mac.cursor

    for frame in range(30):
        centre = (start[0] + 0.004 * frame, start[1])
        rig.frame(bent_pointer(bend, pitch=pitch, centre=centre, jitter=0.002, seed=frame))
        assert not rig.controller.clutch
        assert not rig.controller.holding

    assert rig.mac.kinds() == ["move"] * 30
    assert rig.mac.cursor[0] > before[0] + 200


@pytest.mark.parametrize("pitch", [-30.0, -20.0, 0.0, 20.0, 30.0])
@pytest.mark.parametrize("thumb", ["free", "tucked 0.15", "tucked 0.25"])
def test_a_fist_clutches_with_the_thumb_free_or_tucked(pitch: float, thumb: str) -> None:
    def make(seed: int) -> Landmarks:
        if thumb == "free":
            return synthetic_hand("fist", pitch=pitch, jitter=0.002, seed=seed)
        return tucked_fist(float(thumb.split()[1]), pitch=pitch, jitter=0.002, seed=seed)

    rig = Rig()
    held = rig.play([make(seed) for seed in range(DEBOUNCE_FRAMES + 3)])

    assert held[-1]


def test_the_hold_shows_while_the_fingers_curl_and_ends_when_the_clutch_takes_over() -> None:
    rig = Rig()
    hands = fist_sequence()

    holding, clutched = [], []
    for hand in hands:
        rig.frame(hand)
        holding.append(rig.controller.holding)
        clutched.append(rig.controller.clutch)

    assert any(holding[:13])  # while closing, before the clutch
    assert not any(h and c for h, c in zip(holding, clutched, strict=True))
    assert not holding[-1] and not clutched[-1]  # open again: following
    reading = rig.controller.fist_reading
    assert reading is not None and reading.hold_threshold == CLUTCH.hold_threshold


def test_the_hold_threshold_comes_from_config() -> None:
    half_closed = closing_fist(0.6)
    curl = finger_curl(half_closed)
    assert 0 < curl < 1

    for threshold, held in ((curl / 2, True), (min(1.0, curl + 0.05), False)):
        clutch = dataclasses.replace(CLUTCH, hold_threshold=threshold, score_threshold=1.0)
        rig = Rig(Config(clutch=clutch))
        rig.feed(0.2, half_closed)
        assert rig.controller.holding is held


def test_after_a_click_with_the_other_fingers_curled_the_cursor_follows_at_once() -> None:
    rig = Rig()
    aim = synthetic_hand("pinch fingers curled")
    open_pinch = pinched(aim, 0.8)  # the same hand with the thumb away: a Pointer pose
    rig.feed(0.3, open_pinch)
    rig.feed(0.1, aim)
    rig.frame(open_pinch)
    assert rig.mac.kinds()[-2:] == ["press", "release"]
    rig.mac.events.clear()

    for step in range(1, 8):
        rig.frame(placed(open_pinch, dx=0.01 * step))

    assert not rig.controller.holding
    assert rig.mac.kinds() == ["move"] * 7
