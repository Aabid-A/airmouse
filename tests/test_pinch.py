import dataclasses
import io
import threading
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from airmouse.app import run_preview
from airmouse.config import Config, PinchConfig
from airmouse.controller import CLICK_TOLERANCE, Controller, State
from airmouse.gestures import Landmarks, PinchLatch, pinch_ratio
from airmouse.mapping import make_cursor_path
from airmouse.output import OutputError, QuartzOutput
from anatomy import synthetic_hand
from hands import open_hand, pinched, placed, pointing_hand
from lockstep import WAIT_S, lockstep
from modes import base_config, clutch_for

# Every test here runs in both control modes (absolute explicitly, relative explicitly).
pytestmark = pytest.mark.usefixtures("control_mode")

FRAME_S = 1 / 30
DISPLAY = (1600.0, 1000.0)
AIM = 1.3  # a Pointer pose: the thumb is well away from the index tip
OPEN = 0.6  # a Pinch fully open
CLOSED = 0.1  # a Pinch fully closed
FORMING = 0.32  # between the two thresholds


class RecordingOutput:
    """Records every command and whether the mouse button is down."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.events: list[tuple[Any, ...]] = []
        self.down = False
        self.fail_on = fail_on

    def _record(self, name: str, *point: float) -> None:
        self.events.append((name, *point))
        if name == self.fail_on:
            raise OutputError(f"{name} refused")

    def move_cursor(self, x: float, y: float) -> None:
        self._record("move", x, y)

    def press(self, x: float, y: float) -> None:
        self.down = True
        self._record("press", x, y)

    def drag_to(self, x: float, y: float) -> None:
        self._record("drag", x, y)

    def release(self, x: float, y: float) -> None:
        self.down = False
        self._record("release", x, y)

    def release_drag(self) -> None:
        self.down = False
        self._record("release_drag")

    def scroll(self, pixels: int) -> None:
        self._record("scroll", pixels)

    def kinds(self) -> list[str]:
        return [event[0] for event in self.events]


def hand(ratio: float, dx: float = 0.0) -> Landmarks:
    """The pointing Hand shifted by `dx`, its thumb tip `ratio` hand sizes from the index tip."""
    return pinched(placed(pointing_hand(), dx=dx), ratio)


class Rig:
    """A controller on a 1600x1000 display, fed at 30 fps; active unless told otherwise."""

    def __init__(self, config: Config | None = None, *, active: bool = True) -> None:
        config = config or base_config()
        self.output = RecordingOutput()
        self.controller = Controller(
            config.timing,
            self.output,
            make_cursor_path(config, DISPLAY),
            config.open_palm,
            config.pinch,
            clutch_for(config),
        )
        self.time = 0.0
        if active:
            self.feed(1.0, open_hand())
            assert self.controller.state is State.ACTIVE
            self.feed(0.2, hand(AIM))
            self.output.events.clear()

    def feed(self, seconds: float, landmarks: Landmarks | None) -> None:
        for _ in range(round(seconds / FRAME_S)):
            self.frame(landmarks)

    def frame(self, landmarks: Landmarks | None) -> None:
        self.controller.update(self.time, landmarks)
        self.time += FRAME_S

    def aim(self) -> tuple[float, float]:
        """Settle the cursor on the Pointer and return where it is."""
        self.feed(0.2, hand(AIM))
        _, x, y = self.output.events[-1]
        self.output.events.clear()
        return (x, y)

    def drag_sideways(self, start: float = 0.0, end: float = 0.2, ratio: float = CLOSED) -> None:
        steps = 8
        for step in range(steps + 1):
            self.frame(hand(ratio, start + (end - start) * step / steps))


def test_a_pinch_is_thumb_index_distance_over_hand_size() -> None:
    assert pinch_ratio(hand(0.3)) == pytest.approx(0.3)
    assert pinch_ratio(placed(hand(0.3), scale=0.5)) == pytest.approx(0.3)
    assert pinch_ratio(hand(0.3)[:5]) is None


def test_the_latch_closes_below_the_close_threshold_and_opens_above_the_open_one() -> None:
    latch = PinchLatch(PinchConfig())

    seen = [latch.update(ratio) for ratio in (0.5, 0.3, 0.24, 0.3, 0.39, 0.41, 0.3, 0.1)]

    assert seen == [False, False, True, True, True, False, False, True]


def test_the_latch_keeps_its_answer_when_the_hand_cannot_be_measured() -> None:
    latch = PinchLatch(PinchConfig())
    latch.update(0.1)

    assert latch.update(None) is True


def test_the_thresholds_come_from_config() -> None:
    config = dataclasses.replace(
        base_config(), pinch=PinchConfig(close_threshold=0.1, open_threshold=0.2)
    )
    rig = Rig(config)
    rig.output.events.clear()

    rig.feed(0.2, hand(0.15))  # closed under the defaults, not under these
    assert rig.output.kinds() == []  # frozen: forming, but never closed

    rig.feed(0.2, hand(0.3))
    assert set(rig.output.kinds()) == {"move"}


def test_a_ratio_hovering_between_the_thresholds_cannot_flicker_into_clicks() -> None:
    rig = Rig()
    rig.aim()

    for ratio in (0.1, 0.3, 0.26, 0.38, 0.3, 0.39, 0.3):
        rig.frame(hand(ratio))
    rig.feed(0.1, hand(OPEN))

    assert rig.output.kinds()[:2] == ["press", "release"]
    assert rig.output.kinds().count("press") == 1


def test_a_quick_pinch_without_moving_is_a_click_where_the_cursor_was_aimed() -> None:
    rig = Rig()
    aimed = rig.aim()

    rig.feed(0.1, hand(CLOSED))
    rig.feed(0.1, hand(OPEN))

    assert rig.output.events[:2] == [("press", *aimed), ("release", *aimed)]
    assert rig.output.kinds().count("press") == 1
    assert not rig.output.down


def test_a_little_jitter_while_pinching_is_still_a_click() -> None:
    rig = Rig()
    aimed = rig.aim()
    jitter = CLICK_TOLERANCE * 0.2  # in hand sizes, times the hand size of 0.22

    rig.feed(0.05, hand(CLOSED))
    rig.feed(0.05, hand(CLOSED, dx=jitter * 0.22))
    rig.feed(0.05, hand(CLOSED, dx=-jitter * 0.22))
    rig.feed(0.1, hand(OPEN))

    assert rig.output.events[:2] == [("press", *aimed), ("release", *aimed)]


def test_the_cursor_freezes_while_a_pinch_forms_and_follows_again_when_it_opens() -> None:
    rig = Rig()
    rig.aim()

    for step in range(10):
        rig.frame(hand(FORMING, dx=0.01 * step))
    assert rig.output.kinds() == []

    rig.feed(0.2, hand(OPEN, dx=0.1))
    assert rig.output.kinds() == ["move"] * 6


def test_a_pinch_held_without_moving_past_the_click_window_is_no_click() -> None:
    rig = Rig()
    rig.aim()

    rig.feed(0.5, hand(CLOSED))
    rig.feed(0.1, hand(OPEN))

    assert "press" not in rig.output.kinds()
    assert not rig.output.down


def test_the_click_window_comes_from_config() -> None:
    config = dataclasses.replace(base_config(), pinch=PinchConfig(click_window_ms=1000.0))
    rig = Rig(config)
    rig.aim()

    rig.feed(0.5, hand(CLOSED))
    rig.feed(0.1, hand(OPEN))

    assert rig.output.kinds()[:2] == ["press", "release"]


def test_a_held_pinch_while_the_pointer_moves_is_a_drag_from_the_press_point() -> None:
    rig = Rig()
    aimed = rig.aim()

    rig.feed(0.1, hand(CLOSED))
    rig.drag_sideways()

    kinds = rig.output.kinds()
    assert rig.output.events[0] == ("press", *aimed)
    assert kinds.count("press") == 1
    assert "move" not in kinds
    assert kinds.count("drag") >= 5
    assert rig.output.down
    assert rig.output.events[-1][1] > aimed[0] + 100  # dragged to the right


def test_a_drag_ends_when_the_pinch_opens() -> None:
    rig = Rig()
    rig.aim()
    rig.feed(0.1, hand(CLOSED))
    rig.drag_sideways()
    last_drag = rig.output.events[-1]

    rig.frame(hand(OPEN, dx=0.2))

    assert rig.output.events[-1] == ("release", last_drag[1], last_drag[2])
    assert not rig.output.down
    rig.feed(0.1, hand(OPEN, dx=0.2))
    assert rig.output.events[-1][0] == "move"


def test_a_drag_can_start_after_the_click_window() -> None:
    rig = Rig()
    aimed = rig.aim()

    rig.feed(0.6, hand(CLOSED))
    rig.drag_sideways()

    assert rig.output.events[0] == ("press", *aimed)
    assert rig.output.down


def test_a_drag_ends_when_paused() -> None:
    rig = Rig()
    rig.aim()
    rig.feed(0.1, hand(CLOSED))
    rig.drag_sideways()
    assert rig.output.down

    rig.feed(0.6, open_hand())

    assert rig.controller.state is State.PAUSED
    assert rig.output.events[-1] == ("release_drag",)
    assert not rig.output.down
    rig.output.events.clear()
    rig.feed(0.3, hand(CLOSED, dx=0.2))
    assert rig.output.kinds() == []  # paused: nothing more reaches the Mac


def test_a_pinch_while_paused_does_nothing() -> None:
    rig = Rig(active=False)

    rig.feed(1.0, hand(CLOSED))
    rig.feed(0.1, hand(OPEN))
    rig.drag_sideways()

    assert rig.output.events == []


def test_the_pointing_hand_keeps_moving_the_cursor() -> None:
    rig = Rig()

    for step in range(10):
        rig.frame(hand(AIM, dx=0.01 * step))

    assert rig.output.kinds() == ["move"] * 10
    assert rig.output.events[-1][1] > rig.output.events[0][1]


def test_a_pinch_never_pauses_or_unpauses() -> None:
    active = Rig()
    active.feed(2.0, synthetic_hand("pinch others open"))
    active.feed(2.0, pinched(open_hand(), 0.22))  # open fingers, thumb barely off the index tip
    assert active.controller.state is State.ACTIVE
    assert "release_drag" not in active.output.kinds()

    paused = Rig(active=False)
    paused.feed(2.0, synthetic_hand("pinch others open"))
    paused.feed(2.0, pinched(open_hand(), 0.22))
    assert paused.controller.state is State.PAUSED
    assert paused.controller.hold_progress == 0.0


def test_a_closed_pinch_reads_as_no_open_palm_until_it_opens() -> None:
    rig = Rig()

    rig.frame(pinched(open_hand(), 0.22))
    assert rig.controller.reading.score == 0.0
    assert not rig.controller.reading.counts

    rig.frame(pinched(open_hand(), 0.5))
    assert rig.controller.reading.counts


# The app: a held drag is released on the way out, whatever ends the run.


class Script:
    """Hands by frame number: the Hand for frame i is `make(i)`."""

    def __init__(self, make: Callable[[int], Landmarks | None]) -> None:
        self.make = make
        self.frame = 0

    def track(self, frame: Any, time_s: float) -> Landmarks | None:
        self.frame += 1
        return self.make(self.frame - 1)

    def close(self) -> None:
        pass


def drag_script(frame: int) -> Landmarks:
    """Unpause (30 frames), aim, pinch, then drag right until the end."""
    if frame < 30:
        return open_hand()
    if frame < 36:
        return hand(AIM)
    if frame < 40:
        return hand(CLOSED)
    return hand(CLOSED, dx=min(0.2, 0.02 * (frame - 40)))


class Camera:
    def read(self) -> Any:
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def release(self) -> None:
        pass


class Window:
    def __init__(self, frames: int, *, interrupt: bool = False) -> None:
        self.frames = frames
        self.interrupt = interrupt
        self.shown = 0

    def show(self, image: Any) -> None:
        self.shown += 1
        if self.interrupt and self.shown >= self.frames:
            raise KeyboardInterrupt

    def quit_requested(self) -> bool:
        return not self.interrupt and self.shown >= self.frames

    def close(self) -> None:
        pass


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += FRAME_S
        return self.now


def run_app(
    output: RecordingOutput,
    window: Window,
    script: Callable[[int], Landmarks | None] = drag_script,
    *,
    calibrate: bool = False,
    out: io.StringIO | None = None,
) -> int:
    camera, stepped_window = lockstep(Camera(), window)
    return run_preview(
        base_config(),
        camera,
        Script(script),
        stepped_window,
        calibrate=calibrate,
        output=output,
        display=DISPLAY,
        clock=Clock(),
        timer=Clock(),
        out=out or io.StringIO(),
    )


def test_the_app_really_drags_through_the_output() -> None:
    output = RecordingOutput()

    run_app(output, Window(frames=60, interrupt=True))

    assert output.kinds().count("press") == 1
    assert output.kinds().count("drag") > 5


def test_quitting_with_q_mid_drag_lifts_the_button() -> None:
    output = RecordingOutput()

    run_app(output, Window(frames=60))

    assert "press" in output.kinds()
    assert output.events[-1] == ("release_drag",)
    assert not output.down


def test_ctrl_c_mid_drag_lifts_the_button() -> None:
    output = RecordingOutput()

    run_app(output, Window(frames=60, interrupt=True))

    assert "press" in output.kinds()
    assert not output.down


def test_an_output_error_mid_drag_lifts_the_button() -> None:
    output = RecordingOutput(fail_on="drag")

    with pytest.raises(OutputError, match="drag refused"):
        run_app(output, Window(frames=60))

    assert "press" in output.kinds()
    assert not output.down


def test_a_failing_release_on_exit_is_reported_not_raised() -> None:
    output = RecordingOutput(fail_on="release_drag")
    out = io.StringIO()

    status = run_app(output, Window(frames=60), out=out)

    assert status == 0
    assert "could not release the mouse button" in out.getvalue()
    assert out.getvalue().splitlines()[-1] == "camera off"


def test_calibrate_mode_makes_no_clicks_or_drags() -> None:
    output = RecordingOutput()

    run_app(output, Window(frames=60), calibrate=True)

    assert output.events == []


# QuartzOutput against a fake Quartz module (the real one only exists on macOS).


class FakeQuartz:
    kCGEventMouseMoved = 5
    kCGEventLeftMouseDown = 1
    kCGEventLeftMouseUp = 2
    kCGEventLeftMouseDragged = 6
    kCGMouseButtonLeft = 0
    kCGHIDEventTap = 0

    def __init__(self, *, refuse_kind: int | None = None) -> None:
        self.bounds = SimpleNamespace(
            origin=SimpleNamespace(x=0, y=0), size=SimpleNamespace(width=1440.0, height=900.0)
        )
        self.refuse_kind = refuse_kind
        self.posted: list[tuple[int, tuple[float, float]]] = []

    def CGMainDisplayID(self) -> int:
        return 1

    def CGDisplayBounds(self, display: int) -> Any:
        return self.bounds

    def CGEventCreateMouseEvent(self, source: Any, kind: int, point: Any, button: int) -> Any:
        return None if kind == self.refuse_kind else (kind, point)

    def CGEventPost(self, tap: int, event: Any) -> None:
        self.posted.append(event)


def test_press_drag_and_release_post_down_dragged_and_up_events() -> None:
    quartz = FakeQuartz()
    output = QuartzOutput(quartz)

    output.press(10, 20)
    output.drag_to(30, 40)
    output.release(50, 60)

    assert quartz.posted == [(1, (10, 20)), (6, (30, 40)), (2, (50, 60))]


def test_release_drag_lifts_a_held_button_where_the_cursor_last_was() -> None:
    quartz = FakeQuartz()
    output = QuartzOutput(quartz)
    output.press(10, 20)
    output.drag_to(30, 40)

    output.release_drag()
    output.release_drag()

    assert quartz.posted[-1] == (2, (30, 40))
    assert [kind for kind, _ in quartz.posted].count(2) == 1  # the second call did nothing


def test_release_drag_with_no_button_down_posts_nothing() -> None:
    quartz = FakeQuartz()
    output = QuartzOutput(quartz)
    output.move_cursor(1, 2)
    quartz.posted.clear()

    output.release_drag()

    assert quartz.posted == []


def test_a_refused_button_up_is_an_error_and_is_not_retried_forever() -> None:
    quartz = FakeQuartz(refuse_kind=2)
    output = QuartzOutput(quartz)
    output.press(1, 2)

    with pytest.raises(OutputError, match="Accessibility"):
        output.release_drag()
    output.release_drag()  # no second attempt, no second error


def test_a_refused_button_down_leaves_nothing_to_release() -> None:
    quartz = FakeQuartz(refuse_kind=1)
    output = QuartzOutput(quartz)

    with pytest.raises(OutputError, match="Accessibility"):
        output.press(1, 2)
    output.release_drag()

    assert quartz.posted == []


class SlowPressQuartz(FakeQuartz):
    """Holds a button-down event in CGEventPost until told to go on."""

    def __init__(self) -> None:
        super().__init__()
        self.posting_down = threading.Event()
        self.go = threading.Event()

    def CGEventPost(self, tap: int, event: Any) -> None:
        if event[0] == self.kCGEventLeftMouseDown:
            self.posting_down.set()
            assert self.go.wait(WAIT_S)
        super().CGEventPost(tap, event)


def test_release_drag_from_another_thread_waits_for_a_press_in_progress() -> None:
    # The worker posts a press; the main thread lifts the button on the way out.
    quartz = SlowPressQuartz()
    output = QuartzOutput(quartz)
    presser = threading.Thread(target=output.press, args=(10, 20))
    presser.start()
    assert quartz.posting_down.wait(WAIT_S)

    releaser = threading.Thread(target=output.release_drag)
    releaser.start()
    releaser.join(0.05)
    assert releaser.is_alive()  # it waits for the press instead of missing it

    quartz.go.set()
    presser.join(WAIT_S)
    releaser.join(WAIT_S)
    assert not presser.is_alive() and not releaser.is_alive()
    assert [kind for kind, _ in quartz.posted] == [1, 2]  # down, then up: never left down
