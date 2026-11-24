from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from airmouse.gestures import Landmarks
from airmouse.tracker import HandLandmarkerTracker, TrackerError, nearest_hand
from hands import open_hand, placed


@dataclass
class Point:
    x: float
    y: float


@dataclass
class Result:
    hand_landmarks: list[list[Point]]


class FakeLandmarker:
    def __init__(self, hands: list[list[Point]]) -> None:
        self.hands = hands
        self.timestamps: list[int] = []
        self.closed = False

    def detect_for_video(self, image: Any, timestamp_ms: int) -> Result:
        self.timestamps.append(timestamp_ms)
        return Result(self.hands)

    def close(self) -> None:
        self.closed = True


def frame() -> Any:
    return np.zeros((480, 640, 3), dtype=np.uint8)


def tracker_for(hands: list[list[Point]]) -> HandLandmarkerTracker:
    """A tracker over a fake landmarker; the frame is passed through, not wrapped by MediaPipe."""
    return HandLandmarkerTracker(FakeLandmarker(hands), make_image=lambda frame: frame)


def as_points(hand: Landmarks) -> list[Point]:
    return [Point(x, y) for x, y in hand]


def test_the_hand_nearest_the_camera_is_the_largest() -> None:
    far = placed(open_hand(), scale=0.5)
    near = placed(open_hand(), scale=1.2, dx=0.1)

    assert nearest_hand([far, near]) is near
    assert nearest_hand([near, far]) is near


def test_no_hands_means_no_nearest_hand() -> None:
    assert nearest_hand([]) is None


def test_the_tracker_returns_the_nearest_of_two_hands() -> None:
    far = placed(open_hand(), scale=0.5)
    near = placed(open_hand(), scale=1.0, dx=0.1)
    tracker = tracker_for([as_points(far), as_points(near)])

    assert tracker.track(frame(), 1.0) == near


def test_the_tracker_returns_none_when_no_hand_is_seen() -> None:
    assert tracker_for([]).track(frame(), 1.0) is None


def test_timestamps_strictly_increase_even_when_the_clock_repeats() -> None:
    landmarker = FakeLandmarker([])
    tracker = HandLandmarkerTracker(landmarker, make_image=lambda frame: frame)

    for time_s in (1.0, 1.0001, 1.0001, 0.5):
        tracker.track(frame(), time_s)

    assert landmarker.timestamps == [1000, 1001, 1002, 1003]


def test_close_closes_the_landmarker() -> None:
    landmarker = FakeLandmarker([])

    HandLandmarkerTracker(landmarker, make_image=lambda frame: frame).close()

    assert landmarker.closed


def test_a_missing_hand_model_is_an_error_not_a_download(tmp_path: Path) -> None:
    with pytest.raises(TrackerError, match="Hand model is missing"):
        HandLandmarkerTracker.open(tmp_path / "hand_landmarker.task")
