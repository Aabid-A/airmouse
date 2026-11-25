"""The controller: Hand frames in, state and commands out.

It owns the Paused / active state machine, and while active moves the cursor
to the Pointer (through the Active region and the One Euro filter). A held Open
palm unpauses (the Hold ring fills while it is held steady); an Open palm pauses
after a short debounce and releases any drag. After a held palm unpauses, the Open palm is ignored
until the Hand has left that pose, so the same palm cannot pause again at once.

While active, a Pinch (thumb tip to index tip, in hand sizes) freezes the cursor from
when it starts to form, so the click lands where the Pointer was aimed. A Pinch
released within the click window without the Pointer moving is a click; a Pinch
held while the Pointer moves is a drag, until the Pinch opens or airmouse pauses.
A closed Pinch never counts as an Open palm.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from airmouse.config import OpenPalmConfig, PinchConfig, TimingConfig
from airmouse.gestures import (
    LANDMARK_COUNT,
    POINTER,
    WRIST,
    Landmarks,
    PinchLatch,
    Point,
    distance,
    hand_size,
    open_palm_score,
    pinch_ratio,
)
from airmouse.mapping import CursorPath

# The wrist speed is smoothed over a few frames (weight of the newest frame), so
# one frame of landmark jitter cannot restart the Hold ring.
SPEED_SMOOTHING = 0.3

# A Pinch that has not moved the Pointer further than this (in hand sizes, from where
# the Pinch closed) is still a click; further and it is a drag.
CLICK_TOLERANCE = 0.15


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


class Phase(Enum):
    """Where a Pinch is: not pinching, closed and undecided, or dragging."""

    IDLE = "idle"
    PRESSED = "pressed"
    DRAGGING = "dragging"


class Output(Protocol):
    """What the controller can ask the outside world to do."""

    def move_cursor(self, x: float, y: float) -> None: ...

    def press(self, x: float, y: float) -> None: ...

    def drag_to(self, x: float, y: float) -> None: ...

    def release(self, x: float, y: float) -> None: ...

    def release_drag(self) -> None: ...


class Controller:
    def __init__(
        self,
        timing: TimingConfig,
        output: Output,
        cursor: CursorPath | None = None,
        open_palm: OpenPalmConfig | None = None,
        pinch: PinchConfig | None = None,
    ) -> None:
        self._timing = timing
        self._pinch_config = pinch or PinchConfig()
        self._pinch = PinchLatch(self._pinch_config)
        self._ratio: float | None = None
        self._phase = Phase.IDLE
        self._frozen: Point | None = None  # where the cursor last was (and stays while pinching)
        self._pressed_at = 0.0
        self._pressed_pointer: Point = (0.0, 0.0)
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
        self._ratio = None if landmarks is None else pinch_ratio(landmarks)
        self._pinch.update(self._ratio)
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
            self.release_drag()

    def release_drag(self) -> None:
        """End any Pinch in progress and lift the mouse button, whatever the Hand is doing."""
        self._phase = Phase.IDLE
        self._output.release_drag()

    def _follow(self, landmarks: Landmarks | None) -> None:
        """Move the cursor to the Pointer while active, with Pinch clicks and drags."""
        if self._cursor is None:
            return
        if self.state is not State.ACTIVE or landmarks is None:
            self._cursor.reset()
            self._frozen = None
            return
        position = self._cursor.position(self._now, landmarks[POINTER])
        if self._frozen is None:
            self._frozen = position
        if self._phase is Phase.IDLE:
            self._aim(position, landmarks)
        elif self._phase is Phase.PRESSED:
            self._decide(position, landmarks)
        else:
            self._drag(position)

    def _aim(self, position: Point, landmarks: Landmarks) -> None:
        """No Pinch yet: follow the Pointer, but freeze once a Pinch starts to form."""
        if self._pinch.closed:
            self._phase = Phase.PRESSED
            self._pressed_at = self._now
            self._pressed_pointer = landmarks[POINTER]
        elif self._ratio is None or self._ratio >= self._pinch_config.open_threshold:
            self._frozen = position
            self._output.move_cursor(*position)

    def _decide(self, position: Point, landmarks: Landmarks) -> None:
        """A closed Pinch: released in time without moving is a click; moving makes it a drag."""
        frozen = self._frozen or position
        if not self._pinch.closed:
            self._phase = Phase.IDLE
            if self._now - self._pressed_at <= self._pinch_config.click_window_ms / 1000:
                self._output.press(*frozen)
                self._output.release(*frozen)
            return
        size = hand_size(landmarks)
        moved = distance(landmarks[POINTER], self._pressed_pointer)
        if size > 0 and moved > CLICK_TOLERANCE * size:
            self._phase = Phase.DRAGGING
            self._output.press(*frozen)
            self._frozen = position
            self._output.drag_to(*position)

    def _drag(self, position: Point) -> None:
        if self._pinch.closed:
            self._frozen = position
            self._output.drag_to(*position)
        else:
            self._phase = Phase.IDLE
            self._output.release(*(self._frozen or position))

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
        if self._pinch.closed and self._score is not None:
            self._score = 0.0  # a closed Pinch never counts as an Open palm
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
