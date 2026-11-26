"""Gesture recognition from the Hand's 21 landmarks (pure functions, no camera).

Landmarks are normalised MediaPipe coordinates: index 0 is the wrist, 4/8/12/16/20
the fingertips and 5/9/13/17 the finger base (MCP) joints.
"""

import math
from collections.abc import Sequence

from airmouse.config import ClutchConfig, OpenPalmConfig, PinchConfig

type Point = tuple[float, float]
type Landmarks = Sequence[Point]

LANDMARK_COUNT = 21
WRIST = 0
THUMB_TIP = 4
POINTER = 8  # the index fingertip; its position drives the cursor
INDEX_MCP = 5
INDEX_TIP = 8
MIDDLE_MCP = 9
FINGER_TIPS = (8, 12, 16, 20)
FINGER_BASES = (5, 9, 13, 17)  # the MCP joint of each finger in FINGER_TIPS

# All distances are in hand sizes (wrist to the middle finger's base), so the
# Open palm reads the same near or far from the camera.
THUMB_OUT = 0.7  # a thumb tip this far from the index finger's base is fully out
FINGER_SPREAD = 0.25  # neighbouring fingertips this far apart are fully spread

DEFAULT_OPEN_PALM = OpenPalmConfig()
DEFAULT_CLUTCH = ClutchConfig()


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hand_size(landmarks: Landmarks) -> float:
    """Wrist to the middle finger's base: the unit all gesture thresholds use."""
    return distance(landmarks[WRIST], landmarks[MIDDLE_MCP])


def pinch_ratio(landmarks: Landmarks) -> float | None:
    """Thumb tip to index tip, in hand sizes. None when the Hand cannot be measured."""
    if len(landmarks) != LANDMARK_COUNT:
        return None
    size = hand_size(landmarks)
    if size <= 0:
        return None
    return distance(landmarks[THUMB_TIP], landmarks[INDEX_TIP]) / size


class PinchLatch:
    """Closed below the close threshold and open above the open threshold.

    Between the two it keeps its last answer, so a ratio hovering near one
    threshold cannot flicker the Pinch on and off.
    """

    def __init__(self, config: PinchConfig) -> None:
        self._config = config
        self.closed = False

    def reset(self) -> None:
        """Forget the Pinch: open, as if it had never closed."""
        self.closed = False

    def update(self, ratio: float | None) -> bool:
        if ratio is None:
            return self.closed
        if ratio < self._config.close_threshold:
            self.closed = True
        elif ratio > self._config.open_threshold:
            self.closed = False
        return self.closed


def _ramp(value: float, low: float, high: float) -> float:
    """0 at `low` or less, 1 at `high` or more, a straight line between."""
    return max(0.0, min(1.0, (value - low) / (high - low)))


def open_palm_score(landmarks: Landmarks, config: OpenPalmConfig = DEFAULT_OPEN_PALM) -> float:
    """How much the Hand looks like an Open palm, from 0 to 1.

    Mostly how far each of the four fingers reaches from the wrist, so upright
    fingers held together score well and a fist or a Pointer pose (one finger out,
    three curled) does not. A thumb that is out and fingertips that are spread add
    a little. A thumb tip touching the index tip (a Pinch) scores 0.
    """
    if len(landmarks) != LANDMARK_COUNT:
        return 0.0
    size = hand_size(landmarks)
    if size <= 0:
        return 0.0
    if distance(landmarks[THUMB_TIP], landmarks[INDEX_TIP]) < config.pinch_gap * size:
        return 0.0
    wrist = landmarks[WRIST]
    reach = [
        _ramp(distance(wrist, landmarks[tip]) / size, config.finger_curled, config.finger_extended)
        for tip in FINGER_TIPS
    ]
    thumb = _ramp(distance(landmarks[THUMB_TIP], landmarks[INDEX_MCP]) / size, 0.0, THUMB_OUT)
    tips = [landmarks[tip] for tip in FINGER_TIPS]
    gaps = [distance(a, b) / size for a, b in zip(tips, tips[1:], strict=False)]
    spread = _ramp(sum(gaps) / len(gaps), 0.0, FINGER_SPREAD)
    reach_weight = 1 - config.thumb_weight - config.spread_weight
    return (
        reach_weight * sum(reach) / len(reach)
        + config.thumb_weight * thumb
        + config.spread_weight * spread
    )


def is_open_palm(landmarks: Landmarks, config: OpenPalmConfig = DEFAULT_OPEN_PALM) -> bool:
    """The Open palm score reaches its threshold."""
    return open_palm_score(landmarks, config) >= config.score_threshold


def finger_curl(landmarks: Landmarks, config: ClutchConfig = DEFAULT_CLUTCH) -> float:
    """How curled the least curled of the four fingers is, from 0 (open) to 1 (curled).

    Each finger takes the lower of two scores (see `ClutchConfig`): how far its tip
    lies past its own base along the hand's axis (wrist to the middle finger's base),
    and its wrist-to-tip over wrist-to-base distance. Both are in hand units, so they
    read the same near or far from the camera. A finger aimed at the camera looks
    short, which fools the distance ratio, but its tip still lies beyond its base, so
    the lower score says open. The index counts like the others, so the Pointer pose
    scores 0. Unlike `fist_score`, a thumb on the index tip does not zero it.
    """
    if len(landmarks) != LANDMARK_COUNT:
        return 0.0
    wrist = landmarks[WRIST]
    size = hand_size(landmarks)
    if size <= 0:
        return 0.0
    middle = landmarks[MIDDLE_MCP]
    axis = ((middle[0] - wrist[0]) / size, (middle[1] - wrist[1]) / size)
    curls: list[float] = []
    for tip, base in zip(FINGER_TIPS, FINGER_BASES, strict=True):
        reach = distance(wrist, landmarks[base])
        if reach <= 0:
            return 0.0
        ratio = distance(wrist, landmarks[tip]) / reach
        beyond = _beyond(landmarks, tip, base, axis, size)
        by_ratio = 1 - _ramp(ratio, config.finger_curled, config.finger_open)
        by_axis = 1 - _ramp(beyond, config.tip_curled, config.tip_open)
        curls.append(min(by_ratio, by_axis))
    return min(curls)


def _beyond(landmarks: Landmarks, tip: int, base: int, axis: Point, size: float) -> float:
    """How far the `tip` landmark lies past the `base` one along the hand's axis, in hand
    sizes: positive when the finger reaches out, negative once it folds back to the palm."""
    tip_x, tip_y = landmarks[tip]
    base_x, base_y = landmarks[base]
    return ((tip_x - base_x) * axis[0] + (tip_y - base_y) * axis[1]) / size


def index_reach(landmarks: Landmarks) -> float | None:
    """How far the index tip lies past its base along the hand's axis, in hand sizes.

    It falls as the index curls towards the palm. None when the Hand cannot be measured.
    """
    if len(landmarks) != LANDMARK_COUNT:
        return None
    size = hand_size(landmarks)
    if size <= 0:
        return None
    wrist, middle = landmarks[WRIST], landmarks[MIDDLE_MCP]
    axis = ((middle[0] - wrist[0]) / size, (middle[1] - wrist[1]) / size)
    return _beyond(landmarks, INDEX_TIP, INDEX_MCP, axis, size)


def fist_score(landmarks: Landmarks, config: ClutchConfig = DEFAULT_CLUTCH) -> float:
    """How much the Hand looks like a Fist (all four fingers curled), from 0 to 1.

    The thumb is free (tucked over the fingers or beside them), except that a thumb
    tip right on the index tip (closer than `config.pinch_gap` hand sizes) is a Pinch
    and scores 0.
    """
    if len(landmarks) != LANDMARK_COUNT:
        return 0.0
    size = hand_size(landmarks)
    if size <= 0:
        return 0.0
    if distance(landmarks[THUMB_TIP], landmarks[INDEX_TIP]) < config.pinch_gap * size:
        return 0.0
    return finger_curl(landmarks, config)
