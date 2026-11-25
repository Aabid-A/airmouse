"""The No hand state at the controller seam: a lost Hand never leaves a button stuck."""

import dataclasses
import io
from typing import Any

from airmouse.app import run_preview
from airmouse.config import Config
from airmouse.controller import Phase, State
from airmouse.renderer import LABEL_TOP, WIDTH, Image, render_preview
from anatomy import synthetic_hand
from hands import open_hand
from test_pinch import AIM, CLOSED, OPEN, Camera, Clock, RecordingOutput, Rig, Script, hand

TIMEOUT_S = Config().timing.no_hand_timeout_ms / 1000


def clicks(rig: Rig) -> list[str]:
    return [kind for kind in rig.output.kinds() if kind != "move"]


def dragging_rig() -> Rig:
    rig = Rig()
    rig.aim()
    rig.feed(0.1, hand(CLOSED))
    rig.drag_sideways()
    assert rig.output.down
    rig.output.events.clear()
    return rig


def test_a_short_dropout_changes_nothing() -> None:
    rig = dragging_rig()

    rig.feed(TIMEOUT_S * 0.6, None)

    assert not rig.controller.no_hand
    assert rig.output.down
    assert rig.output.events == []
    assert rig.controller.state is State.ACTIVE


def test_a_short_dropout_while_aiming_keeps_the_cursor_where_it_was() -> None:
    rig = Rig()
    rig.aim()

    rig.feed(TIMEOUT_S * 0.6, None)
    rig.feed(0.1, hand(AIM))

    assert not rig.controller.no_hand
    assert rig.output.kinds() == ["move"] * len(rig.output.events)  # no release, no press


def test_a_hand_lost_mid_drag_releases_the_button_after_the_timeout() -> None:
    rig = dragging_rig()

    rig.feed(TIMEOUT_S + 0.1, None)

    assert rig.controller.no_hand
    assert not rig.output.down
    assert rig.output.kinds() == ["release_drag"]  # once: nothing moves while there is no Hand
    assert rig.controller.state is State.ACTIVE  # a lost Hand never pauses


def test_a_long_loss_keeps_the_button_up_and_the_cursor_still() -> None:
    rig = dragging_rig()

    rig.feed(2.0, None)

    assert rig.output.kinds() == ["release_drag"]
    assert not rig.output.down


def test_the_timeout_comes_from_config() -> None:
    config = Config(timing=dataclasses.replace(Config().timing, no_hand_timeout_ms=1000.0))
    rig = Rig(config)
    rig.aim()
    rig.feed(0.1, hand(CLOSED))
    rig.drag_sideways()

    rig.feed(0.6, None)
    assert rig.output.down

    rig.feed(0.6, None)
    assert not rig.output.down
    assert rig.controller.no_hand


def test_a_hand_that_returns_open_resumes_from_its_new_place_without_gliding() -> None:
    rig = dragging_rig()
    rig.feed(1.0, None)
    rig.output.events.clear()

    rig.frame(hand(AIM, dx=-0.15))

    assert not rig.controller.no_hand
    assert rig.output.kinds() == ["move"]
    first = rig.output.events[0]
    rig.feed(0.2, hand(AIM, dx=-0.15))
    assert abs(rig.output.events[-1][1] - first[1]) < 1.0  # it started on the Pointer, not stale
    assert "press" not in rig.output.kinds()


def test_a_hand_that_returns_still_pinched_does_not_press_or_drag() -> None:
    rig = dragging_rig()
    rig.feed(1.0, None)
    rig.output.events.clear()

    rig.feed(0.5, hand(CLOSED, dx=0.3))

    assert rig.output.events == []
    assert not rig.output.down
    assert rig.controller.state is State.ACTIVE


def test_after_a_still_pinched_return_the_pinch_must_open_before_a_new_click() -> None:
    rig = dragging_rig()
    rig.feed(1.0, None)
    rig.output.events.clear()
    rig.feed(0.3, hand(CLOSED))

    rig.feed(0.2, hand(OPEN))
    rig.output.events.clear()
    rig.feed(0.1, hand(CLOSED))
    rig.feed(0.1, hand(OPEN))

    assert clicks(rig) == ["press", "release"]  # a normal click again


def test_a_pinch_closing_after_a_short_dropout_still_works() -> None:
    rig = Rig()
    rig.aim()
    rig.feed(TIMEOUT_S * 0.6, None)
    rig.output.events.clear()

    rig.feed(0.1, hand(CLOSED))
    rig.feed(0.1, hand(OPEN))

    assert clicks(rig) == ["press", "release"]


def test_no_hand_while_pressed_but_undecided_cancels_the_click() -> None:
    rig = Rig()
    rig.aim()
    rig.feed(0.05, hand(CLOSED))
    assert rig.controller._phase is Phase.PRESSED

    rig.feed(1.0, None)
    rig.feed(0.1, hand(OPEN))

    assert "press" not in rig.output.kinds()
    assert not rig.output.down


def test_no_hand_while_paused_resets_the_hold_ring_and_stays_paused() -> None:
    rig = Rig(active=False)
    rig.feed(0.5, open_hand())
    assert rig.controller.hold_progress > 0

    rig.feed(TIMEOUT_S + 0.1, None)

    assert rig.controller.state is State.PAUSED
    assert rig.controller.hold_progress == 0.0
    assert rig.output.events == [("release_drag",)]  # nothing was held; the call is harmless
    assert not rig.output.down


def test_nothing_reaches_the_mac_while_paused_and_the_hand_is_lost_and_back() -> None:
    rig = Rig(active=False)

    rig.feed(1.0, None)
    rig.feed(0.3, synthetic_hand("pinch others open"))

    assert rig.output.kinds() == ["release_drag"]  # only the harmless release, no moves
    assert not rig.output.down


class RecordingWindow:
    def __init__(self, frames: int) -> None:
        self.frames = frames
        self.images: list[Image] = []

    def show(self, image: Image) -> None:
        self.images.append(image)

    def quit_requested(self) -> bool:
        return len(self.images) >= self.frames

    def close(self) -> None:
        pass


def lost_script(frame: int) -> Any:
    """Unpause (30 frames), aim, pinch and drag, then no Hand at all."""
    if frame < 30:
        return open_hand()
    if frame < 36:
        return hand(AIM)
    if frame < 40:
        return hand(CLOSED)
    if frame < 50:
        return hand(CLOSED, dx=0.02 * (frame - 40))
    return None


def label_rows(image: Image) -> bytes:
    return bytes(image.pixels[LABEL_TOP * WIDTH * 3 :])


def test_the_app_releases_a_lost_drag_and_the_preview_says_no_hand() -> None:
    output = RecordingOutput()
    window = RecordingWindow(frames=80)

    run_preview(
        Config(),
        Camera(),
        Script(lost_script),
        window,
        output=output,
        display=(1600.0, 1000.0),
        clock=Clock(),
        timer=Clock(),
        out=io.StringIO(),
    )

    expected = render_preview(State.ACTIVE, no_hand=True)
    assert label_rows(window.images[79]) == label_rows(expected)
    assert label_rows(window.images[52]) != label_rows(expected)  # not yet: a short dropout
    assert output.kinds().count("release_drag") == 2  # No hand, then the exit
    assert output.kinds().index("release_drag") < 80  # released well before the app quit
    assert not output.down


def test_the_controller_phase_reads_pressed_then_dragging_then_idle_on_no_hand() -> None:
    rig = Rig()
    rig.aim()
    assert rig.controller.phase is Phase.IDLE
    rig.feed(0.1, hand(CLOSED))
    assert rig.controller.phase is Phase.PRESSED
    rig.drag_sideways()
    assert rig.controller.phase is Phase.DRAGGING

    rig.feed(TIMEOUT_S + 0.1, None)

    assert rig.controller.phase is Phase.IDLE


def test_the_preview_says_pinch_then_drag_as_the_controller_presses_and_drags() -> None:
    window = RecordingWindow(frames=80)

    run_preview(
        Config(),
        Camera(),
        Script(lost_script),
        window,
        output=RecordingOutput(),
        display=(1600.0, 1000.0),
        clock=Clock(),
        timer=Clock(),
        out=io.StringIO(),
    )

    def label(phase: Phase) -> bytes:
        return label_rows(render_preview(State.ACTIVE, phase=phase))

    assert label_rows(window.images[33]) == label(Phase.IDLE)  # aiming
    assert label_rows(window.images[38]) == label(Phase.PRESSED)  # the Pinch closed
    assert label_rows(window.images[46]) == label(Phase.DRAGGING)  # moving while pinched
