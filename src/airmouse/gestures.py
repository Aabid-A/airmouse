"""Gesture recognition from the Hand's 21 landmarks (pure functions, no camera).

Landmarks are normalised MediaPipe coordinates: index 0 is the wrist, 4/8/12/16/20
the fingertips and 5/9/13/17 the finger base (MCP) joints.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from airmouse.config import ClutchConfig, OpenPalmConfig, PinchConfig, ScrollConfig

type Point = tuple[float, float]
type Landmarks = Sequence[Point]

LANDMARK_COUNT = 21
WRIST = 0
THUMB_TIP = 4
POINTER = 8  # the index fingertip; its position drives the cursor
INDEX_MCP = 5
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_TIP = 12
RING_TIP = 16
PINKY_TIP = 20
FINGER_TIPS = (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
FINGER_BASES = (5, 9, 13, 17)  # the MCP joint of each finger in FINGER_TIPS

# All distances are in hand sizes (wrist to the middle finger's base), so the
# Open palm reads the same near or far from the camera.
THUMB_OUT = 0.7  # a thumb tip this far from the index finger's base is fully out
FINGER_SPREAD = 0.25  # neighbouring fingertips this far apart are fully spread

DEFAULT_OPEN_PALM = OpenPalmConfig()
DEFAULT_CLUTCH = ClutchConfig()
DEFAULT_SCROLL = ScrollConfig()


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


@dataclass(frozen=True)
class FingerCurl:
    """One finger read two ways, each from 0 (open) to 1 (curled), plus where its tip lies.

    `by_ratio` comes from wrist-to-tip over wrist-to-base distance, `by_axis` from how far
    the tip lies past its own base along the hand's axis (`beyond`, in hand sizes). A
    finger aimed at the camera looks short, which fools the ratio, but its tip still lies
    beyond its base.
    """

    by_ratio: float
    by_axis: float
    beyond: float

    @property
    def curled_by_both(self) -> float:
        """Curled only as far as both measures agree (the Fist's rule)."""
        return min(self.by_ratio, self.by_axis)

    @property
    def curled_by_either(self) -> float:
        """Curled as far as either measure says."""
        return max(self.by_ratio, self.by_axis)


def finger_curls(
    landmarks: Landmarks,
    *,
    tip_curled: float,
    tip_open: float,
    finger_curled: float,
    finger_open: float,
) -> tuple[FingerCurl, ...] | None:
    """Index, middle, ring and pinky, each scored as a `FingerCurl`: a tip at `tip_curled`
    or less past its base is fully curled by the axis, at `tip_open` or more fully open;
    a ratio at `finger_curled` or less is fully curled, at `finger_open` or more open.
    None when the Hand cannot be measured."""
    if len(landmarks) != LANDMARK_COUNT:
        return None
    wrist = landmarks[WRIST]
    size = hand_size(landmarks)
    if size <= 0:
        return None
    middle = landmarks[MIDDLE_MCP]
    axis = ((middle[0] - wrist[0]) / size, (middle[1] - wrist[1]) / size)
    fingers: list[FingerCurl] = []
    for tip, base in zip(FINGER_TIPS, FINGER_BASES, strict=True):
        reach = distance(wrist, landmarks[base])
        if reach <= 0:
            return None
        ratio = distance(wrist, landmarks[tip]) / reach
        beyond = _beyond(landmarks, tip, base, axis, size)
        fingers.append(
            FingerCurl(
                by_ratio=1 - _ramp(ratio, finger_curled, finger_open),
                by_axis=1 - _ramp(beyond, tip_curled, tip_open),
                beyond=beyond,
            )
        )
    return tuple(fingers)


def _pair(a: float, b: float, together: float) -> float:
    """The lower of two values, moved towards the higher as far as `together` (0 to 1)."""
    low, high = min(a, b), max(a, b)
    return low + together * (high - low)


def two_finger_score(landmarks: Landmarks, config: ScrollConfig = DEFAULT_SCROLL) -> float:
    """How much the Hand looks like the Scroll pose, from 0 to 1: index and middle
    raised together, ring and pinky curled, the thumb free. The weakest of three parts:

    - the pair raised: index and middle each count as open as far as either the distance
      ratio or the axis says (the Fist measure, read the other way), so fingers aimed at
      the camera still count;
    - ring and pinky curled: each as far as either measure says;
    - the separation: how far the pair's tips lie past their bases beyond the less
      curled of ring and pinky, along the hand's axis, ramping from half of
      `config.separation` to all of it (hand sizes). This is what tells the pose from a
      hand whose fingers are all half open, three fingers or an open palm, at any tilt.

    Index and middle are read as a pair: when their tips are closer than
    `config.pair_gap` hand sizes (overlapping, as when they point at the camera), the
    pair takes the better of the two, ramping back to the worse at twice the gap. They
    never need to be spread.
    """
    fingers = finger_curls(
        landmarks,
        tip_curled=config.tip_curled,
        tip_open=config.tip_open,
        finger_curled=config.finger_curled,
        finger_open=config.finger_open,
    )
    if fingers is None:
        return 0.0
    index, middle, ring, pinky = fingers
    gap = distance(landmarks[INDEX_TIP], landmarks[MIDDLE_TIP]) / hand_size(landmarks)
    together = 1 - _ramp(gap, config.pair_gap, 2 * config.pair_gap)
    raised = _pair(1 - index.curled_by_both, 1 - middle.curled_by_both, together)
    rest = min(ring.curled_by_either, pinky.curled_by_either)
    lead = _pair(index.beyond, middle.beyond, together) - max(ring.beyond, pinky.beyond)
    separation = _ramp(lead, config.separation / 2, config.separation)
    return min(raised, rest, separation)


def scroll_point(landmarks: Landmarks) -> Point:
    """The midpoint of the index and middle fingers' base (MCP) joints, the knuckles: the
    point the Scroll follows. Where it is when scrolling starts is the anchor. The knuckles,
    not the fingertips, so tilting the two fingers towards the camera moves it less."""
    (ix, iy), (mx, my) = landmarks[INDEX_MCP], landmarks[MIDDLE_MCP]
    return ((ix + mx) / 2, (iy + my) / 2)


def is_open_palm(landmarks: Landmarks, config: OpenPalmConfig = DEFAULT_OPEN_PALM) -> bool:
    """The Open palm score reaches its threshold."""
    return open_palm_score(landmarks, config) >= config.score_threshold


def finger_curl(landmarks: Landmarks, config: ClutchConfig = DEFAULT_CLUTCH) -> float:
    """How curled the least curled of the four fingers is, from 0 (open) to 1 (curled).

    Each finger takes the lower of two scores (see `ClutchConfig` and `FingerCurl`): how
    far its tip lies past its own base along the hand's axis (wrist to the middle
    finger's base), and its wrist-to-tip over wrist-to-base distance. Both are in hand
    units, so they read the same near or far from the camera. A finger aimed at the
    camera looks short, which fools the distance ratio, but its tip still lies beyond its
    base, so the lower score says open. The index counts like the others, so the Pointer
    pose scores 0. Unlike `fist_score`, a thumb on the index tip does not zero it.
    """
    fingers = finger_curls(
        landmarks,
        tip_curled=config.tip_curled,
        tip_open=config.tip_open,
        finger_curled=config.finger_curled,
        finger_open=config.finger_open,
    )
    if fingers is None:
        return 0.0
    return min(finger.curled_by_both for finger in fingers)


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
