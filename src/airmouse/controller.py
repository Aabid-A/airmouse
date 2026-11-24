"""The controller: Hand frames in, state and commands out.

It owns the Paused / active state machine, and while active moves the cursor
to the Pointer (through the Active region and the One Euro filter). A held Open
palm unpauses (the Hold ring fills while it is held steady); an Open palm pauses
after a short debounce and releases any drag. After a held palm unpauses, the Open palm is ignored
until the Hand has left that pose, so the same palm cannot pause again at once.
"""

from enum import Enum
from typing import Protocol

from airmouse.config import TimingConfig
from airmouse.gestures import POINTER, WRIST, Landmarks, distance, hand_size, is_open_palm
from airmouse.mapping import CursorPath

# The wrist may move at most this many hand sizes per second for the Open palm
# to count as steady while the Hold ring fills.
STEADY_MAX_SPEED = 1.0


class State(Enum):
    PAUSED = "paused"
    ACTIVE = "active"


class Output(Protocol):
    """What the controller can ask the outside world to do."""

    def move_cursor(self, x: float, y: float) -> None: ...

    def release_drag(self) -> None: ...


class Controller:
    def __init__(
        self, timing: TimingConfig, output: Output, cursor: CursorPath | None = None
    ) -> None:
        self._timing = timing
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

    def update(self, time_s: float, landmarks: Landmarks | None) -> None:
        """Feed one frame. `landmarks` is None when no Hand is seen."""
        self._now = time_s
        if landmarks is None or not is_open_palm(landmarks):
            self._latched = False
            self._reset_run()
            self._follow(landmarks)
            return
        if self._latched:
            return
        if self._palm_since is None:
            self._palm_since = time_s
        if self.state is State.PAUSED:
            self._charge(landmarks)
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
        self._wrist = None

    def _charge(self, landmarks: Landmarks) -> None:
        if self._hold_since is None or not self._is_steady(landmarks):
            self._hold_since = self._now
        if self._now - self._hold_since >= self._timing.unpause_hold_s:
            self.state = State.ACTIVE
            self._latched = True
            self._reset_run()

    def _is_steady(self, landmarks: Landmarks) -> bool:
        wrist = landmarks[WRIST]
        previous, self._wrist = self._wrist, (wrist[0], wrist[1], self._now)
        if previous is None or self._now <= previous[2]:
            return True
        moved = distance(wrist, (previous[0], previous[1])) / hand_size(landmarks)
        return moved / (self._now - previous[2]) <= STEADY_MAX_SPEED
