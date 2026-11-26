"""The displays the cursor can reach, as plain geometry (pure, no Quartz).

Coordinates are Quartz global display coordinates, in points: the main display's
top left is (0, 0), y grows downwards, and a display to the left of or above the
main display has negative coordinates. Points, not pixels, so a Retina display
needs no special handling: Quartz already reports its bounds in points.

Relative control mode keeps the cursor inside the union of the display
rectangles. A move that would leave the union is clamped to the nearest point
inside it, so the cursor slides along an edge instead of stopping, and it crosses
from one display to the next wherever they meet. The cursor is a continuous
position and each display a half-open rectangle (its right and bottom edges belong
to the next display), so movement of any size, however slow, crosses a seam;
`to_point` rounds a position down to the whole point an event is posted at, which
stays on the same display.
"""

import math
from dataclasses import dataclass
from typing import Protocol

from airmouse.gestures import Point


@dataclass(frozen=True)
class Display:
    """One display's bounds in global points: the half-open rectangle from (x, y) up to,
    not including, (x + width, y + height)."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        """The right edge, which belongs to whatever lies beyond (half-open)."""
        return self.x + self.width

    @property
    def bottom(self) -> float:
        """The bottom edge, which belongs to whatever lies below (half-open)."""
        return self.y + self.height

    @property
    def centre(self) -> Point:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def contains(self, point: Point) -> bool:
        return self.x <= point[0] < self.right and self.y <= point[1] < self.bottom

    def nearest(self, point: Point) -> Point:
        """The point of this display closest to `point` (itself if it is on the display)."""
        return (
            min(math.nextafter(self.right, -math.inf), max(self.x, point[0])),
            min(math.nextafter(self.bottom, -math.inf), max(self.y, point[1])),
        )


def to_point(position: Point) -> Point:
    """The whole point an event at `position` is posted at: rounded down, so a position
    on a display (half-open) stays on it."""
    return (float(math.floor(position[0])), float(math.floor(position[1])))


def clamp_to_displays(point: Point, displays: tuple[Display, ...]) -> Point:
    """The point of the union of `displays` nearest to `point`. Unchanged if it is inside.

    With no displays at all there is nothing to clamp to, so the point is returned.
    """
    if any(display.contains(point) for display in displays):
        return point
    best: Point = point
    best_distance = math.inf
    for display in displays:
        candidate = display.nearest(point)
        distance = math.hypot(candidate[0] - point[0], candidate[1] - point[1])
        if distance < best_distance:
            best, best_distance = candidate, distance
    return best


def main_display(displays: tuple[Display, ...]) -> Display | None:
    """The display at the global origin (Quartz puts the main display there), else the first."""
    for display in displays:
        if display.x == 0 and display.y == 0:
            return display
    return displays[0] if displays else None


class Screen(Protocol):
    """Where the cursor is and which displays exist. The real one asks Quartz."""

    def displays(self) -> tuple[Display, ...]:
        """The active displays. Empty when they cannot be read right now."""
        ...

    def cursor_position(self) -> Point | None:
        """The cursor's current global position, or None when it cannot be read."""
        ...


class FixedScreen:
    """One display at the origin and an unknown cursor position: no real output, or tests."""

    def __init__(self, size: tuple[float, float]) -> None:
        self._displays = (Display(0.0, 0.0, size[0], size[1]),)

    def displays(self) -> tuple[Display, ...]:
        return self._displays

    def cursor_position(self) -> Point | None:
        return None
