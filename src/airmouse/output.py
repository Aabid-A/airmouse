"""The real cursor output: Quartz CGEvent mouse moves (macOS only).

Quartz comes from `pyobjc-framework-Quartz`, a darwin-only dependency, so it is
imported lazily and only by `QuartzOutput.open()`. The class itself takes the
Quartz module as an argument, so tests drive it with a fake on any platform.
Moves, left mouse down, up and dragged, and scroll wheel events in pixels.
It also reads the active displays and the cursor's current position, for relative
control mode. Every coordinate is a Quartz global coordinate in points (the main
display's top left is the origin), so Retina displays need no special handling.
`release_drag` lifts the button if it is down, and is safe to call at any time and
from any thread: the worker thread posts every event, and the main thread calls
`release_drag` only on the way out when the worker is stuck. A lock around the
button state (and each post) makes that safe.
"""

import importlib
import sys
import threading
from typing import Any

from airmouse.displays import Display
from airmouse.gestures import Point

MAX_DISPLAYS = 32  # how many active displays are read at most


class OutputError(Exception):
    """The cursor output cannot start or cannot post an event."""


class QuartzOutput:
    def __init__(self, quartz: Any) -> None:
        self._quartz = quartz
        self._lock = threading.RLock()  # the button state and each post, see the module doc
        self._down = False  # the left button is down
        self._last = (0.0, 0.0)  # where the last event went, in display pixels
        bounds = quartz.CGDisplayBounds(quartz.CGMainDisplayID())
        self._origin = (float(bounds.origin.x), float(bounds.origin.y))
        self.display_size = (float(bounds.size.width), float(bounds.size.height))
        if self.display_size[0] < 1 or self.display_size[1] < 1:
            raise OutputError("airmouse could not read the size of the main display")

    @classmethod
    def open(cls) -> "QuartzOutput":
        if sys.platform != "darwin":
            raise OutputError("moving the cursor is only supported on macOS")
        try:
            return cls(importlib.import_module("Quartz"))
        except ImportError as error:
            raise OutputError(f"the Quartz bindings are not available: {error}") from error

    def displays(self) -> tuple[Display, ...]:
        """The active displays' bounds in global points. Empty if Quartz cannot list them."""
        quartz = self._quartz
        error, ids, count = quartz.CGGetActiveDisplayList(MAX_DISPLAYS, None, None)
        if error or not ids:
            return ()
        found: list[Display] = []
        for display_id in list(ids)[:count]:
            bounds = quartz.CGDisplayBounds(display_id)
            width, height = float(bounds.size.width), float(bounds.size.height)
            if width >= 1 and height >= 1:
                found.append(Display(float(bounds.origin.x), float(bounds.origin.y), width, height))
        return tuple(found)

    def cursor_position(self) -> Point | None:
        """Where the cursor is now, in global points, or None if Quartz cannot say."""
        quartz = self._quartz
        event = quartz.CGEventCreate(None)
        if event is None:
            return None
        location = quartz.CGEventGetLocation(event)
        return (float(location.x), float(location.y))

    def move_cursor(self, x: float, y: float) -> None:
        """Move the cursor to (x, y) in global points from the main display's top left
        (as CGEvent uses), which is also main-display pixels for absolute mode."""
        with self._lock:
            self._post(self._quartz.kCGEventMouseMoved, x, y)

    def press(self, x: float, y: float) -> None:
        """Left mouse button down at (x, y). It stays down until `release` or `release_drag`."""
        with self._lock:
            self._post(self._quartz.kCGEventLeftMouseDown, x, y)
            self._down = True

    def drag_to(self, x: float, y: float) -> None:
        """Move the cursor with the left button held (a dragged event, not a plain move)."""
        with self._lock:
            self._post(self._quartz.kCGEventLeftMouseDragged, x, y)

    def release(self, x: float, y: float) -> None:
        """Left mouse button up at (x, y)."""
        with self._lock:
            self._down = False
            self._post(self._quartz.kCGEventLeftMouseUp, x, y)

    def release_drag(self) -> None:
        """Lift the button if it is down, where the cursor last was. Does nothing otherwise."""
        with self._lock:
            if self._down:
                self.release(*self._last)

    def scroll(self, pixels: int) -> None:
        """A vertical scroll wheel event of `pixels` (pixel units, one wheel): positive
        scrolls up (content above comes into view). It never moves the cursor or the button."""
        quartz = self._quartz
        unit = quartz.kCGScrollEventUnitPixel
        with self._lock:
            self._send(quartz.CGEventCreateScrollWheelEvent(None, unit, 1, pixels), "scroll")

    def _post(self, kind: int, x: float, y: float) -> None:
        quartz = self._quartz
        self._last = (x, y)
        point = (self._origin[0] + x, self._origin[1] + y)
        self._send(
            quartz.CGEventCreateMouseEvent(None, kind, point, quartz.kCGMouseButtonLeft), "mouse"
        )

    def _send(self, event: Any, kind: str) -> None:
        """Post `event`, or say which `kind` of event macOS refused to create."""
        quartz = self._quartz
        if event is None:
            raise OutputError(
                f"macOS refused to create a {kind} event. Check the Accessibility permission "
                "for your terminal app in System Settings > Privacy & Security."
            )
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)
