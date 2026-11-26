"""The Scroll's motion: from the two-finger pose and the Hand's height to scroll events.

The Controller decides when scrolling is allowed at all (active, no Pinch, no Fist,
no Open palm) and feeds every frame here. `Scroll` owns the rest:

- Entry: the two-finger score reaches `score_threshold` for `debounce_ms`. The anchor
  is then the midpoint of the index and middle knuckles (`scroll_point`), and offsets
  are measured in the hand size at that moment, so a Hand that tilts and looks shorter
  does not inflate them.
- Staying: the score only has to stay at `exit_threshold` or more (hysteresis). A
  lower score starts a grace period of `grace_ms`: the offset is no longer read (the
  landmarks are not trusted) and the speed fades from its last value to zero. If the
  score recovers in time scrolling carries on; otherwise it ends.
- Continuous scroll: the offset from the anchor, in hand sizes, is smoothed by a One
  Euro filter of its own; past the deadzone the speed eases in (a smoothstep over
  `ease` hand sizes) to `gain` per hand size, capped at `max_speed` pixels per second.
- Flick: a quick vertical move (at least `flick_speed` hand sizes per second and
  `flick_min_travel` hand sizes over the last `flick_window_ms`) posts one scroll of
  `flick_pixels`, then nothing scrolls for `flick_cooldown_ms`. A flick is armed only
  once the Hand has settled inside the deadzone for a flick window after the cooldown.
- `mode`: "continuous" never flicks, "flick" never scrolls continuously, and "auto"
  does both, but one motion gives one or the other: continuous scroll only starts once
  the offset has been past the deadzone for a whole flick window without a flick, and
  then the flick stays disarmed until the Hand settles back inside the deadzone.

No hand blocks a new scroll until the pose is left and formed again.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from airmouse.config import ScrollConfig
from airmouse.filter import OneEuroFilter
from airmouse.gestures import Landmarks, Point, hand_size, scroll_point

# A frame step longer than this (a stalled worker) is counted as this long, so a stall
# never posts one huge burst of scroll.
MAX_STEP_S = 0.1


class ScrollState(Enum):
    IDLE = "idle"  # not in the pose
    ARMING = "arming"  # in the pose, waiting for the entry debounce
    SCROLLING = "scrolling"
    GRACE = "grace"  # scrolling, but the pose reads below the exit threshold
    COOLDOWN = "cooldown"  # scrolling, but nothing moves for a while after a flick
    BLOCKED = "blocked"  # after No hand: leave the pose before a new scroll


@dataclass(frozen=True)
class ScrollReading:
    """The latest frame's two-finger score and scroll state, for the debug readout."""

    state: ScrollState
    mode: str  # "auto", "continuous" or "flick"
    score: float | None  # two-finger score, None with no Hand
    threshold: float  # entry
    exit_threshold: float  # staying
    counts: bool  # the score reaches the threshold that applies now
    offset: float | None  # smoothed hand sizes above the anchor, None if not scrolling
    deadzone: float
    speed: float  # pixels per second being scrolled, positive scrolls up
    max_speed: float
    flick: float | None  # vertical speed over the flick window, hand sizes per second (up +)
    flick_speed: float

    @property
    def scrolling(self) -> bool:
        return self.state in (ScrollState.SCROLLING, ScrollState.GRACE, ScrollState.COOLDOWN)


class ScrollOutput(Protocol):
    def scroll(self, pixels: int) -> None: ...


def smoothstep(fraction: float) -> float:
    """0 at 0 or less, 1 at 1 or more, an S-curve between with a flat start and end."""
    t = min(1.0, max(0.0, fraction))
    return t * t * (3 - 2 * t)


def scroll_speed(offset: float, config: ScrollConfig) -> float:
    """Continuous scroll speed in pixels per second for a vertical offset from the anchor
    (hand sizes, positive when the Hand is above it). Positive scrolls up (content above
    comes into view), unless `config.invert`. Zero within the deadzone; past it the
    linear `gain` rate, capped at `max_speed`, eased in over `ease` hand sizes so the
    speed starts from zero with no step."""
    beyond = abs(offset) - config.deadzone
    if beyond <= 0:
        return 0.0
    speed = min(config.max_speed, config.gain * beyond)
    if config.ease > 0:
        speed *= smoothstep(beyond / config.ease)
    up = (offset > 0) != config.invert
    return speed if up else -speed


class Scroll:
    def __init__(self, config: ScrollConfig, output: ScrollOutput) -> None:
        self._config = config
        self._output = output
        self._filter = OneEuroFilter(config.min_cutoff, config.beta)
        self._now = 0.0
        self._score: float | None = None
        self._since: float | None = None  # start of the pose run before scrolling
        self._blocked = False
        self._anchor: Point | None = None  # None when not scrolling
        self._scale = 1.0  # the hand size when the scroll started
        self._offset: float | None = None  # smoothed, hand sizes above the anchor
        self._speed = 0.0
        self._carry = 0.0  # the fraction of a pixel not yet scrolled
        self._last = 0.0  # time of the last scroll step
        self._grace_since: float | None = None
        self._grace_speed = 0.0
        self._history: deque[tuple[float, float]] = deque()  # (time, raw offset)
        self._flick: float | None = None
        self._armed = False  # a flick may fire
        self._inside_since: float | None = None  # the offset is inside the deadzone
        self._outside_since: float | None = None
        self._flicked_out = False  # this excursion from the deadzone was a flick
        self._cooldown_until: float | None = None

    @property
    def active(self) -> bool:
        """A scroll is in progress (scrolling, in its grace period or cooling down)."""
        return self._anchor is not None

    @property
    def reading(self) -> ScrollReading:
        config, score, active = self._config, self._score, self.active
        threshold = config.exit_threshold if active else config.score_threshold
        return ScrollReading(
            state=self._state(),
            mode=config.mode,
            score=score,
            threshold=config.score_threshold,
            exit_threshold=config.exit_threshold,
            counts=score is not None and score >= threshold,
            offset=self._offset if active else None,
            deadzone=config.deadzone,
            speed=self._speed if active else 0.0,
            max_speed=config.max_speed,
            flick=self._flick if active else None,
            flick_speed=config.flick_speed,
        )

    def _state(self) -> ScrollState:
        if self._anchor is None:
            if self._blocked:
                return ScrollState.BLOCKED
            return ScrollState.IDLE if self._since is None else ScrollState.ARMING
        if self._grace_since is not None:
            return ScrollState.GRACE
        if self._cooling():
            return ScrollState.COOLDOWN
        return ScrollState.SCROLLING

    def end(self) -> bool:
        """Stop any scroll and restart the entry debounce. True if a scroll was active."""
        was = self.active
        self._since = None
        self._anchor = None
        self._offset = None
        self._speed = 0.0
        self._carry = 0.0
        self._grace_since = None
        self._history.clear()
        self._flick = None
        self._cooldown_until = None
        self._filter.reset()
        return was

    def block(self) -> bool:
        """No hand: stop, and wait until the pose is left before scrolling again."""
        self._blocked = True
        self._score = None
        return self.end()

    def update(
        self, now: float, landmarks: Landmarks | None, score: float | None, *, allowed: bool = True
    ) -> bool:
        """Feed one frame (`landmarks` None: a short dropout). `allowed` False (Paused, a
        Pinch, a Fist) ends any scroll at once. True while a scroll is active."""
        self._now, self._score = now, score
        if not allowed:
            self.end()
            return False
        if landmarks is None or score is None:
            self._last = now  # a dropout scrolls nothing when the Hand returns
            return self.active
        config = self._config
        if self._anchor is None:
            if score < config.score_threshold:
                self._blocked = False
                self._since = None
                return False
            if self._blocked:
                return False
            if self._since is None:
                self._since = now
            if now - self._since < config.debounce_ms / 1000:
                return False  # maybe only passing through the pose
            self._start(landmarks)
            return True
        if score >= config.exit_threshold:
            if self._grace_since is not None:
                self._grace_since = None
                self._history.clear()  # the Hand moved unseen: no flick from that jump
            self._move(landmarks)
            return True
        if self._grace_since is None:
            self._grace_since, self._grace_speed = now, self._speed
        faded = (now - self._grace_since) / (config.grace_ms / 1000) if config.grace_ms else 1.0
        if faded >= 1.0:
            self.end()
            return False
        self._step(0.0 if self._cooling() else self._grace_speed * (1 - faded))
        return True

    def _start(self, landmarks: Landmarks) -> None:
        self._anchor = scroll_point(landmarks)
        self._scale = hand_size(landmarks)
        self._last = self._now
        self._carry = 0.0
        self._filter.reset()
        self._history.clear()
        self._armed = True  # the Hand was held in the pose for the debounce
        self._inside_since, self._outside_since = self._now, None
        self._flicked_out = False

    def _cooling(self) -> bool:
        return self._cooldown_until is not None and self._now < self._cooldown_until

    def _move(self, landmarks: Landmarks) -> None:
        config, now, anchor = self._config, self._now, self._anchor
        if anchor is None:
            return
        raw = (anchor[1] - scroll_point(landmarks)[1]) / self._scale  # image y is down
        offset = self._filter(now, raw)
        self._offset = offset
        travel = self._remember(raw)
        if abs(offset) <= config.deadzone:
            self._outside_since, self._flicked_out = None, False
            if self._inside_since is None:
                self._inside_since = now
        else:
            self._inside_since = None
            if self._outside_since is None:
                self._outside_since = now
        window = config.flick_window_ms / 1000
        flicks = config.mode != "continuous"
        if self._cooling():
            self._step(0.0)
            return
        settled = self._inside_since is not None and now - self._inside_since >= window
        if flicks and settled:
            self._armed = True
        if self._outside_since is not None and now - self._outside_since >= window:
            self._armed = False  # a flick starts from the deadzone, within one flick window
        if flicks and self._armed and self._is_flick(travel):
            self._fire(travel)
            return
        if config.mode == "continuous":
            continuous = True
        elif config.mode == "flick" or self._flicked_out or self._outside_since is None:
            continuous = False
        else:  # auto: past the deadzone for a whole flick window without a flick
            continuous = now - self._outside_since >= window
        speed = scroll_speed(offset, config) if continuous else 0.0
        if speed:
            self._armed = False  # this motion is a continuous scroll: it cannot also flick
        self._step(speed)

    def _remember(self, raw: float) -> float:
        """Keep the raw offsets of the last flick window; return the travel across it and
        set the flick measure (hand sizes per second, up positive)."""
        now, window = self._now, self._config.flick_window_ms / 1000
        self._history.append((now, raw))
        while len(self._history) > 1 and now - self._history[0][0] > window:
            self._history.popleft()
        then, first = self._history[0]
        span = now - then
        self._flick = (raw - first) / span if span > 0 else 0.0
        return raw - first

    def _is_flick(self, travel: float) -> bool:
        config, measure = self._config, self._flick
        return (
            measure is not None
            and abs(measure) >= config.flick_speed
            and abs(travel) >= config.flick_min_travel
        )

    def _fire(self, travel: float) -> None:
        config = self._config
        up = (travel > 0) != config.invert
        self._output.scroll(config.flick_pixels if up else -config.flick_pixels)
        self._armed = False
        self._flicked_out = True
        self._cooldown_until = self._now + config.flick_cooldown_ms / 1000
        self._speed = 0.0
        self._carry = 0.0
        self._last = self._now

    def _step(self, speed: float) -> None:
        """Post this frame's share of `speed` pixels per second, in whole pixels."""
        elapsed = min(MAX_STEP_S, max(0.0, self._now - self._last))
        self._last = self._now
        self._speed = speed
        self._carry += speed * elapsed
        pixels = int(self._carry)  # towards zero; the rest carries over
        self._carry -= pixels
        if pixels:
            self._output.scroll(pixels)
