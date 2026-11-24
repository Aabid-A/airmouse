"""The controller: Hand frames in, state and commands out.

It owns the Paused / active state machine, and while active moves the cursor
to the Pointer (through the Active region and the One Euro filter). A held Open
palm unpauses (the Hold ring fills while it is held steady); an Open palm pauses
after a short debounce and releases any drag. After a held palm unpauses, the Open palm is ignored
until the Hand has left that pose, so the same palm cannot pause again at once.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from airmouse.config import OpenPalmConfig, TimingConfig
from airmouse.gestures import (
    LANDMARK_COUNT,
    POINTER,
    WRIST,
    Landmarks,
    distance,
    hand_size,
    open_palm_score,
)
from airmouse.mapping import CursorPath

# The wrist speed is smoothed over a few frames (weight of the newest frame), so
# one frame of landmark jitter cannot restart the Hold ring.
SPEED_SMOOTHING = 0.3


@dataclass(frozen=True)
class PalmReading:
    """What the controller saw in the latest frame, for the debug readout."""

    score: float | None  # Open palm score, None with no Hand
    threshold: float
    speed: float | None  # smoothed wrist speed in hand sizes per second
    speed_limit: float
    counts: bool  # the Open palm score reaches its threshold
    steady: bool  # the wrist speed is within the tolerance


class State(Enum):
    PAUSED = "paused"
    ACTIVE = "active"


class Output(Protocol):
    """What the controller can ask the outside world to do."""

    def move_cursor(self, x: float, y: float) -> None: ...

    def release_drag(self) -> None: ...


class Controller:
    def __init__(
        self,
        timing: TimingConfig,
        output: Output,
        cursor: CursorPath | None = None,
        open_palm: OpenPalmConfig | None = None,
    ) -> None:
        self._timing = timing
        self._palm = open_palm or OpenPalmConfig()
        self._score: float | None = None
        self._speed: float | None = None
        self._output = output
        self._cursor = cursor
        self.state = State.PAUSED
        self._now = 0.0
        self._palm_since: float | None = None  # start of the current Open palm run
        self._hold_since: float | None = None  # start of the steady hold (Paused)
        self._latched = False  # Open palm ignored until the Hand leaves that pose
        self._wrist: tuple[float, float, float] | None = None  # x, y, time

    @property
    def hold_progress(self) -> float:
        """How full the Hold ring is, 0 to 1."""
        if self.state is not State.PAUSED or self._hold_since is None:
            return 0.0
        hold = self._timing.unpause_hold_s
        return 1.0 if hold <= 0 else min(1.0, (self._now - self._hold_since) / hold)

    @property
    def reading(self) -> PalmReading:
        """The latest frame's Open palm score and wrist speed against their limits."""
        score, speed = self._score, self._speed
        return PalmReading(
            score=score,
            threshold=self._palm.score_threshold,
            speed=speed,
            speed_limit=self._palm.steady_max_speed,
            counts=score is not None and score >= self._palm.score_threshold,
            steady=speed is None or speed <= self._palm.steady_max_speed,
        )

    def update(self, time_s: float, landmarks: Landmarks | None) -> None:
        """Feed one frame. `landmarks` is None when no Hand is seen."""
        self._now = time_s
        self._measure(landmarks)
        if not self.reading.counts:
            self._latched = False
            self._reset_run()
            self._follow(landmarks)
            return
        if self._latched:
            return
        if self._palm_since is None:
            self._palm_since = time_s
        if self.state is State.PAUSED:
            self._charge()
        elif time_s - self._palm_since >= self._timing.pause_debounce_ms / 1000:
            self.state = State.PAUSED
            self._reset_run()
            self._output.release_drag()

    def _follow(self, landmarks: Landmarks | None) -> None:
        """Move the cursor to the Pointer while active. Otherwise leave the cursor alone."""
        if self._cursor is None:
            return
        if self.state is not State.ACTIVE or landmarks is None:
            self._cursor.reset()
            return
        self._output.move_cursor(*self._cursor.position(self._now, landmarks[POINTER]))

    def _reset_run(self) -> None:
        self._palm_since = None
        self._hold_since = None

    def _charge(self) -> None:
        if self._hold_since is None or not self.reading.steady:
            self._hold_since = self._now
        if self._now - self._hold_since >= self._timing.unpause_hold_s:
            self.state = State.ACTIVE
            self._latched = True
            self._reset_run()

    def _measure(self, landmarks: Landmarks | None) -> None:
        """Score the Open palm and the smoothed wrist speed for this frame."""
        self._score = None if landmarks is None else open_palm_score(landmarks, self._palm)
        if landmarks is None or len(landmarks) != LANDMARK_COUNT or hand_size(landmarks) <= 0:
            self._speed = None
            self._wrist = None
            return
        wrist = landmarks[WRIST]
        previous, self._wrist = self._wrist, (wrist[0], wrist[1], self._now)
        if previous is None or self._now <= previous[2]:
            return
        moved = distance(wrist, (previous[0], previous[1])) / hand_size(landmarks)
        speed = moved / (self._now - previous[2])
        old = self._speed
        self._speed = speed if old is None else old + SPEED_SMOOTHING * (speed - old)
