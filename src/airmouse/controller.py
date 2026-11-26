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

When no Hand has been seen for `timing.no_hand_timeout_ms` the controller is in the
No hand state: the cursor freezes, any Pinch or drag is released (the button goes up
where the cursor was), and the Pinch is forgotten. airmouse stays unpaused. A shorter
dropout changes nothing. When the Hand returns the cursor follows the Pointer again
from its new position (the filter starts afresh, so it does not glide from the old
spot), but a Hand that returns still pinched must open its Pinch before a click or
drag can start, so losing the Hand never presses the button.

In relative control mode (when the Controller is given a `ClutchConfig`) a Fist (all
four fingers curled) held for `clutch.debounce_ms` is the clutch: while it is held
the cursor does not follow, no click or drag can start, and a held drag is released.
The Hand leaving the frame (No hand) also stops the cursor, shown as No hand. The
clutch has priority over the Pinch, because closing a fist moves the index towards
the thumb:

- while the finger curl is at `clutch.hold_threshold` or more (the fingers may be
  closing into a Fist) the cursor holds still (HOLD in the Preview), and that
  movement is dropped;
- a closed but undecided Pinch is cancelled (no click) on the first frame that reads
  as a Fist, or once the index tip has folded back towards the palm since it closed,
  and a drag only starts when the whole hand moves, not just the curling fingertip;
- after a clutch, as after No hand, the Pinch must open and the finger curl must fall
  below the hold threshold before the cursor follows or a Pinch can click (HOLD), and
  a Pinch that closes within `REOPEN_S` of the clutch ending is ignored.

Following resumes from where the cursor is, with no movement on the first frame.
Without a `ClutchConfig` (absolute mode) none of this applies: the behaviour is
exactly that of absolute mode before relative mode existed.

The Scroll works in both control modes. While active, the two-finger pose (index and
middle raised, ring and pinky curled) held for `scroll.debounce_ms` starts a scroll,
anchored at the midpoint of the two fingertips. Each frame the Hand's vertical offset
from the anchor (in hand sizes) sets a scroll speed: nothing within the deadzone, then
growing with the offset up to a cap. While scrolling the cursor holds still, a Pinch
cannot start and no button is ever pressed. The scroll ends at once when the pose ends
(a closed Pinch, a Fist or an Open palm never counts as the pose), when airmouse pauses
or on No hand. After No hand the pose must be left and formed again before a new
scroll can start, so a returning Hand never scrolls on its own. After any scroll a
Pinch that closed must open before it can click, as after No hand.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from airmouse.config import ClutchConfig, OpenPalmConfig, PinchConfig, ScrollConfig, TimingConfig
from airmouse.gestures import (
    INDEX_MCP,
    LANDMARK_COUNT,
    POINTER,
    WRIST,
    Landmarks,
    PinchLatch,
    Point,
    distance,
    finger_curl,
    fist_score,
    hand_size,
    index_reach,
    open_palm_score,
    pinch_ratio,
    scroll_point,
    two_finger_score,
)
from airmouse.mapping import CursorPath

# The wrist speed is smoothed over a few frames (weight of the newest frame), so
# one frame of landmark jitter cannot restart the Hold ring.
SPEED_SMOOTHING = 0.3

# A Pinch that has not moved the Pointer further than this (in hand sizes, from where
# the Pinch closed) is still a click; further and it is a drag.
CLICK_TOLERANCE = 0.15

# A closed Pinch during which the index tip folds this far back towards the palm (in
# hand sizes, along the hand's axis) is a Fist forming, not a click or a drag.
FIST_FORMING = 0.3

# A Pinch that closes within this many seconds after a clutch ends is the hand opening
# out of the Fist (the index passing the thumb), not a click.
REOPEN_S = 0.3


def scroll_speed(offset: float, config: ScrollConfig) -> float:
    """Scroll speed in pixels per second for a vertical offset from the anchor (hand
    sizes, positive when the Hand is above it). Positive scrolls up (content above comes
    into view), unless `config.invert`. Zero within the deadzone, capped at `max_speed`."""
    beyond = abs(offset) - config.deadzone
    if beyond <= 0:
        return 0.0
    speed = min(config.max_speed, config.gain * beyond)
    up = (offset > 0) != config.invert
    return speed if up else -speed


@dataclass(frozen=True)
class PalmReading:
    """What the controller saw in the latest frame, for the debug readout."""

    score: float | None  # Open palm score, None with no Hand
    threshold: float
    speed: float | None  # smoothed wrist speed in hand sizes per second
    speed_limit: float
    counts: bool  # the Open palm score reaches its threshold
    steady: bool  # the wrist speed is within the tolerance


@dataclass(frozen=True)
class FistReading:
    """The latest frame's Fist score against the clutch threshold, for the debug readout."""

    score: float | None  # Fist score, None with no Hand
    threshold: float
    counts: bool  # the score reaches the threshold this frame
    clutch: bool  # the clutch is held (the score has counted for the debounce)
    curl: float | None = None  # the finger curl, None with no Hand
    hold_threshold: float = 0.0
    holding: bool = False  # the cursor is held still while the fingers are curled


@dataclass(frozen=True)
class ScrollReading:
    """The latest frame's two-finger score and scroll state, for the debug readout."""

    score: float | None  # two-finger score, None with no Hand
    threshold: float
    counts: bool  # the score reaches the threshold this frame
    scrolling: bool
    offset: float | None  # hand sizes above the anchor (negative: below), None if not scrolling
    deadzone: float
    speed: float  # pixels per second, positive scrolls up
    max_speed: float


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

    def scroll(self, pixels: int) -> None:
        """Scroll by `pixels`: positive scrolls up (content above comes into view)."""
        ...


class Controller:
    def __init__(
        self,
        timing: TimingConfig,
        output: Output,
        cursor: CursorPath | None = None,
        open_palm: OpenPalmConfig | None = None,
        pinch: PinchConfig | None = None,
        clutch: ClutchConfig | None = None,
        scroll: ScrollConfig | None = None,
    ) -> None:
        self._timing = timing
        self._scroll_config = scroll or ScrollConfig()
        self._two: float | None = None  # two-finger score this frame, None with no Hand
        self._two_since: float | None = None  # start of the current two-finger run
        self._anchor: Point | None = None  # where the scroll started; None when not scrolling
        self._scroll_blocked = False  # after No hand: leave the pose before scrolling again
        self._offset: float | None = None  # hand sizes above the anchor this frame
        self._scroll_speed = 0.0  # pixels per second this frame, positive scrolls up
        self._scroll_carry = 0.0  # the fraction of a pixel not yet scrolled
        self._scrolled_at = 0.0  # time of the last scroll frame
        self._clutch_config = clutch  # None: no clutch (absolute mode)
        self._fist: float | None = None  # Fist score this frame, None with no Hand
        self._curl = 0.0  # how curled the fingers are, ignoring the thumb
        self._fist_since: float | None = None  # start of the current Fist run
        self._clutched = False  # the Fist clutch is held
        self._holding = False  # the cursor is held still while the fingers are curled
        self._unclutched_at: float | None = None  # when the last clutch ended
        self._reach: float | None = None  # how far the index reaches past its base
        self._pinch_config = pinch or PinchConfig()
        self._pinch = PinchLatch(self._pinch_config)
        self._ratio: float | None = None
        self._phase = Phase.IDLE
        self._frozen: Point | None = None  # where the cursor last was (and stays while pinching)
        self._pressed_at = 0.0
        self._pressed_pointer: Point = (0.0, 0.0)
        self._pressed_base: Point = (0.0, 0.0)  # the index finger's base when the Pinch closed
        self._pressed_reach: float | None = None  # the index reach when the Pinch closed
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
        self._lost_since: float | None = None  # time of the first frame with no Hand
        self._no_hand = False  # the No hand state has begun (its release was done)
        self._must_open = False  # after No hand or a clutch: open the Pinch and fingers first
        self._wrist: tuple[float, float, float] | None = None  # x, y, time

    @property
    def hold_progress(self) -> float:
        """How full the Hold ring is, 0 to 1."""
        if self.state is not State.PAUSED or self._hold_since is None:
            return 0.0
        hold = self._timing.unpause_hold_s
        return 1.0 if hold <= 0 else min(1.0, (self._now - self._hold_since) / hold)

    @property
    def no_hand(self) -> bool:
        """True once no Hand has been seen for `timing.no_hand_timeout_ms`."""
        if self._lost_since is None:
            return False
        return self._now - self._lost_since >= self._timing.no_hand_timeout_ms / 1000

    @property
    def phase(self) -> Phase:
        """Where the Pinch is (read-only, for the Preview): idle, pressed or dragging."""
        return self._phase

    @property
    def clutch(self) -> bool:
        """True while the Fist clutch is held (active, with a Hand in view)."""
        return self._clutched and self.state is State.ACTIVE

    @property
    def holding(self) -> bool:
        """True while the cursor is held still because the fingers are curled (active)."""
        return self._holding and self.state is State.ACTIVE and not self.no_hand

    @property
    def fist_reading(self) -> FistReading | None:
        """The latest frame's Fist score and finger curl against their thresholds, or None
        without a clutch (absolute mode)."""
        config = self._clutch_config
        if config is None:
            return None
        score = self._fist
        return FistReading(
            score=score,
            threshold=config.score_threshold,
            counts=score is not None and score >= config.score_threshold,
            clutch=self.clutch,
            curl=None if score is None else self._curl,
            hold_threshold=config.hold_threshold,
            holding=self.holding,
        )

    @property
    def scrolling(self) -> bool:
        """True while a Scroll is in progress (active, with the Hand in view)."""
        return self._anchor is not None and self.state is State.ACTIVE and not self.no_hand

    @property
    def scroll_reading(self) -> ScrollReading:
        """The latest frame's two-finger score and scroll offset and speed."""
        config, score = self._scroll_config, self._two
        return ScrollReading(
            score=score,
            threshold=config.score_threshold,
            counts=score is not None and score >= config.score_threshold,
            scrolling=self.scrolling,
            offset=self._offset if self.scrolling else None,
            deadzone=config.deadzone,
            speed=self._scroll_speed if self.scrolling else 0.0,
            max_speed=config.max_speed,
        )

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
        self._track_loss(landmarks)
        self._ratio = None if landmarks is None else pinch_ratio(landmarks)
        self._pinch.update(self._ratio)
        self._measure(landmarks)
        if not self.reading.counts:
            self._latched = False
            self._reset_run()
            self._track_clutch(landmarks)
            if self._track_scroll(landmarks):
                return  # scrolling: the cursor holds still and no Pinch can start
            self._follow(landmarks)
            return
        self._end_scroll()  # an Open palm is never the two-finger pose
        self._fist_since = None
        self._clutched = False  # an Open palm is never a Fist
        self._holding = False
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

    def _track_loss(self, landmarks: Landmarks | None) -> None:
        """Time the Hand's absence; on entering No hand, release everything once."""
        if landmarks is not None:
            self._lost_since = None
        elif self._lost_since is None:
            self._lost_since = self._now
        if not self.no_hand:
            self._no_hand = False
        elif not self._no_hand:
            self._no_hand = True
            self.release_drag()
            self._pinch.reset()
            self._must_open = True
            self._frozen = None
            self._fist_since = None
            self._clutched = False  # No hand is a clutch of its own
            self._end_scroll()
            self._scroll_blocked = True  # a returning Hand must form the pose again
            if self._cursor is not None:
                self._cursor.reset()

    def _track_clutch(self, landmarks: Landmarks | None) -> None:
        """Time the Fist; a Fist cancels an undecided Pinch at once and clutches after the
        debounce. A short dropout (no landmarks) changes nothing."""
        config = self._clutch_config
        if config is None or landmarks is None:
            return
        reading = self.fist_reading
        if reading is None or not reading.counts:
            self._fist_since = None
            if self._clutched:
                self._clutched = False
                self._unclutched_at = self._now
            return
        if self._phase is Phase.PRESSED:
            self._phase = Phase.IDLE  # a Fist is never a Pinch: cancel it, no click
            self._must_open = True
        if self._fist_since is None:
            self._fist_since = self._now
        debounce = config.debounce_ms / 1000
        if not self._clutched and self._now - self._fist_since >= debounce:
            self._clutched = True
            if self._phase is not Phase.IDLE:
                self.release_drag()  # a held drag goes up where the cursor last was
            self._must_open = True
            if self._cursor is not None:
                self._cursor.reset()

    def _track_scroll(self, landmarks: Landmarks | None) -> bool:
        """Time the two-finger pose, start, run and end the Scroll. True while scrolling.

        A short dropout (no landmarks) keeps the scroll but posts nothing."""
        if self.state is not State.ACTIVE or self._clutched:
            self._end_scroll()
            return False
        if landmarks is None:
            self._scrolled_at = self._now  # the dropout scrolls nothing when the Hand returns
            return self._anchor is not None
        if not self.scroll_reading.counts:
            self._end_scroll()
            self._scroll_blocked = False
            return False
        if self._scroll_blocked:
            return False
        if self._two_since is None:
            self._two_since = self._now
        if self._anchor is None:
            if self._now - self._two_since < self._scroll_config.debounce_ms / 1000:
                return False  # maybe only passing through the pose
            if self._phase is not Phase.IDLE:
                self.release_drag()  # never scroll with the button down
            self._anchor = scroll_point(landmarks)
            self._scrolled_at = self._now
            self._scroll_carry = 0.0
        self._scroll(landmarks, self._anchor)
        return True

    def _scroll(self, landmarks: Landmarks, anchor: Point) -> None:
        """Post this frame's share of the scroll speed set by the offset from the anchor."""
        self._holding = False
        if self._cursor is not None:
            self._cursor.reset()  # drop any movement, so following resumes without a jump
        _, y = scroll_point(landmarks)
        self._offset = (anchor[1] - y) / hand_size(landmarks)  # image y grows downwards
        self._scroll_speed = scroll_speed(self._offset, self._scroll_config)
        elapsed, self._scrolled_at = self._now - self._scrolled_at, self._now
        self._scroll_carry += self._scroll_speed * max(0.0, elapsed)
        pixels = int(self._scroll_carry)  # whole pixels, towards zero; the rest carries over
        self._scroll_carry -= pixels
        if pixels:
            self._output.scroll(pixels)

    def _end_scroll(self) -> None:
        """Stop any Scroll and restart the pose's debounce. A Pinch must open afterwards."""
        self._two_since = None
        if self._anchor is not None:
            self._anchor = None
            self._must_open = True  # a Pinch that closed while scrolling never clicks
        self._offset = None
        self._scroll_speed = 0.0
        self._scroll_carry = 0.0

    def release_drag(self) -> None:
        """End any Pinch in progress and lift the mouse button, whatever the Hand is doing."""
        self._phase = Phase.IDLE
        self._output.release_drag()

    def _follow(self, landmarks: Landmarks | None) -> None:
        """Move the cursor to the Pointer while active, with Pinch clicks and drags."""
        if self._cursor is None:
            return
        if self.state is not State.ACTIVE:
            self._cursor.reset()
            self._frozen = None
            return
        if landmarks is None:
            return  # a short dropout (or No hand): nothing moves, nothing is released here
        if self._clutch_config is None:
            position = self._cursor.position(self._now, landmarks)
            if self._must_open:
                if self._pinch.closed:
                    return  # back from No hand still pinched: wait for it to open
                self._must_open = False
        else:
            self._holding = self._waiting(self._clutch_config) and not self._clutched
            if self._clutched or self._holding:
                self._cursor.reset()  # drop any movement, so following resumes without a jump
                return
            position = self._cursor.position(self._now, landmarks)
        if self._frozen is None:
            self._frozen = position
        if self._phase is Phase.IDLE:
            self._aim(position, landmarks)
        elif self._phase is Phase.PRESSED:
            self._decide(position, landmarks)
        else:
            self._drag(position)

    def _waiting(self, config: ClutchConfig) -> bool:
        """Clutched, or the fingers are curled (maybe closing into a Fist), or back from a
        clutch or No hand still pinched or curled: the cursor must not follow."""
        curled = self._curl >= config.hold_threshold
        if self._clutched:
            return True
        if self._must_open:
            if self._pinch.closed or curled:
                return True
            self._must_open = False
        return self._phase is Phase.IDLE and curled and not self._pinch.closed

    def _aim(self, position: Point, landmarks: Landmarks) -> None:
        """No Pinch yet: follow the Pointer, but freeze once a Pinch starts to form."""
        if self._pinch.closed:
            if self._reopening():
                self._must_open = True  # the index passing the thumb as the fist opens
                return
            self._phase = Phase.PRESSED
            self._pressed_at = self._now
            self._pressed_pointer = landmarks[POINTER]
            self._pressed_base = landmarks[INDEX_MCP]
            self._pressed_reach = self._reach
        elif self._ratio is None or self._ratio >= self._pinch_config.open_threshold:
            self._frozen = position
            self._output.move_cursor(*position)

    def _decide(self, position: Point, landmarks: Landmarks) -> None:
        """A closed Pinch: released in time without moving is a click; moving makes it a drag."""
        frozen = self._frozen or position
        if self._fist_forming():
            self._phase = Phase.IDLE  # the index is curling into a Fist: no click, no drag
            self._must_open = True
            return
        if not self._pinch.closed:
            self._phase = Phase.IDLE
            if self._now - self._pressed_at <= self._pinch_config.click_window_ms / 1000:
                self._output.press(*frozen)
                self._output.release(*frozen)
            return
        size = hand_size(landmarks)
        moved = distance(landmarks[POINTER], self._pressed_pointer)
        if self._clutch_config is not None:
            # The whole hand must move: a fingertip curling towards the palm (a Fist
            # forming) moves the Pointer but not the index finger's base.
            moved = min(moved, distance(landmarks[INDEX_MCP], self._pressed_base))
        if size > 0 and moved > CLICK_TOLERANCE * size:
            self._phase = Phase.DRAGGING
            self._output.press(*frozen)
            self._frozen = position
            self._output.drag_to(*position)

    def _reopening(self) -> bool:
        """With a clutch: the clutch ended less than `REOPEN_S` ago, so the hand is still
        opening out of the Fist and a Pinch now is the index passing the thumb."""
        ended = self._unclutched_at
        return (
            self._clutch_config is not None and ended is not None and self._now - ended < REOPEN_S
        )

    def _fist_forming(self) -> bool:
        """With a clutch: the index tip has folded back towards the palm since the Pinch closed."""
        if self._clutch_config is None or self._reach is None or self._pressed_reach is None:
            return False
        return self._reach < self._pressed_reach - FIST_FORMING

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
        """Score the Open palm, the Fist and the smoothed wrist speed for this frame."""
        self._score = None if landmarks is None else open_palm_score(landmarks, self._palm)
        clutch = self._clutch_config
        if clutch is None or landmarks is None:
            self._fist, self._curl, self._reach = None, 0.0, None
        else:
            self._fist = fist_score(landmarks, clutch)
            self._curl = finger_curl(landmarks, clutch)
            self._reach = index_reach(landmarks)
        self._two = None if landmarks is None else two_finger_score(landmarks, self._scroll_config)
        if self._pinch.closed and self._score is not None:
            self._score = 0.0  # a closed Pinch never counts as an Open palm
        if self._pinch.closed and self._two is not None:
            self._two = 0.0  # nor as the two-finger pose
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
