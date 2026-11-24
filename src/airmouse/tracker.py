"""The Hand tracker: camera frames in, the Hand's 21 landmarks out.

It wraps MediaPipe's `HandLandmarker` (Tasks API) and loads the vendored Hand
model from `assets/`. It never downloads anything (ADR 0001, ADR 0003).
MediaPipe is imported on use so the pure modules and the tests load without it.
"""

import importlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from airmouse.frame import Frame
from airmouse.gestures import Landmarks, hand_size

HAND_MODEL_PATH = Path(__file__).parent / "assets" / "hand_landmarker.task"
MAX_HANDS = 2  # track two so the one nearest the camera can be chosen


class TrackerError(Exception):
    """The Hand tracker could not start."""


class Tracker(Protocol):
    def track(self, frame: Frame, time_s: float) -> Landmarks | None:
        """The Hand nearest the camera in this frame, or None when no Hand is seen."""
        ...

    def close(self) -> None: ...


def nearest_hand(hands: Sequence[Landmarks]) -> Landmarks | None:
    """The Hand nearest the camera is the one that looks largest."""
    return max(hands, key=hand_size, default=None)


def mediapipe_image(frame: Frame) -> Any:
    mediapipe: Any = importlib.import_module("mediapipe")
    return mediapipe.Image(image_format=mediapipe.ImageFormat.SRGB, data=frame)


class HandLandmarkerTracker:
    def __init__(
        self, landmarker: Any, make_image: Callable[[Frame], Any] = mediapipe_image
    ) -> None:
        self._landmarker = landmarker
        self._make_image = make_image
        self._last_timestamp_ms = -1

    @classmethod
    def open(cls, model_path: Path = HAND_MODEL_PATH) -> "HandLandmarkerTracker":
        if not model_path.is_file():
            raise TrackerError(f"the Hand model is missing: {model_path}")
        vision: Any = importlib.import_module("mediapipe.tasks.python.vision")
        base_options: Any = importlib.import_module("mediapipe.tasks.python.core.base_options")
        options = vision.HandLandmarkerOptions(
            base_options=base_options.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=MAX_HANDS,
        )
        return cls(vision.HandLandmarker.create_from_options(options))

    def track(self, frame: Frame, time_s: float) -> Landmarks | None:
        image = self._make_image(frame)
        # MediaPipe needs strictly increasing timestamps in whole milliseconds.
        timestamp_ms = max(round(time_s * 1000), self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        hands: list[Landmarks] = [
            [(point.x, point.y) for point in hand] for hand in result.hand_landmarks
        ]
        return nearest_hand(hands)

    def close(self) -> None:
        self._landmarker.close()
