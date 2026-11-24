"""Anatomically modelled synthetic Hands (21 MediaPipe landmarks), never recorded video.

A Hand is built in "palm units" (wrist to the middle finger's base is 1) with real
finger proportions, then turned like a hand seen by a camera: pitched (the
fingertips tilted towards or away from the lens, which foreshortens the Hand),
rolled in the image plane, placed in a 640x480 frame, and jittered. Fingers bend
in the plane that holds the palm's long axis and its normal, so a curled finger
shortens in the picture the way a real one does.

Landmark order: wrist 0, thumb 1-4, index 5-8, middle 9-12, ring 13-16, pinky 17-20.
"""

import math
import random
from dataclasses import dataclass

from airmouse.gestures import Landmarks, Point

type Vec = tuple[float, float, float]  # x across the palm, y along it (up), z towards the camera

FRAME_ASPECT = 640 / 480
HAND_HEIGHT = 0.30  # a palm unit in frame heights, when the Hand faces the camera

# Finger base (MCP) positions and bone lengths (proximal, middle, distal), in palm units.
MCP: dict[str, tuple[float, float]] = {
    "index": (-0.30, 0.97),
    "middle": (0.0, 1.0),
    "ring": (0.27, 0.95),
    "pinky": (0.52, 0.82),
}
BONES: dict[str, tuple[float, float, float]] = {
    "index": (0.40, 0.23, 0.19),
    "middle": (0.42, 0.26, 0.20),
    "ring": (0.40, 0.25, 0.19),
    "pinky": (0.31, 0.17, 0.17),
}
FINGERS = tuple(MCP)
THUMB_BONES = (0.45, 0.36, 0.30)  # metacarpal, proximal, distal
THUMB_BASE = (-0.20, 0.18)

type Bend = tuple[float, float, float]


@dataclass(frozen=True)
class Pose:
    """Per finger: the sideways angle at its base and the bend (degrees) at its three joints."""

    fan: dict[str, float]
    bend: dict[str, Bend]
    thumb_angles: Bend  # direction of each thumb bone, degrees from "up"
    thumb_lift: float = 0.0  # degrees the thumb bones lift towards the camera
    pinch: bool = False  # bring the thumb tip to the index tip


TOGETHER = {"index": -2.0, "middle": 0.0, "ring": 2.0, "pinky": 7.0}
FANNED = {"index": -16.0, "middle": -4.0, "ring": 9.0, "pinky": 26.0}
CLOSED = {"index": -2.0, "middle": 0.0, "ring": 2.0, "pinky": 5.0}

STRAIGHT: Bend = (0.0, 0.0, 0.0)
RELAXED: Bend = (12.0, 18.0, 10.0)  # a relaxed open hand is never perfectly straight
CURLED: Bend = (88.0, 100.0, 60.0)
LOOSE_CURL: Bend = (70.0, 80.0, 45.0)  # a relaxed pointing hand's three folded fingers
HOOKED: Bend = (45.0, 55.0, 30.0)  # half open: not a clean pointer, not an open hand

LIGHT_CURVE: dict[str, Bend] = {
    "index": (6, 10, 6),
    "middle": (5, 10, 6),
    "ring": (8, 12, 8),
    "pinky": (12, 16, 10),
}
FIST: dict[str, Bend] = {"index": CURLED, "middle": CURLED, "ring": CURLED, "pinky": CURLED}

POSES: dict[str, Pose] = {
    "open together": Pose(TOGETHER, LIGHT_CURVE, (-38.0, -30.0, -24.0)),
    "open relaxed curl": Pose(
        TOGETHER,
        {"index": RELAXED, "middle": RELAXED, "ring": RELAXED, "pinky": (20, 24, 14)},
        (-30.0, -20.0, -10.0),
    ),
    "open fanned": Pose(
        FANNED,
        {finger: STRAIGHT for finger in MCP},
        (-70.0, -64.0, -58.0),
    ),
    "open thumb tucked": Pose(TOGETHER, LIGHT_CURVE, (30.0, 40.0, 50.0), thumb_lift=40.0),
    "fist": Pose(CLOSED, FIST, (25.0, 55.0, 85.0), thumb_lift=50.0),
    "pointing": Pose(
        CLOSED,
        {**FIST, "index": (4, 6, 4)},
        (20.0, 45.0, 70.0),
        thumb_lift=45.0,
    ),
    "pointing relaxed": Pose(
        CLOSED,
        {"index": (4, 6, 4), "middle": LOOSE_CURL, "ring": LOOSE_CURL, "pinky": LOOSE_CURL},
        (-10.0, 5.0, 20.0),
        thumb_lift=25.0,
    ),
    "half-open fingers": Pose(
        CLOSED,
        {"index": (4, 6, 4), "middle": HOOKED, "ring": HOOKED, "pinky": HOOKED},
        (-10.0, 5.0, 20.0),
        thumb_lift=25.0,
    ),
    "pinch fingers curled": Pose(
        CLOSED,
        {**FIST, "index": (35, 45, 25)},
        (-30.0, 0.0, 0.0),
        pinch=True,
    ),
    "pinch others open": Pose(
        TOGETHER,
        {"index": (35, 45, 25), "middle": RELAXED, "ring": RELAXED, "pinky": RELAXED},
        (-30.0, 0.0, 0.0),
        pinch=True,
    ),
}


def _rotate_x(point: Vec, degrees: float) -> Vec:
    """Pitch about the horizontal axis through the wrist: fingertips towards the camera."""
    x, y, z = point
    angle = math.radians(degrees)
    return (x, y * math.cos(angle) - z * math.sin(angle), y * math.sin(angle) + z * math.cos(angle))


def _lerp(start: Vec, end: Vec, fraction: float) -> Vec:
    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
        start[2] + (end[2] - start[2]) * fraction,
    )


def _finger(name: str, fan: float, bend: Bend) -> list[Vec]:
    """The finger's four landmarks (MCP, PIP, DIP, tip): bone by bone, bending to the camera."""
    base_x, base_y = MCP[name]
    points: list[Vec] = [(base_x, base_y, 0.0)]
    cumulative = 0.0
    spread = math.radians(fan)
    for length, joint in zip(BONES[name], bend, strict=True):
        cumulative += math.radians(joint)
        along = length * math.cos(cumulative)
        x, y, z = points[-1]
        points.append(
            (
                x + along * math.sin(spread),
                y + along * math.cos(spread),
                z + length * math.sin(cumulative),
            )
        )
    return points


def _thumb(pose: Pose) -> list[Vec]:
    x, y = THUMB_BASE
    points: list[Vec] = [(x, y, 0.0)]
    lift = math.radians(pose.thumb_lift)
    for length, degrees in zip(THUMB_BONES, pose.thumb_angles, strict=True):
        angle = math.radians(degrees)
        px, py, pz = points[-1]
        points.append(
            (
                px + length * math.sin(angle) * math.cos(lift),
                py + length * math.cos(angle) * math.cos(lift),
                pz + length * math.sin(lift),
            )
        )
    return points


def build_palm_units(pose: Pose) -> list[Vec]:
    """The 21 landmarks of `pose` facing the camera, in palm units, y up."""
    thumb = _thumb(pose)
    fingers = {name: _finger(name, pose.fan[name], pose.bend[name]) for name in FINGERS}
    if pose.pinch:
        index_tip = fingers["index"][3]
        thumb[3] = (index_tip[0] - 0.02, index_tip[1] - 0.04, index_tip[2] + 0.02)
        thumb[1] = _lerp(thumb[0], thumb[3], 0.4)
        thumb[2] = _lerp(thumb[0], thumb[3], 0.75)
    points: list[Vec] = [(0.0, 0.0, 0.0), *thumb]
    for name in FINGERS:
        points.extend(fingers[name])
    return points


def synthetic_hand(
    pose: str,
    *,
    pitch: float = 0.0,
    roll: float = 0.0,
    size: float = HAND_HEIGHT,
    centre: Point = (0.5, 0.75),
    jitter: float = 0.0,
    seed: int = 0,
) -> Landmarks:
    """A pose seen by the camera as normalised landmarks (wrist at `centre`).

    `pitch` tilts the fingertips towards (positive) or away from the camera, `roll`
    turns the Hand in the image (degrees, clockwise), `size` is a palm unit in
    frame heights, and `jitter` is the standard deviation of per-landmark noise in
    frame heights.
    """
    rng = random.Random(seed)
    turn = math.radians(roll)
    result: list[Point] = []
    for point in build_palm_units(POSES[pose]):
        x, y, _ = _rotate_x(point, pitch)
        x, y = x * math.cos(turn) + y * math.sin(turn), y * math.cos(turn) - x * math.sin(turn)
        px = centre[0] + (x * size + rng.gauss(0.0, jitter)) / FRAME_ASPECT
        py = centre[1] - y * size + rng.gauss(0.0, jitter)
        result.append((px, py))
    return result
