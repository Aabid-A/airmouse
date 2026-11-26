"""Relative control mode, the RelativePath on its own: deltas, gain, displays, resets."""

import math
from collections.abc import Callable

import pytest

from airmouse.config import Config, RelativeConfig
from airmouse.displays import Display, to_point
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
    max_gain: float | None = None,
) -> RelativePath:
    """A RelativePath with the filter all but switched off, so deltas can be checked exactly.

    With no `max_gain` the gain is `gain` at every speed."""
    return RelativePath(
        RelativeConfig(gain=gain, max_gain=gain if max_gain is None else max_gain),
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
    assert moved == to_point(expected)  # posted at the whole point under the cursor


def test_the_same_movement_moves_the_cursor_the_same_near_or_far_from_the_camera() -> None:
    near, far = (Feed(make_path(FakeScreen(cursor=(700.0, 400.0)))) for _ in range(2))
    near(placed(HAND, scale=1.5))
    far(placed(HAND, scale=0.75))

    # The same hand movement looks twice as large to the camera when the Hand is twice as big.
    a = near(placed(HAND, scale=1.5, dx=0.03))
    b = far(placed(HAND, scale=0.75, dx=0.015))

    assert a == pytest.approx(b, abs=1)


def test_sideways_and_upward_movements_of_the_same_size_move_the_cursor_the_same() -> None:
    sideways, upward = (Feed(make_path(FakeScreen(cursor=(700.0, 400.0)))) for _ in range(2))
    sideways(HAND)
    upward(HAND)

    across = sideways(placed(HAND, dx=0.03 / ASPECT))[0] - 700  # 0.03 frame heights
    up = 400 - upward(placed(HAND, dy=-0.03))[1]

    assert across == pytest.approx(up, abs=1)


def test_a_fast_movement_goes_further_than_the_same_movement_made_slowly() -> None:
    def travel(frames: int) -> float:
        feed = Feed(make_path(FakeScreen(cursor=(100.0, 400.0)), max_gain=3000.0))
        feed(HAND)
        x = 0.0
        for frame in range(1, frames + 1):
            x = feed(placed(HAND, dx=0.06 * frame / frames))[0]
        return x - 100

    assert travel(2) > 1.5 * travel(12)


def test_with_max_gain_equal_to_gain_speed_changes_nothing() -> None:
    def travel(frames: int) -> float:
        feed = Feed(make_path(FakeScreen(cursor=(100.0, 400.0))))
        feed(HAND)
        x = 0.0
        for frame in range(1, frames + 1):
            x = feed(placed(HAND, dx=0.06 * frame / frames))[0]
        return x - 100

    assert travel(2) == pytest.approx(travel(12), abs=1)


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
    assert x == math.floor(700 + 0.02 * ASPECT / SIZE * 1000)


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


# Slow movement must add up and cross a seam, even under half a point per frame.
STEP = 0.4 / (ASPECT / SIZE * 1000)  # a sideways hand step that moves the cursor 0.4 points
ABOVE = Display(-240, -1080, 1920, 1080)  # stacked above MAIN
LOWER_RIGHT = Display(1440, 300, 1280, 800)  # to the right, offset downwards


def on_a_display(point: Point, displays: tuple[Display, ...]) -> bool:
    return any(display.contains(point) for display in displays)


@pytest.mark.parametrize(
    ("displays", "start", "step", "crossed"),
    [
        ((MAIN, RIGHT), (1430.0, 300.0), (STEP, 0.0), lambda p: p[0] >= 1440),
        ((MAIN, ABOVE), (700.0, 10.0), (0.0, -STEP * ASPECT), lambda p: p[1] < 0),
        ((MAIN, LOWER_RIGHT), (1430.0, 600.0), (STEP, 0.0), lambda p: p[0] >= 1440),
    ],
    ids=["side by side", "stacked", "offset"],
)
def test_movement_under_half_a_point_a_frame_still_crosses_a_seam(
    displays: tuple[Display, ...], start: Point, step: Point, crossed: Callable[[Point], bool]
) -> None:
    feed = Feed(make_path(FakeScreen(displays, cursor=start)))
    positions = [feed(placed(HAND, dx=step[0] * frame, dy=step[1] * frame)) for frame in range(101)]

    assert crossed(positions[-1])
    assert all(on_a_display(p, displays) for p in positions)  # every posted point
    moves = [math.dist(a, b) for a, b in zip(positions, positions[1:], strict=False)]
    assert max(moves) <= 1.0  # one whole point at a time: no jump at the seam


def test_a_cursor_pushed_against_the_outer_edge_stays_on_the_display() -> None:
    feed = Feed(make_path(FakeScreen((MAIN, RIGHT), cursor=(3350.0, 500.0))))

    positions = [feed(placed(HAND, dx=STEP * 50 * frame)) for frame in range(20)]

    assert all(on_a_display(p, (MAIN, RIGHT)) for p in positions)
    assert positions[-1][0] == RIGHT.right - 1


# --- speed-dependent gain and slow-speed smoothing (the default [relative] settings) ---

DEFAULTS = RelativeConfig()
WIDE = Display(0, 0, 100000, 900)  # room to travel far without meeting an edge


def default_path(screen: FakeScreen, config: RelativeConfig = DEFAULTS) -> RelativePath:
    """A RelativePath with `config`'s gain curve and its own smoothing, as the app builds it."""
    return RelativePath(
        config,
        screen,
        frame_aspect=ASPECT,
        min_cutoff=config.min_cutoff,
        beta=config.beta,
        fallback=(MAIN,),
    )


def test_the_gain_is_low_when_slow_high_when_fast_and_capped() -> None:
    path = default_path(FakeScreen())

    assert path.gain(0.0) == path.gain(DEFAULTS.slow_speed) == DEFAULTS.gain
    assert path.gain(DEFAULTS.fast_speed) == path.gain(100.0) == DEFAULTS.max_gain
    middle = path.gain((DEFAULTS.slow_speed + DEFAULTS.fast_speed) / 2)
    assert middle == pytest.approx((DEFAULTS.gain + DEFAULTS.max_gain) / 2)


def test_the_gain_rises_monotonically_with_no_steps() -> None:
    path = default_path(FakeScreen())
    speeds = [step / 1000 for step in range(10001)]  # 0 to 10 hand sizes per second
    gains = [path.gain(speed) for speed in speeds]

    steps = [b - a for a, b in zip(gains, gains[1:], strict=False)]
    assert min(steps) >= 0  # never falls
    assert max(steps) < 2.0  # 1 ms of speed never adds more than 2 points per hand size
    assert max(gains) == DEFAULTS.max_gain  # capped


def test_the_gain_has_no_kink_where_the_slow_and_fast_regions_meet_the_curve() -> None:
    path = default_path(FakeScreen())
    tiny = 1e-4

    for edge in (DEFAULTS.slow_speed, DEFAULTS.fast_speed):
        slope_below = (path.gain(edge) - path.gain(edge - tiny)) / tiny
        slope_above = (path.gain(edge + tiny) - path.gain(edge)) / tiny
        assert slope_below == pytest.approx(slope_above, abs=1.0)


def lag_seconds(speed: float) -> float:
    """How far behind the hand the cursor runs, in seconds, at a steady `speed` (hand sizes
    per second), with the default smoothing and a constant gain so only the filter shows."""
    config = RelativeConfig(gain=1000.0, max_gain=1000.0)
    feed = Feed(default_path(FakeScreen((WIDE,), cursor=(100.0, 400.0)), config))
    step = speed * FRAME_S * SIZE / ASPECT  # sideways, in frame widths per frame
    frames = 90
    x = 0.0
    for frame in range(frames + 1):
        x = feed(placed(HAND, dx=step * frame))[0]
    unsmoothed = speed * frames * FRAME_S * config.gain
    return (unsmoothed - (x - 100)) / (speed * config.gain)


def test_smoothing_is_stronger_when_the_hand_is_slow_than_when_it_is_fast() -> None:
    slow, fast = lag_seconds(0.1), lag_seconds(3.0)

    assert slow > 0.06  # a slow hand is smoothed hard: tremor stays off the cursor
    assert fast < 0.02  # a fast hand is barely smoothed: no lag
    assert slow > 5 * fast


def test_the_same_movement_goes_the_same_distance_near_or_far_with_the_default_settings() -> None:
    """Gain and smoothing both count speed in hand sizes, so distance changes neither."""
    near, far = (Feed(default_path(FakeScreen((WIDE,), cursor=(100.0, 400.0)))) for _ in range(2))
    shifts = [0.01 * min(frame, 15) for frame in range(46)]  # a fast move for 0.5 s, then still
    nears = [near(placed(HAND, scale=1.5, dx=shift)) for shift in shifts]
    fars = [far(placed(HAND, scale=0.75, dx=shift / 2)) for shift in shifts]

    for a, b in zip(nears, fars, strict=True):
        assert a == pytest.approx(b, abs=1)
    moved = 0.15 * ASPECT / hand_size(placed(HAND, scale=1.5))  # hand sizes
    assert nears[-1][0] - 100 > 2 * moved * DEFAULTS.gain  # well above the slow gain


def tremor(frame: int) -> float:
    """A small, fast shake, as frame heights: about 2% of a hand size at 10 Hz."""
    return 0.02 * SIZE * math.sin(2 * math.pi * 10 * frame * FRAME_S + 0.3)


def test_a_slow_small_move_gives_a_small_smooth_cursor_path() -> None:
    """A tenth of a hand size over a second, with tremor, moves the cursor a little and
    steadily: no shake back and forth, no jumps."""
    feed = Feed(default_path(FakeScreen(cursor=(700.0, 400.0))))
    distance = 0.1 * SIZE / ASPECT  # sideways, in frame widths
    positions = [
        feed(placed(HAND, dx=distance * min(frame, 30) / 30, dy=tremor(frame)))
        for frame in range(46)
    ]

    xs = [x for x, _ in positions]
    ys = [y for _, y in positions]
    travelled = xs[-1] - 700
    assert 0.5 * 0.1 * DEFAULTS.gain < travelled <= 0.1 * DEFAULTS.gain + 1  # about gain's worth
    assert all(b >= a for a, b in zip(xs, xs[1:], strict=False))  # never backwards
    assert max(b - a for a, b in zip(xs, xs[1:], strict=False)) <= 3  # small steps
    assert max(ys) - min(ys) <= 5  # the tremor barely shows


def test_the_first_frame_after_a_reset_moves_nothing_with_the_default_settings() -> None:
    screen = FakeScreen(cursor=(700.0, 400.0))
    feed = Feed(default_path(screen))
    for frame in range(10):
        feed(placed(HAND, dx=0.02 * frame))  # a fast move
    feed.path.reset()  # a clutch or No hand
    screen.cursor = (300.0, 200.0)

    assert feed(placed(HAND, dx=-0.2, dy=0.1)) == (300.0, 200.0)
    assert feed(placed(HAND, dx=-0.2, dy=0.1)) == (300.0, 200.0)  # a still hand stays still
