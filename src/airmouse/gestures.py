"""Gesture recognition from the Hand's 21 landmarks (pure functions, no camera).

Landmarks are normalised MediaPipe coordinates: index 0 is the wrist, 4/8/12/16/20
the fingertips and 5/9/13/17 the finger base (MCP) joints.
"""

import math
from collections.abc import Sequence

type Point = tuple[float, float]
type Landmarks = Sequence[Point]

LANDMARK_COUNT = 21
WRIST = 0
THUMB_TIP = 4
POINTER = 8  # the index fingertip; its position drives the cursor
INDEX_MCP = 5
MIDDLE_MCP = 9
FINGER_TIPS = (8, 12, 16, 20)

# All distances are in hand sizes (wrist to the middle finger's base), so the
# Open palm reads the same near or far from the camera.
FINGER_EXTENDED = 1.5  # a fingertip this far from the wrist counts as extended
THUMB_OUT = 0.7  # thumb tip this far from the index finger's base counts as out
FINGER_SPREAD = 0.25  # neighbouring fingertips at least this far apart


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hand_size(landmarks: Landmarks) -> float:
    """Wrist to the middle finger's base: the unit all gesture thresholds use."""
    return distance(landmarks[WRIST], landmarks[MIDDLE_MCP])


def is_open_palm(landmarks: Landmarks) -> bool:
    """All five fingers extended and spread."""
    if len(landmarks) != LANDMARK_COUNT:
        return False
    size = hand_size(landmarks)
    if size <= 0:
        return False
    wrist = landmarks[WRIST]
    if any(distance(wrist, landmarks[tip]) < FINGER_EXTENDED * size for tip in FINGER_TIPS):
        return False
    if distance(landmarks[THUMB_TIP], landmarks[INDEX_MCP]) < THUMB_OUT * size:
        return False
    tips = [landmarks[tip] for tip in FINGER_TIPS]
    return all(distance(a, b) >= FINGER_SPREAD * size for a, b in zip(tips, tips[1:], strict=False))
