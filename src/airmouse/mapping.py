"""Control mode: how the Pointer becomes a cursor position.

`Mapping` is the one interface (ADR 0002). v1 has `AbsoluteMapping`: the Pointer
maps to a screen point through the Active region, and a Pointer outside the
region clamps to the nearest screen edge. `Relative` can be added here later and
selected by `control.mode`. `CursorPath` adds the One Euro filter on top.

The Pointer arrives already in the prepared (rotated, mirrored) frame, because
the tracker runs on the prepared frame, so rotate and mirror need no step here.
Positions are in display pixels, the unit the filter's `beta` is tuned for.
"""

from typing import Protocol

from airmouse.config import CONTROL_MODES, Config, ConfigError
from airmouse.filter import OneEuroFilter
from airmouse.frame import Region, active_region, prepared_frame_size
from airmouse.gestures import Point


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


def make_mapping(config: Config, display: tuple[float, float]) -> Mapping:
    """The Mapping for `config.control.mode` on a display of `display` pixels."""
    if config.control.mode != "absolute":
        valid = ", ".join(CONTROL_MODES)
        raise ConfigError(f"control.mode: unknown value {config.control.mode!r}; valid: {valid}")
    width, height = prepared_frame_size(
        config.camera.width, config.camera.height, config.camera.rotate
    )
    region = active_region(
        width, height, config.active_region.width_fraction, display[0] / display[1]
    )
    return AbsoluteMapping(region, display)


class CursorPath:
    """The Pointer over time to a smoothed cursor position."""

    def __init__(self, mapping: Mapping, min_cutoff: float, beta: float) -> None:
        self._mapping = mapping
        self._x = OneEuroFilter(min_cutoff, beta)
        self._y = OneEuroFilter(min_cutoff, beta)

    def position(self, time_s: float, pointer: Point) -> Point:
        x, y = self._mapping.to_screen(pointer)
        return (self._x(time_s, x), self._y(time_s, y))

    def reset(self) -> None:
        """Start afresh, so a Pointer that reappears elsewhere does not glide from the old spot."""
        self._x.reset()
        self._y.reset()


def make_cursor_path(config: Config, display: tuple[float, float]) -> CursorPath:
    return CursorPath(make_mapping(config, display), config.filter.min_cutoff, config.filter.beta)
