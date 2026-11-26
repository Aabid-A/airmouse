"""The Scroll's motion (issue #14): smoothing, the grace period and the flick, in both modes.

Continuous scrolling, the Controller's rules and config are in test_scroll.py; this file
reuses its Rig and synthetic Hands.
"""

import dataclasses
import io
import statistics
from typing import Any

import pytest

from airmouse.app import scroll_line
from airmouse.config import ScrollConfig
from airmouse.scroll import ScrollState
from anatomy import synthetic_hand
from hands import open_hand
from lockstep import lockstep
from modes import base_config
from test_pinch import DISPLAY, FRAME_S, Camera, Clock, RecordingOutput, Script, Window
from test_scroll import (
    CONTINUOUS,
    SIZE,
    TOWARDS_CAMERA,
    WRIST_Y,
    Rig,
    occluded,
    overlapped,
    pointer,
    pose,
    two,
)

pytestmark = pytest.mark.usefixtures("control_mode")

AUTO = ScrollConfig()
FLICK_ONLY = ScrollConfig(mode="flick")


def jittery_two(up: float, seed: int) -> list[tuple[float, float]]:
    return list(
        synthetic_hand(
            "two fingers", size=SIZE, centre=(0.5, WRIST_Y - SIZE * up), jitter=0.004, seed=seed
        )
    )


def speeds_while_held(scroll: ScrollConfig, up: float) -> list[float]:
    rig = Rig(scroll=scroll)
    rig.start_scroll()
    for frame in range(30):
        rig.frame(jittery_two(up, frame))
    speeds: list[float] = []
    for frame in range(30, 90):
        rig.frame(jittery_two(up, frame))
        speeds.append(rig.controller.scroll_reading.speed)
    return speeds


def flick(rig: Rig, *, start: float = 0.0, travel: float = 0.6, frames: int = 3) -> None:
    """A quick vertical move: `travel` hand sizes in `frames` frames (6 hand sizes per
    second with the defaults)."""
    for step in range(1, frames + 1):
        rig.frame(two(up=start + travel * step / frames))


def flick_events(rig: Rig) -> list[int]:
    return [event[1] for event in rig.output.events if event[0] == "scroll"]


# --- smoothing ---


def test_the_smoothing_keeps_the_speed_steady_with_a_jittery_hand() -> None:
    raw = speeds_while_held(dataclasses.replace(CONTINUOUS, min_cutoff=30.0, beta=0.0), 0.5)
    smooth = speeds_while_held(CONTINUOUS, 0.5)

    assert statistics.mean(smooth) == pytest.approx(875.0, rel=0.05)
    assert statistics.pstdev(smooth) < statistics.pstdev(raw) / 3
    assert statistics.pstdev(smooth) < 15.0  # pixels per second


def test_easing_out_of_the_deadzone_never_jumps() -> None:
    rig = Rig()
    rig.start_scroll()
    speeds: list[float] = []

    for step in range(60):  # a slow rise through the deadzone edge
        rig.frame(two(up=0.4 * step / 60))
        speeds.append(rig.controller.scroll_reading.speed)

    changes = [abs(b - a) for a, b in zip(speeds, speeds[1:], strict=False)]
    assert speeds[-1] > 100
    assert max(changes) < 40  # pixels per second from one frame to the next


# --- the grace period ---


def test_a_dip_in_the_pose_keeps_the_scroll_and_never_reverses_it() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.settle(two(up=0.5))

    for _ in range(3):  # 100 ms of a hand that does not read as the pose at all
        rig.frame(pose("pointing", up=0.5))
        assert rig.controller.scrolling
        assert rig.state is ScrollState.GRACE
    rig.feed(0.3, two(up=0.5))

    assert rig.state is ScrollState.SCROLLING
    assert all(pixels > 0 for pixels in flick_events(rig))


def test_the_speed_fades_out_during_the_grace_period() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.settle(two(up=0.5))
    held = rig.controller.scroll_reading.speed

    speeds: list[float] = []
    for _ in range(round(AUTO.grace_ms / 1000 / FRAME_S) - 1):
        rig.frame(pose("pointing", up=0.5))
        speeds.append(rig.controller.scroll_reading.speed)

    assert speeds == sorted(speeds, reverse=True)
    assert speeds[0] <= held
    assert speeds[1] < held
    assert speeds[-1] < held / 3


def test_two_fingers_turning_towards_the_camera_keep_a_started_scroll_going() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.settle(two(up=0.5))
    frame = 0

    for pitch in [*TOWARDS_CAMERA, *reversed(TOWARDS_CAMERA)]:
        for _ in range(3):
            hand = synthetic_hand(
                "two fingers",
                size=SIZE,
                centre=(0.5, WRIST_Y - SIZE * 0.5),
                pitch=pitch,
                jitter=0.004,
                seed=frame,
            )
            seen = (hand, overlapped(hand), occluded(hand))[frame % 3]
            rig.frame(seen)
            frame += 1
            assert rig.controller.scrolling

    assert rig.state is ScrollState.SCROLLING


@pytest.mark.parametrize("name", ["pointing", "open together", "fist", "half-open fingers"])
def test_a_real_exit_ends_the_scroll_within_the_grace_period(name: str) -> None:
    rig = Rig()
    rig.start_scroll()
    rig.feed(0.3, two(up=0.5))

    rig.feed(AUTO.grace_ms / 1000 + 2 * FRAME_S, pose(name, up=0.5))

    assert not rig.controller.scrolling


def test_the_grace_period_comes_from_config() -> None:
    rig = Rig(scroll=dataclasses.replace(CONTINUOUS, grace_ms=0.0))
    rig.start_scroll()

    rig.frame(pose("pointing"))

    assert not rig.controller.scrolling


# --- the flick ---


def test_a_quick_move_posts_one_flick_step_then_cools_down() -> None:
    rig = Rig(scroll=AUTO)
    rig.start_scroll()

    flick(rig)
    assert flick_events(rig) == [600]
    assert rig.state is ScrollState.COOLDOWN

    flick(rig, start=0.6, travel=-0.6)  # the return stroke, quick, inside the cooldown
    rig.feed(0.3, two())

    assert flick_events(rig) == [600]  # nothing else at all


def test_a_quick_move_down_flicks_down_and_invert_flips_it() -> None:
    down = Rig(scroll=AUTO)
    down.start_scroll()
    flick(down, travel=-0.6)
    inverted = Rig(scroll=dataclasses.replace(AUTO, invert=True))
    inverted.start_scroll()
    flick(inverted)

    assert flick_events(down) == [-600]
    assert flick_events(inverted) == [-600]


def test_the_next_flick_waits_for_the_cooldown_and_a_settled_hand() -> None:
    rig = Rig(scroll=AUTO)
    rig.start_scroll()
    flick(rig)
    rig.feed(0.6, two(up=0.6))  # held up past the cooldown: nothing, not even continuous
    assert flick_events(rig) == [600]

    flick(rig, start=0.6, travel=0.6)  # not settled in the deadzone since: no flick
    assert flick_events(rig) == [600]

    rig.feed(0.5, two())  # back to the anchor and still
    flick(rig)
    assert flick_events(rig) == [600, 600]


def test_a_slow_move_scrolls_continuously_and_never_flicks() -> None:
    rig = Rig(scroll=AUTO)
    rig.start_scroll()

    for step in range(30):
        rig.frame(two(up=0.6 * step / 30))
    rig.feed(1.0, two(up=0.6))

    events = flick_events(rig)
    assert sum(events) > 300
    assert max(events) < 100  # continuous steps only


def test_one_motion_is_a_continuous_scroll_or_a_flick_never_both() -> None:
    rig = Rig(scroll=AUTO)
    rig.start_scroll()
    for step in range(30):  # a slow move starts a continuous scroll...
        rig.frame(two(up=0.4 * step / 30))
    rig.feed(0.3, two(up=0.4))
    assert flick_events(rig)
    rig.output.events.clear()

    flick(rig, start=0.4, travel=0.6)  # ...so a quick move on from there cannot flick

    assert all(abs(pixels) < 100 for pixels in flick_events(rig))


def test_a_flick_is_not_followed_by_a_continuous_scroll() -> None:
    rig = Rig(scroll=AUTO)
    rig.start_scroll()

    flick(rig)
    rig.feed(1.5, two(up=0.6))  # the Hand stays up well past the cooldown

    assert flick_events(rig) == [600]


def test_continuous_mode_never_flicks() -> None:
    rig = Rig(scroll=CONTINUOUS)
    rig.start_scroll()

    flick(rig)
    rig.feed(0.5, two(up=0.6))

    events = flick_events(rig)
    assert events and max(events) < 100
    assert rig.state is ScrollState.SCROLLING


def test_flick_mode_never_scrolls_continuously() -> None:
    rig = Rig(scroll=FLICK_ONLY)
    rig.start_scroll()

    for step in range(30):
        rig.frame(two(up=0.6 * step / 30))
    rig.feed(1.0, two(up=0.6))
    assert flick_events(rig) == []

    rig.feed(0.5, two())
    flick(rig)
    assert flick_events(rig) == [600]


def test_the_flick_settings_come_from_config() -> None:
    big = Rig(scroll=dataclasses.replace(AUTO, flick_pixels=900, flick_cooldown_ms=100.0))
    big.start_scroll()
    flick(big)
    assert flick_events(big) == [900]
    assert big.state is ScrollState.COOLDOWN
    big.feed(0.15, two(up=0.6))
    assert big.state is ScrollState.SCROLLING  # the shorter cooldown is over

    fussy = Rig(scroll=dataclasses.replace(AUTO, flick_speed=10.0))
    fussy.start_scroll()
    flick(fussy)  # 6 hand sizes per second: too slow for this one
    assert 600 not in flick_events(fussy)

    far = Rig(scroll=dataclasses.replace(AUTO, flick_min_travel=1.0))
    far.start_scroll()
    flick(far)  # 0.6 hand sizes: too short
    assert 600 not in flick_events(far)


def test_the_flick_measure_is_in_the_reading() -> None:
    rig = Rig(scroll=AUTO)
    rig.start_scroll()

    rig.frame(two(up=0.2))
    rig.frame(two(up=0.4))  # 0.4 hand sizes in 2 frames: 6 hand sizes per second
    reading = rig.controller.scroll_reading

    assert reading.flick == pytest.approx(6.0, rel=0.05)
    assert reading.flick_speed == 3.0


# --- the readout in the terminal ---


def test_the_scroll_line_has_every_number_needed_for_tuning() -> None:
    rig = Rig()
    rig.start_scroll()
    rig.settle(two(up=0.35))
    rig.settle(two(up=0.35))

    line = scroll_line(rig.controller.scroll_reading)

    assert line.startswith(
        "scroll: continuous scrolling two=1.00 entry=0.50 exit=0.30 offset=+0.35"
    )
    assert "deadzone=0.15" in line
    assert "speed=+500px/s" in line
    assert "flick=+0.00/3.0" in line


def test_the_scroll_line_after_no_hand_says_blocked_and_has_no_numbers() -> None:
    rig = Rig()
    rig.feed(0.5, None)

    line = scroll_line(rig.controller.scroll_reading)

    assert line == (
        "scroll: continuous blocked two=-- entry=0.50 exit=0.30 offset=-- deadzone=0.15 "
        "speed=+0px/s flick=--/3.0"
    )


def run_with_readout(debug_gestures: bool, frames: int = 75) -> str:
    def script(frame: int) -> Any:
        return open_hand() if frame < 30 else pointer()

    from airmouse.app import run_preview

    out = io.StringIO()
    camera, window = lockstep(Camera(), Window(frames=frames))
    run_preview(
        base_config(),
        camera,
        Script(script),
        window,
        output=RecordingOutput(),
        display=DISPLAY,
        clock=Clock(),
        timer=Clock(),
        out=out,
        debug_gestures=debug_gestures,
    )
    return out.getvalue()


def test_debug_gestures_prints_the_scroll_line_about_once_a_second() -> None:
    printed = run_with_readout(True).splitlines()
    lines = [line for line in printed if line.startswith("scroll: ")]

    # The fake timer runs faster than the frames (the worker and the window share it),
    # so only check the line is there and throttled, never one per frame.
    assert 1 <= len(lines) <= 75 // 3
    assert printed[-1] == "camera off"


def test_without_debug_gestures_nothing_is_printed_for_the_scroll() -> None:
    assert "scroll: " not in run_with_readout(False)
