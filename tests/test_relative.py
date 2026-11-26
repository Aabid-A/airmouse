"""Relative control mode, the RelativePath on its own: deltas, gain, displays, resets."""

import math

import pytest

from airmouse.config import Config, RelativeConfig
from airmouse.displays import Display
from airmouse.gestures import POINTER, Landmarks, Point, hand_size
from airmouse.mapping import RelativePath, make_cursor_path
from anatomy import closing_fist
from hands import placed, pointing_hand

FRAME_S = 1 / 30
ASPECT = 640 / 480
MAIN = Display(0, 0, 1440, 900)
RIGHT = Display(1440, -180, 1920, 1080)
HAND = pointing_hand()
SIZE = hand_size(HAND)  # the pointing Hand's size; its wrist and middle base are level


class FakeScreen:
    """Displays and a cursor position that a test can change; counts the display reads."""

    def __init__(self, displays: tuple[Display, ...] = (MAIN,), cursor: Point | None = None):
        self.list = displays
        self.cursor = cursor
        self.reads = 0

    def displays(self) -> tuple[Display, ...]:
        self.reads += 1
        return self.list

    def cursor_position(self) -> Point | None:
        return self.cursor


def make_path(
    screen: FakeScreen,
    *,
    gain: float = 1000.0,
    acceleration: float = 0.0,
    max_gain: float = 50000.0,
) -> RelativePath:
    """A RelativePath with the filter all but switched off, so deltas can be checked exactly."""
    return RelativePath(
        RelativeConfig(gain=gain, acceleration=acceleration, max_gain=max_gain),
        screen,
        frame_aspect=ASPECT,
        min_cutoff=1e9,
        beta=0.0,
        fallback=(MAIN,),
    )


class Feed:
    """Feeds a RelativePath one frame at a time at 30 fps."""

    def __init__(self, path: RelativePath) -> None:
        self.path = path
        self.frame = 0

    def __call__(self, landmarks: Landmarks) -> Point:
        position = self.path.position(self.frame * FRAME_S, landmarks)
        self.frame += 1
        return position


def test_the_first_frame_moves_nothing_and_starts_where_the_cursor_is() -> None:
    feed = Feed(make_path(FakeScreen(cursor=(300.0, 200.0))))

    assert feed(placed(HAND, dx=0.3)) == (300.0, 200.0)  # wherever the Hand is


def test_a_cursor_position_that_cannot_be_read_starts_at_the_main_display_centre() -> None:
    feed = Feed(make_path(FakeScreen((Display(-1920, 0, 1920, 1080), MAIN))))

    assert feed(HAND) == MAIN.centre


def test_the_cursor_moves_by_the_pointer_delta_in_hand_sizes_times_the_gain() -> None:
    feed = Feed(make_path(FakeScreen(cursor=(700.0, 400.0)), gain=1000.0))
    feed(HAND)

    moved = feed(placed(HAND, dx=0.03, dy=-0.02))

    expected = (700 + 0.03 * ASPECT / SIZE * 1000, 400 - 0.02 / SIZE * 1000)
    assert moved == pytest.approx(expected)


def test_the_same_movement_moves_the_cursor_the_same_near_or_far_from_the_camera() -> None:
    near, far = (Feed(make_path(FakeScreen(cursor=(700.0, 400.0)))) for _ in range(2))
    near(placed(HAND, scale=1.5))
    far(placed(HAND, scale=0.75))

    # The same hand movement looks twice as large to the camera when the Hand is twice as big.
    a = near(placed(HAND, scale=1.5, dx=0.03))
    b = far(placed(HAND, scale=0.75, dx=0.015))

    assert a == pytest.approx(b)


def test_sideways_and_upward_movements_of_the_same_size_move_the_cursor_the_same() -> None:
    sideways, upward = (Feed(make_path(FakeScreen(cursor=(700.0, 400.0)))) for _ in range(2))
    sideways(HAND)
    upward(HAND)

    across = sideways(placed(HAND, dx=0.03 / ASPECT))[0] - 700  # 0.03 frame heights
    up = 400 - upward(placed(HAND, dy=-0.03))[1]

    assert across == pytest.approx(up)


def test_acceleration_adds_gain_with_speed_up_to_the_cap() -> None:
    path = make_path(FakeScreen(), gain=800.0, acceleration=0.5, max_gain=2000.0)

    assert path.gain(0.0) == 800.0
    assert path.gain(1.0) == 1200.0
    assert path.gain(2.0) == 1600.0
    assert path.gain(10.0) == 2000.0  # capped


def test_a_fast_movement_goes_further_than_the_same_movement_made_slowly() -> None:
    def travel(frames: int) -> float:
        feed = Feed(make_path(FakeScreen(cursor=(100.0, 400.0)), acceleration=0.5))
        feed(HAND)
        x = 0.0
        for frame in range(1, frames + 1):
            x = feed(placed(HAND, dx=0.06 * frame / frames))[0]
        return x - 100

    assert travel(2) > 1.5 * travel(12)


def test_with_no_acceleration_speed_changes_nothing() -> None:
    def travel(frames: int) -> float:
        feed = Feed(make_path(FakeScreen(cursor=(100.0, 400.0))))
        feed(HAND)
        x = 0.0
        for frame in range(1, frames + 1):
            x = feed(placed(HAND, dx=0.06 * frame / frames))[0]
        return x - 100

    assert travel(2) == pytest.approx(travel(12))


def test_bending_the_index_finger_barely_moves_the_cursor() -> None:
    """Closing a fist moves the fingertip towards the palm; that alone is not aiming."""
    feed = Feed(make_path(FakeScreen(cursor=(700.0, 400.0))))
    feed(closing_fist(0.0))

    bent = feed(closing_fist(0.3))

    tip_travel = math.dist(closing_fist(0.0)[POINTER], closing_fist(0.3)[POINTER])
    as_a_hand_movement = tip_travel / hand_size(closing_fist(0.0)) * 1000
    assert as_a_hand_movement > 200  # the fingertip really moved
    assert math.dist(bent, (700.0, 400.0)) < 0.1 * as_a_hand_movement


def test_after_a_reset_the_first_frame_moves_nothing_and_starts_from_the_real_cursor() -> None:
    screen = FakeScreen(cursor=(700.0, 400.0))
    feed = Feed(make_path(screen))
    feed(HAND)
    feed(placed(HAND, dx=0.02))
    feed.path.reset()
    screen.cursor = (50.0, 60.0)  # the user moved the real mouse meanwhile

    assert feed(placed(HAND, dx=0.3, dy=0.1)) == (50.0, 60.0)
    assert feed(placed(HAND, dx=0.31, dy=0.1))[0] > 50.0  # and follows on from there


def test_the_cursor_crosses_onto_the_next_display() -> None:
    feed = Feed(make_path(FakeScreen((MAIN, RIGHT), cursor=(1400.0, 300.0))))
    feed(HAND)

    x, y = feed(placed(HAND, dx=0.02))

    assert x > 1440 and y == pytest.approx(300.0)


def test_a_move_off_the_displays_slides_along_the_edge() -> None:
    feed = Feed(make_path(FakeScreen(cursor=(700.0, 890.0))))
    feed(HAND)

    x, y = feed(placed(HAND, dx=0.02, dy=0.1))  # down and right, far past the bottom

    assert y == 899
    assert x == pytest.approx(700 + 0.02 * ASPECT / SIZE * 1000)


def test_the_display_list_is_read_about_once_a_second() -> None:
    screen = FakeScreen()
    feed = Feed(make_path(screen))

    for _ in range(30):  # 1 s at 30 fps
        feed(HAND)
    assert screen.reads == 1
    feed(HAND)
    assert screen.reads == 2


def test_a_display_unplugged_under_the_cursor_moves_it_to_the_nearest_remaining_one() -> None:
    screen = FakeScreen((MAIN, RIGHT), cursor=(2500.0, -100.0))  # on the right display
    feed = Feed(make_path(screen))
    feed(HAND)
    assert feed(HAND) == (2500.0, -100.0)

    screen.list = (MAIN,)
    positions = [feed(HAND) for _ in range(30)]
    position = positions[-1]

    assert position == (1439, 0)
    assert feed.path.displays == (MAIN,)


def test_a_display_added_while_running_becomes_reachable() -> None:
    screen = FakeScreen((MAIN,), cursor=(1430.0, 300.0))
    feed = Feed(make_path(screen))
    feed(HAND)
    assert feed(placed(HAND, dx=0.02))[0] == 1439  # the edge of the only display

    screen.list = (MAIN, RIGHT)
    for _ in range(30):
        feed(placed(HAND, dx=0.02))

    assert feed(placed(HAND, dx=0.04))[0] > 1440


def test_an_unreadable_display_list_keeps_the_last_one() -> None:
    screen = FakeScreen((MAIN, RIGHT), cursor=(2500.0, -100.0))
    feed = Feed(make_path(screen))
    feed(HAND)

    screen.list = ()
    positions = [feed(HAND) for _ in range(31)]
    position = positions[-1]

    assert position == (2500.0, -100.0)
    assert feed.path.displays == (MAIN, RIGHT)


def test_a_cursor_reported_outside_every_display_is_clamped_in() -> None:
    feed = Feed(make_path(FakeScreen(cursor=(-40.0, 1000.0))))

    assert feed(HAND) == (0, 899)


def test_the_default_config_builds_a_relative_path_on_the_main_display() -> None:
    path = make_cursor_path(Config(), (1440.0, 900.0))

    assert isinstance(path, RelativePath)
    assert path.displays == (MAIN,)
