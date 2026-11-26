"""Display geometry: the union of the display rectangles and the clamp into it."""

import pytest

from airmouse.displays import Display, FixedScreen, clamp_to_displays, main_display
from airmouse.gestures import Point

MAIN = Display(0, 0, 1440, 900)  # a 1440x900-point laptop screen, the main display


def test_a_display_covers_whole_points_from_its_origin() -> None:
    assert (MAIN.right, MAIN.bottom) == (1439, 899)
    assert MAIN.centre == (719.5, 449.5)


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        ((100, 200), (100, 200)),  # inside: unchanged
        ((1439, 899), (1439, 899)),  # the last point is inside
        ((-50, 300), (0, 300)),  # off the left edge: slides along it
        ((700, 2000), (700, 899)),  # off the bottom
        ((5000, -5000), (1439, 0)),  # off a corner: the corner
    ],
)
def test_a_single_display_clamps_to_its_nearest_point(point: Point, expected: Point) -> None:
    assert clamp_to_displays(point, (MAIN,)) == expected


SIDE_BY_SIDE = (MAIN, Display(1440, -180, 1920, 1080))  # a taller external display to the right
STACKED = (MAIN, Display(-240, -1080, 1920, 1080))  # an external display above, wider
OFFSET = (MAIN, Display(1440, 300, 1280, 800))  # to the right, lower down
GAP = (MAIN, Display(1500, 900, 1920, 1080))  # diagonal below right, 60 points apart
LEFT = (Display(-1920, -100, 1920, 1080), MAIN)  # to the left: negative coordinates


@pytest.mark.parametrize(
    ("displays", "point", "expected"),
    [
        # Side by side, different heights: crossing at a shared height lands on the other.
        (SIDE_BY_SIDE, (1500, 100), (1500, 100)),
        # Above the laptop's top edge but within the taller display: allowed.
        (SIDE_BY_SIDE, (1500, -150), (1500, -150)),
        # Moving left from the tall display above the laptop: slides down its left edge.
        (SIDE_BY_SIDE, (1400, -150), (1440, -150)),
        # Stacked: moving up off the laptop enters the display above.
        (STACKED, (720, -50), (720, -50)),
        (STACKED, (-300, -500), (-240, -500)),
        # Offset vertically: the lower display is reachable where they overlap only.
        (OFFSET, (1500, 850), (1500, 850)),
        (OFFSET, (1500, 100), (1439, 100)),
        # A gap between diagonal displays: a point in the gap goes to the nearer display.
        (GAP, (1470, 950), (1500, 950)),
        (GAP, (1460, 905), (1439, 899)),
        # A display at negative coordinates.
        (LEFT, (-5, 500), (-5, 500)),
        (LEFT, (-2500, 500), (-1920, 500)),
        (LEFT, (-1000, -400), (-1000, -100)),
    ],
)
def test_the_union_of_displays_clamps_to_its_nearest_point(
    displays: tuple[Display, ...], point: Point, expected: Point
) -> None:
    assert clamp_to_displays(point, displays) == expected


def test_a_point_inside_any_display_is_never_moved() -> None:
    for displays in (SIDE_BY_SIDE, STACKED, OFFSET, GAP, LEFT):
        for display in displays:
            assert clamp_to_displays(display.centre, displays) == display.centre


def test_with_no_displays_there_is_nothing_to_clamp_to() -> None:
    assert clamp_to_displays((12.5, -3), ()) == (12.5, -3)


def test_the_main_display_is_the_one_at_the_origin() -> None:
    assert main_display(LEFT) == MAIN
    assert main_display((Display(10, 10, 100, 100),)) == Display(10, 10, 100, 100)
    assert main_display(()) is None


def test_a_fixed_screen_is_one_display_at_the_origin_with_no_cursor_reading() -> None:
    screen = FixedScreen((1440.0, 900.0))

    assert screen.displays() == (MAIN,)
    assert screen.cursor_position() is None
