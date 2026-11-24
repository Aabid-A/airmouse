import itertools

import numpy as np
import pytest

from airmouse.config import ROTATIONS
from airmouse.frame import active_region, prepare_frame, prepare_point

COMBINATIONS = list(itertools.product(ROTATIONS, (False, True)))
HEIGHT, WIDTH = 4, 6  # not square, so a wrong turn changes the shape


def marked_frame(row: int, column: int) -> np.ndarray:
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    frame[row, column] = (255, 255, 255)
    return frame


def marker_centre(frame: np.ndarray) -> tuple[float, float]:
    """The normalised centre of the one lit pixel."""
    rows, columns = np.nonzero(frame[:, :, 0])
    height, width = frame.shape[:2]
    return ((columns[0] + 0.5) / width, (rows[0] + 0.5) / height)


@pytest.mark.parametrize(("rotate", "mirror"), COMBINATIONS)
def test_the_frame_and_a_point_are_prepared_the_same_way(rotate: int, mirror: bool) -> None:
    for row, column in [(0, 0), (0, 5), (3, 0), (1, 4), (2, 2)]:
        point = ((column + 0.5) / WIDTH, (row + 0.5) / HEIGHT)

        prepared = prepare_frame(marked_frame(row, column), rotate, mirror)

        expected = marker_centre(prepared)
        actual = prepare_point(point, rotate, mirror)
        assert actual == pytest.approx(expected)


@pytest.mark.parametrize(
    ("rotate", "mirror", "expected_point"),
    [
        (0, False, (0.9, 0.2)),  # right and up stay right and up
        (0, True, (0.1, 0.2)),
        (90, False, (0.8, 0.9)),  # a quarter turn clockwise: up goes right, right goes down
        (90, True, (0.2, 0.9)),
        (180, False, (0.1, 0.8)),
        (180, True, (0.9, 0.8)),
        (270, False, (0.2, 0.1)),
        (270, True, (0.8, 0.1)),
    ],
)
def test_every_rotate_and_mirror_on_a_known_point(
    rotate: int, mirror: bool, expected_point: tuple[float, float]
) -> None:
    assert prepare_point((0.9, 0.2), rotate, mirror) == pytest.approx(expected_point)


@pytest.mark.parametrize(("rotate", "mirror"), COMBINATIONS)
def test_the_frame_shape_swaps_only_for_quarter_turns(rotate: int, mirror: bool) -> None:
    prepared = prepare_frame(marked_frame(0, 0), rotate, mirror)

    expected = (WIDTH, HEIGHT, 3) if rotate in (90, 270) else (HEIGHT, WIDTH, 3)
    assert prepared.shape == expected
    assert prepared.flags["C_CONTIGUOUS"]


def test_mirror_alone_flips_left_to_right() -> None:
    assert prepare_point((0.25, 0.4), 0, True) == pytest.approx((0.75, 0.4))


def test_the_default_active_region_is_centred_with_the_screen_shape() -> None:
    left, top, right, bottom = active_region(640, 480, 0.6, 16 / 10)

    assert (left, right) == pytest.approx((0.2, 0.8))
    assert (left + right) / 2 == pytest.approx(0.5)
    assert (top + bottom) / 2 == pytest.approx(0.5)
    assert (right - left) * 640 / ((bottom - top) * 480) == pytest.approx(16 / 10)


def test_the_active_region_never_leaves_the_frame() -> None:
    left, top, right, bottom = active_region(640, 480, 1.0, 16 / 10)

    assert 0 <= left < right <= 1
    assert 0 <= top < bottom <= 1
    assert right - left <= 1


def test_the_active_region_follows_the_prepared_frame_size() -> None:
    portrait = active_region(480, 640, 0.6, 16 / 10)

    assert portrait[2] - portrait[0] == pytest.approx(0.6)
    assert portrait[3] - portrait[1] < 0.6
