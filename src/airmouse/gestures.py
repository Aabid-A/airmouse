"""Gesture recognition from the Hand's 21 landmarks (pure functions, no camera).

Landmarks are normalised MediaPipe coordinates: index 0 is the wrist, 4/8/12/16/20
the fingertips and 5/9/13/17 the finger base (MCP) joints.
"""

import math
from collections.abc import Sequence

from airmouse.config import OpenPalmConfig, PinchConfig

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

# All distances are in hand sizes (wrist to the middle finger's base), so the
# Open palm reads the same near or far from the camera.
THUMB_OUT = 0.7  # a thumb tip this far from the index finger's base is fully out
FINGER_SPREAD = 0.25  # neighbouring fingertips this far apart are fully spread

DEFAULT_OPEN_PALM = OpenPalmConfig()


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
