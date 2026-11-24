"""The real cursor output: Quartz CGEvent mouse moves (macOS only).

Quartz comes from `pyobjc-framework-Quartz`, a darwin-only dependency, so it is
imported lazily and only by `QuartzOutput.open()`. The class itself takes the
Quartz module as an argument, so tests drive it with a fake on any platform.
Only moves exist so far; click, drag and scroll come with later issues.
"""

import importlib
import sys
from typing import Any


class OutputError(Exception):
    """The cursor output cannot start or cannot post an event."""


class QuartzOutput:
    def __init__(self, quartz: Any) -> None:
        self._quartz = quartz
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

    def move_cursor(self, x: float, y: float) -> None:
        """Move the cursor to (x, y) in main-display pixels, origin top left (as CGEvent uses)."""
        quartz = self._quartz
        point = (self._origin[0] + x, self._origin[1] + y)
        event = quartz.CGEventCreateMouseEvent(
            None, quartz.kCGEventMouseMoved, point, quartz.kCGMouseButtonLeft
        )
        if event is None:
            raise OutputError(
                "macOS refused to create a mouse event. Check the Accessibility permission "
                "for your terminal app in System Settings > Privacy & Security."
            )
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)

    def release_drag(self) -> None:
        pass  # no drag exists yet (a later issue)
