"""Frame preparation: rotate, then mirror, so the Hand reads the way the user moves it.

This is the one place rotate and mirror are defined. `prepare_frame` turns a
camera frame into the prepared frame the tracker and the Preview see.
`prepare_point` is the same transform on one normalised point, for anything
that holds raw-frame coordinates (the cursor mapping will reuse it). A test
proves the two agree, so they cannot drift. The Active region is placed in the
prepared frame, after this step.
"""

from typing import Any

import numpy as np

from airmouse.gestures import Point

type Frame = Any  # an RGB numpy array, shape (height, width, 3), dtype uint8
type Region = tuple[float, float, float, float]  # left, top, right, bottom, each 0 to 1

# A MacBook screen is 16:10. airmouse does not read the display size yet.
DEFAULT_SCREEN_ASPECT = 16 / 10


def prepare_frame(frame: Frame, rotate: int, mirror: bool) -> Frame:
    """Rotate clockwise by `rotate` degrees (0, 90, 180, 270), then mirror left to right."""
    turns = (rotate // 90) % 4
    prepared = np.rot90(frame, k=-turns)  # a negative k turns clockwise
    if mirror:
        prepared = np.flip(prepared, axis=1)
    return np.ascontiguousarray(prepared)


def prepare_point(point: Point, rotate: int, mirror: bool) -> Point:
    """`prepare_frame` for one normalised (x, y) point of the raw frame."""
    x, y = point
    for _ in range((rotate // 90) % 4):
        x, y = 1 - y, x  # a quarter turn clockwise
    if mirror:
        x = 1 - x
    return (x, y)


def active_region(
    frame_width: int,
    frame_height: int,
    width_fraction: float,
    screen_aspect: float = DEFAULT_SCREEN_ASPECT,
) -> Region:
    """The centred Active region of a prepared frame, as normalised edges.

    Its width is `width_fraction` of the frame width and its shape is the
    screen's (`screen_aspect` is width over height). It never leaves the frame.
    """
    width = min(width_fraction, frame_height * screen_aspect / frame_width)
    height = width * frame_width / screen_aspect / frame_height
    left, top = (1 - width) / 2, (1 - height) / 2
    return (left, top, left + width, top + height)
