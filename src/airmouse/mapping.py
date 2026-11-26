"""Control mode: how the Pointer becomes a cursor position (ADR 0002).

The Controller sees one interface, `CursorPath`: a position for each frame's Hand,
and `reset` to start afresh. `control.mode` picks the implementation:

- `RelativePath` (the default) moves the cursor by the Pointer's movement, scaled
  by hand size, from wherever the cursor is, across all displays (clamped to their
  union, see `displays.py`). The first frame after a reset moves nothing, so the
  cursor never jumps when tracking resumes.
- `AbsolutePath` maps the Pointer to a point on the main display through the
  Active region (`AbsoluteMapping`); a Pointer outside the region clamps to the
  nearest screen edge.

Both smooth the Pointer with the One Euro filter. The Pointer arrives already in the
prepared (rotated, mirrored) frame, because the tracker runs on the prepared frame,
so rotate and mirror need no step here. Absolute positions are in display pixels,
the unit the filter's `beta` is tuned for; relative mode filters the Pointer in the
same scale (`RELATIVE_FILTER_SCALE`), so one `[filter]` section suits both.
"""

import math
from typing import Protocol

from airmouse.config import CONTROL_MODES, Config, ConfigError, RelativeConfig
from airmouse.displays import (
    Display,
    FixedScreen,
    Screen,
    clamp_to_displays,
    main_display,
    to_point,
)
from airmouse.filter import OneEuroFilter
from airmouse.frame import Region, active_region, prepared_frame_size
from airmouse.gestures import INDEX_MCP, MIDDLE_MCP, POINTER, WRIST, Landmarks, Point

# Relative mode filters the Pointer in these units per frame height. With the default
# camera, region and a 1440x900 display, absolute mode maps one frame height to about
# 1800 display pixels, so `filter.beta` means the same in both modes.
RELATIVE_FILTER_SCALE = 1800.0
# Relative mode re-reads the display list this often (seconds), on the worker thread.
DISPLAY_REFRESH_S = 1.0


class CursorPath(Protocol):
    """The Pointer over time to a cursor position: what the Controller uses."""

    def position(self, time_s: float, landmarks: Landmarks) -> Point:
        """The cursor position for this frame's Hand, in global display points."""
        ...

    def reset(self) -> None:
        """Start afresh: the next position does not follow on from the last one."""
        ...


class Mapping(Protocol):
    def to_screen(self, pointer: Point) -> Point:
        """A normalised Pointer in the prepared frame to a point on the display, in pixels."""
        ...


class AbsoluteMapping:
    def __init__(self, region: Region, display: tuple[float, float]) -> None:
        self._region = region
        self._display = display

    def to_screen(self, pointer: Point) -> Point:
        left, top, right, bottom = self._region
        width, height = self._display
        fx = min(1.0, max(0.0, (pointer[0] - left) / (right - left)))
        fy = min(1.0, max(0.0, (pointer[1] - top) / (bottom - top)))
        return (fx * (width - 1), fy * (height - 1))


def mapped_region(config: Config, display: tuple[float, float]) -> Region:
    """The Active region the absolute mapping uses for a display of `display` pixels.

    The Preview outlines this same region in absolute mode, so the outline and the
    cursor agree.
    """
    width, height = prepared_frame_size(
        config.camera.width, config.camera.height, config.camera.rotate
    )
    return active_region(
        width, height, config.active_region.width_fraction, display[0] / display[1]
    )


def make_mapping(config: Config, display: tuple[float, float]) -> AbsoluteMapping:
    """The absolute mapping (Active region to the main display) for a display of `display`."""
    return AbsoluteMapping(mapped_region(config, display), display)


class AbsolutePath:
    """Absolute control mode: the filtered Pointer through the Active region."""

    def __init__(self, mapping: Mapping, min_cutoff: float, beta: float) -> None:
        self._mapping = mapping
        self._x = OneEuroFilter(min_cutoff, beta)
        self._y = OneEuroFilter(min_cutoff, beta)

    def position(self, time_s: float, landmarks: Landmarks) -> Point:
        x, y = self._mapping.to_screen(landmarks[POINTER])
        return (self._x(time_s, x), self._y(time_s, y))

    def reset(self) -> None:
        """Start afresh, so a Pointer that reappears elsewhere does not glide from the old spot."""
        self._x.reset()
        self._y.reset()


class RelativePath:
    """Relative control mode: the cursor moves by the filtered Pointer's movement.

    A Pointer movement of one hand size moves the cursor `gain` points, more when the
    hand moves fast (`acceleration`), never more than `max_gain`. Distances are
    measured in frame heights (x is scaled by the prepared frame's aspect), so a
    sideways and an upward movement of the same size move the cursor the same amount.

    The part of the Pointer's movement that only bends or straightens the index
    finger (the fingertip moving along the hand's axis relative to the finger's base)
    is left out, so closing a fist or opening it again does not drag the cursor.
    Moving the hand, or swinging the finger sideways, moves the cursor; tipping only
    the finger up or down at its base does not.

    The cursor starts where it really is (`screen.cursor_position`), on the first
    frame after construction or a reset, and that frame moves nothing. The display
    list is read on that first frame and then every `refresh_s` seconds; after a
    change the cursor is clamped into the new displays, so it never sits outside them.
    The cursor is kept as a continuous position, so slow movement adds up and crosses
    from one display to the next; each returned position is the whole point under it.
    """

    def __init__(
        self,
        config: RelativeConfig,
        screen: Screen,
        *,
        frame_aspect: float,
        min_cutoff: float,
        beta: float,
        fallback: tuple[Display, ...],
        refresh_s: float = DISPLAY_REFRESH_S,
    ) -> None:
        self._config = config
        self._screen = screen
        self._aspect = frame_aspect
        self._filters = tuple(OneEuroFilter(min_cutoff, beta) for _ in range(4))
        self._displays = fallback  # used until the screen reports a display list
        self._refresh_s = refresh_s
        self._refreshed_at: float | None = None
        self._cursor: Point | None = None  # where the cursor is, None: read it on the next frame
        self._known: Point | None = None  # the last cursor position, for a screen that cannot tell
        # Time, filtered Pointer and filtered index base, in frame heights.
        self._last: tuple[float, Point, Point] | None = None

    @property
    def displays(self) -> tuple[Display, ...]:
        """The display list in use (the last one the screen reported)."""
        return self._displays

    def position(self, time_s: float, landmarks: Landmarks) -> Point:
        self._refresh(time_s)
        if self._cursor is None:
            start = self._screen.cursor_position() or self._known or self._home()
            self._cursor = clamp_to_displays(start, self._displays)
        pointer, base = self._filtered(time_s, landmarks[POINTER], landmarks[INDEX_MCP])
        size = self._distance(landmarks[WRIST], landmarks[MIDDLE_MCP])
        last, self._last = self._last, (time_s, pointer, base)
        if last is None or size <= 0 or time_s <= last[0]:
            return to_point(self._cursor)  # the first (or an unmeasurable) frame moves nothing
        wrist, middle = landmarks[WRIST], landmarks[MIDDLE_MCP]
        axis = (
            (middle[0] - wrist[0]) * self._aspect / size,
            (middle[1] - wrist[1]) / size,
        )
        bend = _bend(last[1], last[2], pointer, base, axis)
        dx = (pointer[0] - last[1][0] - bend[0]) / size
        dy = (pointer[1] - last[1][1] - bend[1]) / size
        gain = self.gain(math.hypot(dx, dy) / (time_s - last[0]))
        x, y = self._cursor
        self._cursor = clamp_to_displays((x + dx * gain, y + dy * gain), self._displays)
        self._known = self._cursor
        return to_point(self._cursor)  # the cursor itself stays continuous

    def gain(self, speed: float) -> float:
        """Display points per hand size at `speed` hand sizes per second, capped."""
        config = self._config
        return min(config.max_gain, config.gain * (1 + config.acceleration * speed))

    def reset(self) -> None:
        """Forget the Pointer: the next frame starts from the real cursor position (or, if
        the screen cannot tell, from where this path last put it) and moves nothing."""
        for each in self._filters:
            each.reset()
        self._last = None
        self._cursor = None

    def _refresh(self, time_s: float) -> None:
        due = self._refreshed_at is None or time_s - self._refreshed_at >= self._refresh_s
        if not due:
            return
        self._refreshed_at = time_s
        displays = self._screen.displays()
        if not displays or displays == self._displays:
            return  # unreadable right now, or unchanged: keep what we have
        self._displays = displays
        if self._cursor is not None:
            self._cursor = clamp_to_displays(self._cursor, displays)
        if self._known is not None:
            self._known = clamp_to_displays(self._known, displays)

    def _home(self) -> Point:
        main = main_display(self._displays)
        return main.centre if main is not None else (0.0, 0.0)

    def _filtered(self, time_s: float, pointer: Point, base: Point) -> tuple[Point, Point]:
        """The Pointer and the index base through the One Euro filter, in frame heights."""
        scale = RELATIVE_FILTER_SCALE
        values = (pointer[0] * self._aspect, pointer[1], base[0] * self._aspect, base[1])
        x, y, bx, by = (
            each(time_s, value * scale) / scale
            for each, value in zip(self._filters, values, strict=True)
        )
        return (x, y), (bx, by)

    def _distance(self, a: Point, b: Point) -> float:
        return math.hypot((a[0] - b[0]) * self._aspect, a[1] - b[1])


def _bend(last_tip: Point, last_base: Point, tip: Point, base: Point, axis: Point) -> Point:
    """The part of the fingertip's movement that only bends or straightens the finger.

    A finger bends in the plane of the hand's long axis, so in the picture its tip moves
    along that axis relative to its base. That component of the tip's movement relative
    to the base is the bend; what is left is the hand's movement and the finger's
    sideways swing. `axis` is the hand's axis as a unit vector (wrist to the middle
    finger's base)."""
    change_x = (tip[0] - base[0]) - (last_tip[0] - last_base[0])
    change_y = (tip[1] - base[1]) - (last_tip[1] - last_base[1])
    along = change_x * axis[0] + change_y * axis[1]
    return (along * axis[0], along * axis[1])


def make_cursor_path(
    config: Config, display: tuple[float, float], screen: Screen | None = None
) -> CursorPath:
    """The CursorPath for `config.control.mode`.

    `display` is the main display's size in pixels (absolute mode maps to it, and
    relative mode falls back to it until `screen` reports the displays). `screen`
    tells relative mode where the cursor is and which displays exist.
    """
    mode = config.control.mode
    filtering = config.filter
    if mode == "absolute":
        return AbsolutePath(make_mapping(config, display), filtering.min_cutoff, filtering.beta)
    if mode == "relative":
        width, height = prepared_frame_size(
            config.camera.width, config.camera.height, config.camera.rotate
        )
        return RelativePath(
            config.relative,
            screen or FixedScreen(display),
            frame_aspect=width / height,
            min_cutoff=filtering.min_cutoff,
            beta=filtering.beta,
            fallback=FixedScreen(display).displays(),
        )
    valid = ", ".join(CONTROL_MODES)
    raise ConfigError(f"control.mode: unknown value {mode!r}; valid: {valid}")
