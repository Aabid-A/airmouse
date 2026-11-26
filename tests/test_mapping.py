import dataclasses

import pytest

from airmouse.config import Config, ConfigError, ControlConfig, FilterConfig
from airmouse.controller import Controller, State
from airmouse.frame import prepare_point
from airmouse.gestures import POINTER, Landmarks, Point
from airmouse.mapping import AbsolutePath, RelativePath, make_cursor_path, make_mapping
from anatomy import synthetic_hand
from hands import open_hand, pointing_hand

FRAME_S = 1 / 30
# These tests are about absolute control mode (no longer the default), so they ask for it.
ABSOLUTE = Config(control=ControlConfig(mode="absolute"))
DISPLAY = (1600.0, 1000.0)
# The default Active region of a 640x480 frame on a 16:10 display: 60% of the width.
LEFT, TOP, RIGHT, BOTTOM = 0.2, 0.25, 0.8, 0.75
MAX_X, MAX_Y = DISPLAY[0] - 1, DISPLAY[1] - 1


class FakeOutput:
    def __init__(self) -> None:
        self.moves: list[Point] = []

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


def pointer_at(x: float, y: float) -> Landmarks:
    hand = list(pointing_hand())
    hand[POINTER] = (x, y)
    return hand


class Rig:
    """An absolute-mode controller on a 1600x1000 display, fed at 30 fps; active unless told
    otherwise."""

    def __init__(self, config: Config | None = None, *, active: bool = True) -> None:
        config = config or ABSOLUTE
        self.output = FakeOutput()
        self.controller = Controller(config.timing, self.output, make_cursor_path(config, DISPLAY))
        self.time = 0.0
        if active:
            self.feed(1.0, open_hand())
            assert self.controller.state is State.ACTIVE
            self.output.moves.clear()

    def feed(self, seconds: float, landmarks: Landmarks | None) -> None:
        for _ in range(round(seconds / FRAME_S)):
            self.frame(landmarks)

    def frame(self, landmarks: Landmarks | None) -> None:
        self.controller.update(self.time, landmarks)
        self.time += FRAME_S

    @property
    def last(self) -> Point:
        return self.output.moves[-1]


@pytest.mark.parametrize(
    ("pointer", "expected"),
    [
        ((LEFT, TOP), (0, 0)),
        ((RIGHT, TOP), (MAX_X, 0)),
        ((LEFT, BOTTOM), (0, MAX_Y)),
        ((RIGHT, BOTTOM), (MAX_X, MAX_Y)),
        ((0.5, 0.5), (MAX_X / 2, MAX_Y / 2)),
        ((0.5, TOP), (MAX_X / 2, 0)),
        ((LEFT, 0.5), (0, MAX_Y / 2)),
        ((0.35, 0.4), (MAX_X * 0.25, MAX_Y * 0.3)),
    ],
)
def test_the_active_region_maps_to_the_whole_display(pointer: Point, expected: Point) -> None:
    rig = Rig()

    rig.frame(pointer_at(*pointer))

    assert rig.last == pytest.approx(expected)


@pytest.mark.parametrize(
    ("pointer", "expected"),
    [
        ((0.0, 0.0), (0, 0)),
        ((1.0, 1.0), (MAX_X, MAX_Y)),
        ((0.95, 0.5), (MAX_X, MAX_Y / 2)),
        ((0.5, 0.05), (MAX_X / 2, 0)),
        ((0.1, 0.9), (0, MAX_Y)),
    ],
)
def test_a_pointer_outside_the_region_clamps_to_the_nearest_edge(
    pointer: Point, expected: Point
) -> None:
    rig = Rig()

    rig.frame(pointer_at(*pointer))

    assert rig.last == pytest.approx(expected)


def test_the_cursor_never_leaves_the_display_while_the_pointer_sweeps_across_the_frame() -> None:
    rig = Rig()

    for step in range(31):
        rig.frame(pointer_at(step / 30, 1 - step / 30))

    assert all(0 <= x <= MAX_X and 0 <= y <= MAX_Y for x, y in rig.output.moves)


def test_the_region_takes_the_shape_of_the_display() -> None:
    mapping = make_mapping(Config(), (1000.0, 1000.0))  # a square display: region 0.6 x 0.8

    assert mapping.to_screen((0.2, 0.1)) == pytest.approx((0, 0))
    assert mapping.to_screen((0.8, 0.9)) == pytest.approx((999, 999))


def test_a_rotated_camera_places_the_region_in_the_rotated_frame() -> None:
    config = Config(camera=dataclasses.replace(Config().camera, rotate=90))
    mapping = make_mapping(config, DISPLAY)  # frame 480x640: region 0.6 wide, 0.3 tall

    assert mapping.to_screen((0.2, 0.35)) == pytest.approx((0, 0))
    assert mapping.to_screen((0.8, 0.65)) == pytest.approx((MAX_X, MAX_Y))


def test_mirror_and_rotate_turn_a_raw_point_into_the_direction_the_hand_moved() -> None:
    mapping = make_mapping(Config(), DISPLAY)

    # Mirrored, a hand at the camera's left is at the user's right.
    x_left = mapping.to_screen(prepare_point((0.3, 0.5), 0, True))[0]
    x_right = mapping.to_screen(prepare_point((0.7, 0.5), 0, True))[0]
    assert x_left > x_right
    # Rotated a quarter turn, a raw point lower in the frame lands further left.
    up = mapping.to_screen(prepare_point((0.5, 0.3), 90, False))[0]
    down = mapping.to_screen(prepare_point((0.5, 0.7), 90, False))[0]
    assert down < up


def test_no_input_while_paused() -> None:
    rig = Rig(active=False)

    rig.feed(1.0, pointer_at(0.5, 0.5))

    assert rig.controller.state is State.PAUSED
    assert rig.output.moves == []


def test_no_input_after_pausing_with_the_open_palm() -> None:
    rig = Rig()
    rig.feed(0.1, pointer_at(0.5, 0.5))  # the Hand leaves the pose that unpaused
    rig.feed(0.5, open_hand())
    assert rig.controller.state is State.PAUSED
    rig.output.moves.clear()

    rig.feed(1.0, pointer_at(0.4, 0.4))

    assert rig.output.moves == []


def test_the_open_palm_that_unpauses_does_not_move_the_cursor() -> None:
    rig = Rig(active=False)

    rig.feed(1.5, open_hand())

    assert rig.controller.state is State.ACTIVE
    assert rig.output.moves == []


def test_no_input_without_a_hand() -> None:
    rig = Rig()

    rig.feed(1.0, None)

    assert rig.output.moves == []


def test_a_pointer_that_reappears_elsewhere_starts_there_without_gliding() -> None:
    rig = Rig()
    rig.feed(0.5, pointer_at(LEFT, TOP))
    rig.feed(0.5, None)

    rig.frame(pointer_at(RIGHT, BOTTOM))

    assert rig.last == pytest.approx((MAX_X, MAX_Y))


def test_the_cursor_is_steady_when_the_hand_is_still_but_jittery() -> None:
    rig = Rig()
    jitters = [0.002 if step % 2 else -0.002 for step in range(60)]  # about 4 px of jitter
    for jitter in jitters:
        rig.frame(pointer_at(0.5 + jitter, 0.5))

    settled = [x for x, _ in rig.output.moves[30:]]
    raw_span = (max(jitters) - min(jitters)) / (RIGHT - LEFT) * MAX_X
    assert max(settled) - min(settled) < raw_span / 4


def test_the_cursor_keeps_up_with_a_fast_move() -> None:
    gaps = []
    for beta in (0.007, 0.0):
        rig = Rig(dataclasses.replace(ABSOLUTE, filter=FilterConfig(min_cutoff=1.0, beta=beta)))
        rig.feed(0.5, pointer_at(LEFT, 0.5))
        for step in range(1, 7):  # LEFT to RIGHT in 0.2 s
            rig.frame(pointer_at(LEFT + (RIGHT - LEFT) * step / 6, 0.5))
        gaps.append(MAX_X - rig.last[0])

    with_beta, without_beta = gaps
    assert with_beta < 0.3 * MAX_X
    assert with_beta < without_beta / 2


def test_the_cursor_reaches_the_target_once_the_pointer_settles() -> None:
    rig = Rig()
    rig.feed(0.3, pointer_at(LEFT, 0.5))

    rig.feed(2.0, pointer_at(RIGHT, 0.5))

    assert rig.last[0] == pytest.approx(MAX_X, abs=2)


def test_an_unknown_control_mode_is_an_error_listing_the_valid_ones() -> None:
    config = Config(control=ControlConfig(mode="joystick"))  # past the config check

    with pytest.raises(ConfigError, match="control.mode.*joystick.*relative, absolute"):
        make_cursor_path(config, DISPLAY)


def test_each_control_mode_gets_its_own_cursor_path() -> None:
    assert isinstance(make_cursor_path(ABSOLUTE, DISPLAY), AbsolutePath)
    assert isinstance(make_cursor_path(Config(), DISPLAY), RelativePath)


def test_a_close_fingered_open_hand_never_moves_the_cursor() -> None:
    rig = Rig()
    rig.feed(FRAME_S, pointer_at(0.5, 0.5))  # the Hand leaves the pose that unpaused
    rig.output.moves.clear()

    for frame in range(30):
        rig.frame(synthetic_hand("open together", jitter=0.003, seed=frame))

    assert rig.controller.state is State.PAUSED
    assert rig.output.moves == []


def test_a_close_fingered_open_hand_unpauses_without_moving_the_cursor() -> None:
    rig = Rig(active=False)

    for frame in range(45):
        rig.frame(synthetic_hand("open together", jitter=0.003, seed=frame))

    assert rig.controller.state is State.ACTIVE
    assert rig.output.moves == []


def test_a_real_pointing_hand_moves_the_cursor_and_is_not_an_open_palm() -> None:
    rig = Rig()
    rig.feed(FRAME_S, None)

    for frame in range(30):
        rig.frame(synthetic_hand("pointing relaxed", jitter=0.003, seed=frame))

    assert rig.controller.state is State.ACTIVE
    assert len(rig.output.moves) == 30
    assert all(0 <= x <= MAX_X and 0 <= y <= MAX_Y for x, y in rig.output.moves)
