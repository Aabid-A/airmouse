import sys
from types import SimpleNamespace
from typing import Any

import pytest

from airmouse.output import OutputError, QuartzOutput


class FakeQuartz:
    """Just enough of Quartz to record the events posted."""

    kCGEventMouseMoved = 5
    kCGMouseButtonLeft = 0
    kCGHIDEventTap = 0

    def __init__(
        self, *, origin: tuple[float, float] = (0, 0), width: float = 1440.0, refuse: bool = False
    ) -> None:
        self.bounds = SimpleNamespace(
            origin=SimpleNamespace(x=origin[0], y=origin[1]),
            size=SimpleNamespace(width=width, height=900.0),
        )
        self.refuse = refuse
        self.posted: list[tuple[Any, Any]] = []

    def CGMainDisplayID(self) -> int:
        return 1

    def CGDisplayBounds(self, display: int) -> Any:
        return self.bounds

    def CGEventCreateMouseEvent(self, source: Any, kind: int, point: Any, button: int) -> Any:
        return None if self.refuse else ("mouse_moved", kind, point, button)

    def CGEventPost(self, tap: int, event: Any) -> None:
        self.posted.append((tap, event))


def test_it_reports_the_main_display_size() -> None:
    assert QuartzOutput(FakeQuartz()).display_size == (1440.0, 900.0)


def test_a_move_posts_a_mouse_moved_event_at_the_point() -> None:
    quartz = FakeQuartz()

    QuartzOutput(quartz).move_cursor(100.5, 200.0)

    assert quartz.posted == [(0, ("mouse_moved", 5, (100.5, 200.0), 0))]


def test_a_move_is_offset_by_the_display_origin() -> None:
    quartz = FakeQuartz(origin=(10, 20))

    QuartzOutput(quartz).move_cursor(1, 2)

    assert quartz.posted[0][1][2] == (11, 22)


def test_a_refused_event_is_a_clear_error_naming_accessibility() -> None:
    with pytest.raises(OutputError, match="Accessibility"):
        QuartzOutput(FakeQuartz(refuse=True)).move_cursor(1, 2)


def test_a_display_with_no_size_is_an_error() -> None:
    with pytest.raises(OutputError, match="size"):
        QuartzOutput(FakeQuartz(width=0))


def test_it_cannot_open_off_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(OutputError, match="macOS"):
        QuartzOutput.open()


def test_a_missing_quartz_module_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "Quartz", None)

    with pytest.raises(OutputError, match="Quartz"):
        QuartzOutput.open()
