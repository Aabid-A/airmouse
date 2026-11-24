"""Synthetic Hands for tests: 21 normalised landmarks, never recorded from a camera."""

from airmouse.gestures import Landmarks, Point

# Index 0 is the wrist, then thumb (1-4), index (5-8), middle (9-12), ring (13-16), little (17-20).
_OPEN: list[Point] = [
    (0.50, 0.86),
    (0.43, 0.80), (0.37, 0.73), (0.31, 0.67), (0.25, 0.62),
    (0.42, 0.66), (0.40, 0.55), (0.39, 0.47), (0.38, 0.40),
    (0.50, 0.64), (0.50, 0.52), (0.50, 0.43), (0.50, 0.35),
    (0.58, 0.66), (0.60, 0.56), (0.61, 0.48), (0.62, 0.41),
    (0.65, 0.70), (0.68, 0.62), (0.70, 0.56), (0.72, 0.50),
]  # fmt: skip

_POINTING: list[Point] = [
    (0.50, 0.86),
    (0.43, 0.80), (0.38, 0.74), (0.40, 0.68), (0.45, 0.66),
    (0.42, 0.66), (0.41, 0.54), (0.405, 0.45), (0.40, 0.37),
    (0.50, 0.64), (0.50, 0.55), (0.50, 0.61), (0.50, 0.68),
    (0.58, 0.66), (0.59, 0.58), (0.58, 0.64), (0.57, 0.70),
    (0.65, 0.70), (0.67, 0.64), (0.65, 0.69), (0.63, 0.73),
]  # fmt: skip


def open_hand() -> Landmarks:
    return list(_OPEN)


def pointing_hand() -> Landmarks:
    return list(_POINTING)


def placed(hand: Landmarks, *, dx: float = 0.0, dy: float = 0.0, scale: float = 1.0) -> Landmarks:
    """The Hand scaled about its wrist (a larger scale looks nearer), then shifted."""
    wx, wy = hand[0]
    return [(wx + (x - wx) * scale + dx, wy + (y - wy) * scale + dy) for x, y in hand]
