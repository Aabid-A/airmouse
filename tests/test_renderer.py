import random
from pathlib import Path

import pytest

from airmouse.controller import PalmReading, State
from airmouse.frame import active_region, prepare_point
from airmouse.gestures import Landmarks, is_open_palm
from airmouse.renderer import (
    BACKGROUND,
    BONE,
    CAMERA_ON_DOT,
    HEIGHT,
    JOINT,
    LABEL_TOP,
    PALETTE,
    POINTER_COLOUR,
    POINTER_INDEX,
    REGION_OUTLINE,
    TEXT_ACTIVE,
    TEXT_PAUSED,
    WIDTH,
    DebugReadout,
    Image,
    render_calibrate,
    render_preview,
)
from hands import open_hand, placed, pointing_hand
from png import decode_png

SNAPSHOTS = Path(__file__).parent / "snapshots"


CALIBRATE_REGION = active_region(640, 480, 0.6)
CALIBRATE_VARIANTS = [(rotate, mirror) for rotate in (0, 90, 180, 270) for mirror in (False, True)]


def calibrate_name(rotate: int, mirror: bool) -> str:
    return f"calibrate_r{rotate}{'_mirror' if mirror else ''}"


def calibrate_cases() -> dict[str, Image]:
    """One raw synthetic Hand, prepared with each rotate and mirror, in Calibrate mode.

    The raw Hand is upright and a little to the right, so each snapshot shows
    where that setting puts it. The camera frame is 640x480; a quarter turn
    makes the prepared frame 480x640, which the Preview stretches to its size.
    """
    raw = placed(pointing_hand(), dx=0.2, dy=-0.08)
    cases: dict[str, Image] = {}
    for rotate, mirror in CALIBRATE_VARIANTS:
        landmarks = [prepare_point(point, rotate, mirror) for point in raw]
        width, height = (480, 640) if rotate in (90, 270) else (640, 480)
        region = active_region(width, height, 0.6)
        cases[calibrate_name(rotate, mirror)] = render_calibrate(
            region, landmarks=landmarks, camera_on=True, fps=30.0
        )
    return cases


TIMINGS = (("CAM", 31.2), ("PREP", 0.4), ("TRACK", 12.7), ("DRAW", 38.5), ("WIN", 4.1))


def reading(score: float | None, speed: float | None, *, counts: bool, steady: bool) -> PalmReading:
    return PalmReading(
        score=score,
        threshold=0.6,
        speed=speed,
        speed_limit=2.5,
        counts=counts,
        steady=steady,
    )


def debug_cases() -> dict[str, Image]:
    """The `--debug-gestures` readout in three situations, from made-up numbers."""
    return {
        "debug_open": render_preview(
            State.PAUSED,
            0.6,
            landmarks=placed(open_hand(), dy=-0.08),
            camera_on=True,
            fps=22.0,
            debug=DebugReadout(reading(0.91, 0.8, counts=True, steady=True), TIMINGS),
        ),
        "debug_pointing": render_preview(
            State.ACTIVE,
            landmarks=placed(pointing_hand(), dy=-0.08),
            camera_on=True,
            fps=29.6,
            debug=DebugReadout(reading(0.34, 3.4, counts=False, steady=False), TIMINGS),
        ),
        "debug_no_hand": render_preview(
            State.PAUSED,
            camera_on=True,
            fps=30.0,
            debug=DebugReadout(reading(None, None, counts=False, steady=True), TIMINGS),
        ),
    }


def snapshot_cases() -> dict[str, Image]:
    """Each frame is built from synthetic landmarks only."""
    return {
        **calibrate_cases(),
        **debug_cases(),
        "hand_paused": render_preview(
            State.PAUSED, 0.6, landmarks=placed(open_hand(), dy=-0.08), camera_on=True, fps=30.0
        ),
        "hand_active": render_preview(
            State.ACTIVE, landmarks=placed(pointing_hand(), dy=-0.08), camera_on=True, fps=29.6
        ),
        "no_hand": render_preview(State.PAUSED, camera_on=True, fps=30.0),
        "no_hand_active": render_preview(State.ACTIVE, camera_on=True, fps=30.0, no_hand=True),
    }


def colours_in(image: Image) -> set[tuple[int, int, int]]:
    return {image.get(x, y) for x in range(image.width) for y in range(image.height)}


def pixel_of(landmarks: Landmarks, index: int) -> tuple[int, int]:
    x, y = landmarks[index]
    return round(x * (WIDTH - 1)), round(y * (HEIGHT - 1))


def noisy_camera_image() -> Image:
    rng = random.Random(7)
    return Image(WIDTH, HEIGHT, bytearray(rng.randbytes(WIDTH * HEIGHT * 3)))


def top_right_corner(image: Image) -> bytes:
    rows = (bytes(image.pixels[(y * WIDTH + 200) * 3 : (y * WIDTH + WIDTH) * 3]) for y in range(30))
    return b"".join(rows)


@pytest.mark.parametrize(
    "name",
    ["hand_paused", "hand_active", "no_hand", "no_hand_active", *calibrate_cases(), *debug_cases()],
)
def test_preview_snapshots_match_pixel_for_pixel(name: str) -> None:
    expected = decode_png((SNAPSHOTS / f"{name}.png").read_bytes())
    actual = snapshot_cases()[name]

    assert (actual.width, actual.height) == (expected.width, expected.height)
    assert actual.pixels == expected.pixels


def test_the_png_writer_and_the_test_decoder_agree() -> None:
    image = snapshot_cases()["hand_paused"]

    assert decode_png(image.to_png()).pixels == image.pixels


def test_the_synthetic_open_hand_is_an_open_palm() -> None:
    assert is_open_palm(open_hand())
    assert not is_open_palm(pointing_hand())


def test_the_skeleton_draws_joints_bones_and_the_pointer() -> None:
    hand = pointing_hand()
    image = render_preview(State.ACTIVE, landmarks=hand)

    assert image.get(*pixel_of(hand, 12)) == JOINT
    assert image.get(*pixel_of(hand, POINTER_INDEX)) == POINTER_COLOUR
    wrist_x, wrist_y = pixel_of(hand, 0)
    base_x, base_y = pixel_of(hand, 5)
    assert image.get((wrist_x + base_x) // 2, (wrist_y + base_y) // 2) == BONE


def test_no_landmarks_draws_no_skeleton() -> None:
    colours = colours_in(render_preview(State.ACTIVE))

    assert not colours & {JOINT, BONE, POINTER_COLOUR}


def test_a_hand_partly_out_of_the_frame_still_draws() -> None:
    hand = placed(open_hand(), dx=0.2, dy=-0.4)  # the middle fingertip is above the frame

    image = render_preview(State.ACTIVE, landmarks=hand)

    assert colours_in(image) <= PALETTE
    assert image.get(*pixel_of(hand, 20)) == JOINT


def test_landmarks_of_the_wrong_count_are_not_drawn() -> None:
    assert render_preview(State.ACTIVE, landmarks=open_hand()[:5]).pixels == (
        render_preview(State.ACTIVE).pixels
    )


def test_the_camera_on_indicator_shows_only_when_the_camera_is_on() -> None:
    def has_dot(image: Image) -> bool:
        return any(image.get(x, y) == CAMERA_ON_DOT for x in range(30) for y in range(30))

    assert has_dot(render_preview(State.PAUSED, camera_on=True))
    assert not has_dot(render_preview(State.PAUSED))


def test_the_fps_readout_shows_whole_frames_per_second() -> None:
    thirty = top_right_corner(render_preview(State.PAUSED, fps=30.2))

    assert thirty == top_right_corner(render_preview(State.PAUSED, fps=29.8))
    assert thirty != top_right_corner(render_preview(State.PAUSED, fps=31.0))
    assert thirty != top_right_corner(render_preview(State.PAUSED))


def test_the_default_preview_contains_no_camera_pixels() -> None:
    camera = noisy_camera_image()

    default = render_preview(
        State.PAUSED, 0.4, landmarks=open_hand(), camera_on=True, fps=30.0, camera_image=camera
    )

    plain = render_preview(State.PAUSED, 0.4, landmarks=open_hand(), camera_on=True, fps=30.0)
    assert default.pixels == plain.pixels
    assert colours_in(default) <= PALETTE
    assert BACKGROUND in colours_in(default)


def test_every_snapshot_frame_uses_only_palette_colours() -> None:
    for image in snapshot_cases().values():
        assert colours_in(image) <= PALETTE


def test_the_camera_image_appears_only_with_the_opt_in() -> None:
    camera = noisy_camera_image()

    shown = render_preview(State.ACTIVE, camera_image=camera, show_camera_image=True)

    assert shown.get(2, 120) == camera.get(2, 120)
    assert shown.get(300, 230) == camera.get(300, 230)


def test_opting_in_without_a_camera_image_is_still_the_plain_background() -> None:
    assert render_preview(State.ACTIVE, show_camera_image=True).pixels == (
        render_preview(State.ACTIVE).pixels
    )


def test_a_camera_image_of_the_wrong_size_is_refused() -> None:
    small = Image.blank(10, 10, (0, 0, 0))

    with pytest.raises(ValueError, match="must be 320x240"):
        render_preview(State.ACTIVE, camera_image=small, show_camera_image=True)


def test_calibrate_draws_the_active_region_outline_and_the_hand() -> None:
    hand = placed(open_hand(), dy=-0.08)
    image = render_calibrate(CALIBRATE_REGION, landmarks=hand)

    left, top, right, bottom = CALIBRATE_REGION
    mid_x, mid_y = round((left + right) / 2 * (WIDTH - 1)), round((top + bottom) / 2 * (HEIGHT - 1))
    assert image.get(round(left * (WIDTH - 1)), mid_y) == REGION_OUTLINE
    assert image.get(round(right * (WIDTH - 1)), mid_y) == REGION_OUTLINE
    assert image.get(mid_x, round(top * (HEIGHT - 1))) == REGION_OUTLINE
    assert image.get(mid_x, round(bottom * (HEIGHT - 1))) == REGION_OUTLINE
    assert image.get(*pixel_of(hand, POINTER_INDEX)) == POINTER_COLOUR


def test_calibrate_without_a_hand_still_shows_the_region() -> None:
    image = render_calibrate(CALIBRATE_REGION)

    assert REGION_OUTLINE in colours_in(image)
    assert POINTER_COLOUR not in colours_in(image)


def test_calibrate_has_no_hold_ring_or_state_label() -> None:
    calibrate = render_calibrate(CALIBRATE_REGION)
    paused = render_preview(State.PAUSED, 0.5)
    active = render_preview(State.ACTIVE)

    assert calibrate.pixels != paused.pixels
    assert calibrate.pixels != active.pixels
    assert colours_in(calibrate) <= PALETTE


def test_calibrate_contains_no_camera_pixels_without_the_opt_in() -> None:
    image = render_calibrate(CALIBRATE_REGION, camera_image=noisy_camera_image())

    assert colours_in(image) <= PALETTE


def test_calibrate_shows_the_camera_image_only_with_the_opt_in() -> None:
    image = render_calibrate(
        CALIBRATE_REGION, camera_image=noisy_camera_image(), show_camera_image=True
    )

    assert not colours_in(image) <= PALETTE


def test_calibrate_refuses_a_camera_image_of_the_wrong_size() -> None:
    wrong = Image.blank(10, 10, (0, 0, 0))

    with pytest.raises(ValueError):
        render_calibrate(CALIBRATE_REGION, camera_image=wrong, show_camera_image=True)


@pytest.mark.parametrize(("rotate", "mirror"), CALIBRATE_VARIANTS)
def test_the_pointer_lands_where_the_prepared_frame_puts_it(rotate: int, mirror: bool) -> None:
    raw = placed(pointing_hand(), dx=0.2, dy=-0.08)
    landmarks = [prepare_point(point, rotate, mirror) for point in raw]
    width, height = (480, 640) if rotate in (90, 270) else (640, 480)

    image = render_calibrate(active_region(width, height, 0.6), landmarks=landmarks)

    assert image.get(*pixel_of(landmarks, POINTER_INDEX)) == POINTER_COLOUR


def test_the_default_preview_is_unchanged_by_the_debug_option() -> None:
    hand = placed(open_hand(), dy=-0.08)
    plain = render_preview(State.PAUSED, 0.6, landmarks=hand, camera_on=True, fps=30.0)
    explicit = render_preview(
        State.PAUSED, 0.6, landmarks=hand, camera_on=True, fps=30.0, debug=None
    )

    assert plain.pixels == explicit.pixels


def test_the_readout_only_adds_pixels_in_the_palette_and_never_camera_pixels() -> None:
    for name, image in debug_cases().items():
        assert colours_in(image) <= PALETTE, name
    noisy = noisy_camera_image()
    image = render_preview(
        State.PAUSED,
        camera_image=noisy,
        debug=DebugReadout(reading(0.5, 1.0, counts=False, steady=True), TIMINGS),
    )

    assert colours_in(image) <= PALETTE


def test_the_readout_can_show_camera_pixels_only_with_the_opt_in() -> None:
    noisy = noisy_camera_image()
    readout = DebugReadout(reading(0.5, 1.0, counts=False, steady=True), TIMINGS)

    opted_in = render_preview(
        State.PAUSED, camera_image=noisy, show_camera_image=True, debug=readout
    )
    default = render_preview(State.PAUSED, camera_image=noisy, debug=readout)

    assert colours_in(opted_in) - PALETTE
    assert not colours_in(default) - PALETTE


BAR_LEFT, BAR_TOP = 6, 34 + 7 + 3  # the first bar: the palm score


def filled_width(image: Image, bar_top: int, colour: tuple[int, int, int]) -> int:
    return sum(image.get(x, bar_top + 2) == colour for x in range(BAR_LEFT, BAR_LEFT + 80))


def test_the_score_bar_fills_in_proportion_and_goes_green_when_the_palm_counts() -> None:
    low = render_preview(
        State.PAUSED, debug=DebugReadout(reading(0.25, 0.0, counts=False, steady=True))
    )
    high = render_preview(
        State.PAUSED, debug=DebugReadout(reading(1.0, 0.0, counts=True, steady=True))
    )

    assert filled_width(low, BAR_TOP, TEXT_PAUSED) == 20
    assert filled_width(high, BAR_TOP, TEXT_ACTIVE) == 80 - 1  # the threshold tick covers a pixel


def test_the_threshold_tick_sits_where_the_threshold_is() -> None:
    image = render_preview(
        State.PAUSED, debug=DebugReadout(reading(0.1, 0.0, counts=False, steady=True))
    )

    tick_x = BAR_LEFT + round(0.6 * 80)
    assert image.get(tick_x, BAR_TOP + 2) == JOINT
    assert image.get(tick_x, BAR_TOP - 2) == JOINT  # it reaches above the bar
    assert image.get(tick_x + 4, BAR_TOP - 2) == BACKGROUND


def test_the_speed_bar_is_full_at_twice_the_tolerance() -> None:
    speed_top = BAR_TOP + 20
    image = render_preview(
        State.PAUSED, debug=DebugReadout(reading(0.1, 5.0, counts=False, steady=False))
    )

    assert filled_width(image, speed_top, TEXT_PAUSED) >= 80 - 2  # all but the tick


def test_no_hand_leaves_the_bars_empty_and_says_so_without_inventing_numbers() -> None:
    image = render_preview(
        State.PAUSED, debug=DebugReadout(reading(None, None, counts=False, steady=True))
    )

    assert filled_width(image, BAR_TOP, TEXT_PAUSED) == 0
    assert filled_width(image, BAR_TOP, TEXT_ACTIVE) == 0


@pytest.mark.parametrize(
    "palm",
    [
        reading(float("nan"), float("inf"), counts=False, steady=False),
        reading(1e9, 1e9, counts=True, steady=False),
        reading(-3.0, -3.0, counts=False, steady=True),
    ],
)
def test_odd_numbers_never_break_the_readout(palm: PalmReading) -> None:
    timings = (("CAM", float("nan")), ("TRACK", 1e12), ("WIN", -5.0))

    image = render_preview(State.PAUSED, debug=DebugReadout(palm, timings))

    assert colours_in(image) <= PALETTE


def test_every_timing_row_is_drawn_on_the_right_below_the_fps() -> None:
    plain = render_preview(State.ACTIVE, camera_on=True, fps=30.0)
    debug = render_preview(
        State.ACTIVE,
        camera_on=True,
        fps=30.0,
        debug=DebugReadout(reading(None, None, counts=False, steady=True), TIMINGS),
    )

    def changed_rows(columns: range) -> list[int]:
        return [
            y for y in range(HEIGHT) if any(plain.get(x, y) != debug.get(x, y) for x in columns)
        ]

    rows = changed_rows(range(236, WIDTH - 5))
    assert min(rows) >= 34  # below the FPS readout
    assert len({y for y in rows if (y - 34) % 10 == 0}) == len(TIMINGS)


def test_the_no_hand_state_says_so_and_only_the_label_differs_from_active() -> None:
    active = render_preview(State.ACTIVE, camera_on=True, fps=30.0)
    lost = render_preview(State.ACTIVE, camera_on=True, fps=30.0, no_hand=True)

    assert lost.pixels != active.pixels
    top = LABEL_TOP * WIDTH * 3
    assert lost.pixels[:top] == active.pixels[:top]  # everything above the label is the same


def test_no_hand_while_paused_keeps_the_paused_label() -> None:
    paused = render_preview(State.PAUSED, 0.3)

    assert render_preview(State.PAUSED, 0.3, no_hand=True).pixels == paused.pixels


def test_the_no_hand_preview_uses_only_palette_colours() -> None:
    assert colours_in(snapshot_cases()["no_hand_active"]) <= PALETTE
