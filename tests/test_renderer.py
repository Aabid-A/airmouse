import random
from pathlib import Path

import numpy as np
import pytest

from airmouse.config import CameraConfig, Config
from airmouse.controller import FistReading, PalmReading, Phase, State
from airmouse.frame import active_region, prepare_point, prepared_frame_size
from airmouse.gestures import Point, is_open_palm
from airmouse.mapping import AbsoluteMapping, mapped_region
from airmouse.renderer import (
    BACKGROUND,
    BONE,
    CAMERA_ON_DOT,
    DEBUG_BAR_OFFSET,
    DEBUG_BAR_WIDTH,
    DEBUG_FIST_TOP,
    DEBUG_LEFT,
    DEBUG_LINE,
    DEBUG_ROW,
    DEBUG_SCROLL_STATE_TOP,
    DEBUG_SCROLL_TOP,
    DEBUG_TOP,
    DEFAULT_VIEW,
    HEIGHT,
    JOINT,
    JOINT_PAUSED,
    LABEL_TOP,
    POINTER_COLOUR,
    POINTER_INDEX,
    PRESS_RING_RADIUS,
    REGION_OUTLINE,
    REGION_PREVIEW,
    STAGE_BOTTOM,
    TEXT_ACTIVE,
    TEXT_PAUSED,
    WIDTH,
    DebugReadout,
    FrameView,
    Image,
    render_calibrate,
    render_preview,
    stage_for,
    to_canvas,
)
from airmouse.scroll import ScrollReading, ScrollState
from anatomy import closing_fist, synthetic_hand
from hands import open_hand, pinched, placed, pointing_hand
from png import decode_png

SNAPSHOTS = Path(__file__).parent / "snapshots"

DISPLAY = (1440.0, 900.0)
ROTATE_MIRROR = [(rotate, mirror) for rotate in (0, 90, 180, 270) for mirror in (False, True)]


def view_for(rotate: int, mirror: bool = False) -> FrameView:
    """The prepared 640x480 camera frame for `rotate`, with the region the cursor maps."""
    config = Config(camera=CameraConfig(rotate=rotate, mirror=mirror))
    width, height = prepared_frame_size(640, 480, rotate)
    return FrameView(width, height, mapped_region(config, DISPLAY))


def calibrate_name(rotate: int, mirror: bool) -> str:
    return f"calibrate_r{rotate}{'_mirror' if mirror else ''}"


def calibrate_cases() -> dict[str, Image]:
    """One raw synthetic Hand, prepared with each rotate and mirror, in Calibrate mode.

    The raw Hand is upright and a little to the right, so each snapshot shows
    where that setting puts it. The camera frame is 640x480; a quarter turn
    makes the prepared frame 480x640, which the Preview fits without stretching.
    """
    raw = placed(pointing_hand(), dx=0.2, dy=-0.08)
    cases: dict[str, Image] = {}
    for rotate, mirror in ROTATE_MIRROR:
        landmarks = [prepare_point(point, rotate, mirror) for point in raw]
        width, height = prepared_frame_size(640, 480, rotate)
        view = FrameView(width, height, active_region(width, height, 0.6))
        cases[calibrate_name(rotate, mirror)] = render_calibrate(
            view, landmarks=landmarks, camera_on=True, fps=30.0
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


def scroll_reading(
    score: float | None,
    *,
    offset: float | None = None,
    speed: float = 0.0,
    flick: float | None = None,
    state: ScrollState | None = None,
) -> ScrollReading:
    scrolling = offset is not None
    return ScrollReading(
        state=state or (ScrollState.SCROLLING if scrolling else ScrollState.IDLE),
        score=score,
        threshold=0.5,
        exit_threshold=0.3,
        counts=score is not None and score >= (0.3 if scrolling else 0.5),
        offset=offset,
        deadzone=0.15,
        speed=speed,
        max_speed=1500.0,
        flick=flick if scrolling else None,
        flick_speed=3.0,
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
        "debug_clutch": render_preview(
            State.ACTIVE,
            landmarks=FIST,
            camera_on=True,
            fps=29.8,
            view=RELATIVE_VIEW,
            clutch=True,
            debug=DebugReadout(
                reading(0.13, 0.4, counts=False, steady=True),
                TIMINGS,
                FistReading(
                    score=0.97,
                    threshold=0.6,
                    counts=True,
                    clutch=True,
                    curl=0.97,
                    hold_threshold=0.3,
                    holding=False,
                ),
            ),
        ),
        "debug_scroll": render_preview(
            State.ACTIVE,
            landmarks=TWO_FINGERS,
            camera_on=True,
            fps=29.9,
            view=RELATIVE_VIEW,
            scrolling=True,
            debug=DebugReadout(
                reading(0.0, 0.3, counts=False, steady=True),
                TIMINGS,
                FistReading(0.0, 0.6, counts=False, clutch=False, curl=0.0, hold_threshold=0.3),
                scroll_reading(0.92, offset=0.35, speed=500.0, flick=0.4),
            ),
        ),
        "debug_no_hand": render_preview(
            State.PAUSED,
            camera_on=True,
            fps=30.0,
            debug=DebugReadout(reading(None, None, counts=False, steady=True), TIMINGS),
        ),
    }


PINCHED = placed(pinched(pointing_hand(), 0.05), dy=-0.08)
FIST = synthetic_hand("fist", centre=(0.5, 0.68))
HALF_CLOSED = placed(closing_fist(0.6), dy=-0.07)
TWO_FINGERS = synthetic_hand("two fingers", centre=(0.5, 0.68))
RELATIVE_VIEW = FrameView(outline=False)  # relative mode: no Active region outline


def state_cases() -> dict[str, Image]:
    """Every Preview state with a Hand in view (and without), from synthetic landmarks only."""
    return {
        "hand_paused": render_preview(
            State.PAUSED, landmarks=placed(open_hand(), dy=-0.08), camera_on=True, fps=30.0
        ),
        "hand_charging": render_preview(
            State.PAUSED, 0.6, landmarks=placed(open_hand(), dy=-0.08), camera_on=True, fps=30.0
        ),
        "hand_active": render_preview(
            State.ACTIVE, landmarks=placed(pointing_hand(), dy=-0.08), camera_on=True, fps=29.6
        ),
        "pinching": render_preview(
            State.ACTIVE, landmarks=PINCHED, camera_on=True, fps=30.0, phase=Phase.PRESSED
        ),
        "dragging": render_preview(
            State.ACTIVE,
            landmarks=placed(PINCHED, dx=0.12),
            camera_on=True,
            fps=30.0,
            phase=Phase.DRAGGING,
        ),
        "hand_active_portrait": render_preview(
            State.ACTIVE,
            landmarks=[prepare_point(point, 90, False) for point in placed(pointing_hand())],
            camera_on=True,
            fps=30.0,
            view=view_for(90),
        ),
        "clutch": render_preview(
            State.ACTIVE, landmarks=FIST, camera_on=True, fps=30.0, view=RELATIVE_VIEW, clutch=True
        ),
        "hold": render_preview(
            State.ACTIVE,
            landmarks=HALF_CLOSED,
            camera_on=True,
            fps=30.0,
            view=RELATIVE_VIEW,
            holding=True,
        ),
        "scroll": render_preview(
            State.ACTIVE,
            landmarks=TWO_FINGERS,
            camera_on=True,
            fps=30.0,
            view=RELATIVE_VIEW,
            scrolling=True,
        ),
        "no_hand": render_preview(State.PAUSED, camera_on=True, fps=30.0),
        "no_hand_active": render_preview(State.ACTIVE, camera_on=True, fps=30.0, no_hand=True),
    }


def snapshot_cases() -> dict[str, Image]:
    return {**calibrate_cases(), **debug_cases(), **state_cases()}


def pixels(image: Image) -> np.ndarray:
    return np.frombuffer(bytes(image.pixels), dtype=np.uint8).reshape(image.height, image.width, 3)


def colours_in(image: Image) -> set[tuple[int, int, int]]:
    flat = np.unique(pixels(image).reshape(-1, 3), axis=0)
    return {(int(r), int(g), int(b)) for r, g, b in flat}


def pixel_at(point: Point, view: FrameView = DEFAULT_VIEW) -> tuple[int, int]:
    """The canvas pixel that holds a normalised point of the prepared frame."""
    x, y = to_canvas(point, view)
    return int(x), int(y)


def noisy_camera_image(width: int = 640, height: int = 480) -> Image:
    rng = random.Random(7)
    return Image(width, height, bytearray(rng.randbytes(width * height * 3)))


def top_right_corner(image: Image) -> np.ndarray:
    return pixels(image)[:36, WIDTH - 160 :].copy()


@pytest.mark.parametrize("name", list(snapshot_cases()))
def test_preview_snapshots_match_pixel_for_pixel(name: str) -> None:
    expected = decode_png((SNAPSHOTS / f"{name}.png").read_bytes())
    actual = snapshot_cases()[name]

    assert (actual.width, actual.height) == (expected.width, expected.height)
    assert actual.pixels == expected.pixels


def test_the_png_writer_and_the_test_decoder_agree() -> None:
    image = snapshot_cases()["hand_charging"]

    assert decode_png(image.to_png()).pixels == image.pixels


def test_the_preview_is_a_fixed_16_by_9_canvas_whatever_the_frame() -> None:
    assert WIDTH * 9 == HEIGHT * 16
    for image in snapshot_cases().values():
        assert (image.width, image.height) == (WIDTH, HEIGHT)


@pytest.mark.parametrize("view", [FrameView(), view_for(90), FrameView(1280, 720)])
def test_the_frame_is_fitted_without_stretching_and_clear_of_the_label(view: FrameView) -> None:
    stage = stage_for(view)

    assert stage.width / stage.height == pytest.approx(view.width / view.height)
    assert stage.left >= 0 and stage.left + stage.width <= WIDTH
    assert stage.top >= 0 and stage.top + stage.height <= STAGE_BOTTOM < LABEL_TOP
    assert to_canvas((0.5, 0.5), view) == pytest.approx((WIDTH / 2, stage.top + stage.height / 2))


def test_the_synthetic_open_hand_is_an_open_palm() -> None:
    assert is_open_palm(open_hand())
    assert not is_open_palm(pointing_hand())


def test_the_skeleton_draws_joints_bones_and_the_pointer() -> None:
    hand = pointing_hand()
    image = render_preview(State.ACTIVE, landmarks=hand)

    assert image.get(*pixel_at(hand[12])) == JOINT
    assert image.get(*pixel_at(hand[POINTER_INDEX])) == POINTER_COLOUR
    middle = ((hand[0][0] + hand[5][0]) / 2, (hand[0][1] + hand[5][1]) / 2)
    x, y = pixel_at(middle)
    near = {image.get(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    assert BONE in near


def test_the_skeleton_glows_around_its_lines() -> None:
    hand = pointing_hand()
    image = render_preview(State.ACTIVE, landmarks=hand)

    x, y = pixel_at(hand[POINTER_INDEX])
    halo = image.get(x + 8, y)  # outside the Pointer, inside its halo
    assert halo != BACKGROUND
    assert halo[2] > BACKGROUND[2] + 20  # a blue-ish glow, not a hard edge
    assert image.get(x + 40, y) == BACKGROUND


def test_lines_are_anti_aliased() -> None:
    image = render_preview(State.ACTIVE, landmarks=pointing_hand())

    # Many in-between shades, not a handful of flat colours.
    assert len(colours_in(image)) > 200


def test_a_paused_hand_is_drawn_in_greys() -> None:
    hand = placed(open_hand(), dy=-0.08)
    image = render_preview(State.PAUSED, landmarks=hand)

    assert image.get(*pixel_at(hand[POINTER_INDEX])) == JOINT_PAUSED
    assert POINTER_COLOUR not in colours_in(image)


def label_band(image: Image) -> np.ndarray:
    return pixels(image)[LABEL_TOP:].copy()


def test_pinching_and_dragging_each_have_their_own_label() -> None:
    def label(phase: Phase) -> bytes:
        return label_band(render_preview(State.ACTIVE, landmarks=PINCHED, phase=phase)).tobytes()

    assert len({label(Phase.IDLE), label(Phase.PRESSED), label(Phase.DRAGGING)}) == 3


def test_a_pinch_rings_the_pointer_and_an_open_hand_does_not() -> None:
    def ring_pixel(phase: Phase) -> tuple[int, int, int]:
        image = render_preview(State.ACTIVE, landmarks=PINCHED, phase=phase)
        x, y = to_canvas(PINCHED[POINTER_INDEX])
        return image.get(int(x + PRESS_RING_RADIUS), int(y))

    for phase in (Phase.PRESSED, Phase.DRAGGING):
        assert ring_pixel(phase)[2] > ring_pixel(Phase.IDLE)[2] + 40


@pytest.mark.parametrize("phase", [Phase.PRESSED, Phase.DRAGGING])
def test_the_pinch_phase_is_not_shown_while_paused_or_with_no_hand(phase: Phase) -> None:
    for state, no_hand in ((State.PAUSED, False), (State.ACTIVE, True)):
        idle = render_preview(state, landmarks=PINCHED, no_hand=no_hand)
        pinch = render_preview(state, landmarks=PINCHED, no_hand=no_hand, phase=phase)
        assert pinch.pixels == idle.pixels


def test_no_landmarks_draws_no_skeleton() -> None:
    colours = colours_in(render_preview(State.ACTIVE))

    assert not colours & {JOINT, BONE, POINTER_COLOUR}


def test_a_hand_partly_out_of_the_frame_still_draws() -> None:
    hand = placed(open_hand(), dx=0.2, dy=-0.6)  # the fingertips are above the canvas

    image = render_preview(State.ACTIVE, landmarks=hand)

    assert to_canvas(hand[12])[1] < 0
    assert image.get(*pixel_at(hand[0])) == JOINT


def test_landmarks_of_the_wrong_count_are_not_drawn() -> None:
    assert render_preview(State.ACTIVE, landmarks=open_hand()[:5]).pixels == (
        render_preview(State.ACTIVE).pixels
    )


def test_the_camera_on_indicator_shows_only_when_the_camera_is_on() -> None:
    def has_dot(image: Image) -> bool:
        return CAMERA_ON_DOT in {image.get(x, y) for x in range(40) for y in range(40)}

    assert has_dot(render_preview(State.PAUSED, camera_on=True))
    assert not has_dot(render_preview(State.PAUSED))


def test_the_fps_readout_shows_whole_frames_per_second() -> None:
    thirty = top_right_corner(render_preview(State.PAUSED, fps=30.2))

    assert np.array_equal(thirty, top_right_corner(render_preview(State.PAUSED, fps=29.8)))
    assert not np.array_equal(thirty, top_right_corner(render_preview(State.PAUSED, fps=31.0)))
    assert not np.array_equal(thirty, top_right_corner(render_preview(State.PAUSED)))


def test_the_default_preview_contains_no_camera_pixels() -> None:
    camera = noisy_camera_image()

    default = render_preview(
        State.PAUSED, 0.4, landmarks=open_hand(), camera_on=True, fps=30.0, camera_image=camera
    )

    plain = render_preview(State.PAUSED, 0.4, landmarks=open_hand(), camera_on=True, fps=30.0)
    assert default.pixels == plain.pixels
    assert default.get(4, HEIGHT // 2) == BACKGROUND


def test_the_camera_image_appears_only_with_the_opt_in_and_only_in_the_frame() -> None:
    camera = noisy_camera_image()

    shown = render_preview(State.ACTIVE, camera_image=camera, show_camera_image=True)

    stage = stage_for(FrameView())
    assert shown.get(round(stage.left), round(stage.top)) == camera.get(0, 0)
    assert shown.get(4, HEIGHT // 2) == BACKGROUND  # beside the fitted frame: no camera pixels


def test_opting_in_without_a_camera_image_is_still_the_plain_background() -> None:
    assert render_preview(State.ACTIVE, show_camera_image=True).pixels == (
        render_preview(State.ACTIVE).pixels
    )


def test_a_camera_image_of_the_wrong_size_is_refused() -> None:
    small = Image.blank(10, 10, (0, 0, 0))

    with pytest.raises(ValueError, match="must be 640x480"):
        render_preview(State.ACTIVE, camera_image=small, show_camera_image=True)


CALIBRATE_VIEW = FrameView(640, 480, active_region(640, 480, 0.6))


def outline_pixels(view: FrameView) -> list[tuple[int, int]]:
    """The middle of each edge of the Active region, on the canvas."""
    left, top, right, bottom = view.region
    mid_x, mid_y = (left + right) / 2, (top + bottom) / 2
    return [
        pixel_at((left, mid_y), view),
        pixel_at((right, mid_y), view),
        pixel_at((mid_x, top), view),
        pixel_at((mid_x, bottom), view),
    ]


def test_calibrate_draws_the_active_region_outline_and_the_hand() -> None:
    hand = placed(open_hand(), dy=-0.08)
    image = render_calibrate(CALIBRATE_VIEW, landmarks=hand)
    outline = render_calibrate(CALIBRATE_VIEW)  # the Hand's glow would tint the outline

    for x, y in outline_pixels(CALIBRATE_VIEW):
        assert outline.get(x, y) == REGION_OUTLINE
    assert image.get(*pixel_at(hand[POINTER_INDEX])) == POINTER_COLOUR


def test_the_preview_draws_a_quiet_active_region_outline() -> None:
    view = view_for(0)
    image = render_preview(State.ACTIVE, view=view)

    for x, y in outline_pixels(view):
        assert image.get(x, y) == REGION_PREVIEW
        assert image.get(x + 3, y + 3) == BACKGROUND or image.get(x - 3, y - 3) == BACKGROUND


def test_calibrate_without_a_hand_still_shows_the_region() -> None:
    image = render_calibrate(CALIBRATE_VIEW)

    assert REGION_OUTLINE in colours_in(image)
    assert POINTER_COLOUR not in colours_in(image)


def test_calibrate_has_no_hold_ring_or_state_label() -> None:
    calibrate = render_calibrate(CALIBRATE_VIEW)
    paused = render_preview(State.PAUSED, 0.5)
    active = render_preview(State.ACTIVE)

    assert calibrate.pixels != paused.pixels
    assert calibrate.pixels != active.pixels
    assert TEXT_PAUSED not in colours_in(calibrate)
    assert TEXT_ACTIVE not in colours_in(calibrate)


def test_calibrate_contains_no_camera_pixels_without_the_opt_in() -> None:
    image = render_calibrate(CALIBRATE_VIEW, camera_image=noisy_camera_image())

    assert image.pixels == render_calibrate(CALIBRATE_VIEW).pixels


def test_calibrate_shows_the_camera_image_only_with_the_opt_in() -> None:
    camera = noisy_camera_image()
    image = render_calibrate(CALIBRATE_VIEW, camera_image=camera, show_camera_image=True)

    stage = stage_for(CALIBRATE_VIEW)
    assert image.get(round(stage.left), round(stage.top)) == camera.get(0, 0)


def test_calibrate_refuses_a_camera_image_of_the_wrong_size() -> None:
    wrong = Image.blank(10, 10, (0, 0, 0))

    with pytest.raises(ValueError):
        render_calibrate(CALIBRATE_VIEW, camera_image=wrong, show_camera_image=True)


def raw_point_for(prepared: Point, rotate: int, mirror: bool) -> Point:
    """The raw camera point that `prepare_point` turns into `prepared` (its inverse)."""
    x, y = prepared
    if mirror:
        x = 1 - x
    return prepare_point((x, y), (360 - rotate) % 360, False)


@pytest.mark.parametrize(("rotate", "mirror"), ROTATE_MIRROR)
def test_the_pointer_skeleton_and_region_outline_agree_with_the_frame(
    rotate: int, mirror: bool
) -> None:
    """No drift: a Pointer on a corner of the Active region is drawn on that outline corner.

    The Hand is placed in the raw camera frame, prepared by `frame.py`, and the
    region is the one the cursor mapping uses, so the drawn Pointer, the drawn
    outline and the cursor all agree for every rotate and mirror.
    """
    view = view_for(rotate, mirror)
    mapping = AbsoluteMapping(view.region, DISPLAY)
    left, top, right, bottom = view.region
    corners = [((left, top), (0.0, 0.0)), ((right, bottom), (DISPLAY[0] - 1, DISPLAY[1] - 1))]
    outline = render_preview(State.ACTIVE, view=view)
    for corner, screen in corners:
        raw_pointer = raw_point_for(corner, rotate, mirror)
        hand = pointing_hand()
        dx, dy = raw_pointer[0] - hand[POINTER_INDEX][0], raw_pointer[1] - hand[POINTER_INDEX][1]
        landmarks = [prepare_point(point, rotate, mirror) for point in placed(hand, dx=dx, dy=dy)]

        image = render_preview(State.ACTIVE, landmarks=landmarks, view=view)

        assert landmarks[POINTER_INDEX] == pytest.approx(corner)
        assert mapping.to_screen(landmarks[POINTER_INDEX]) == pytest.approx(screen)
        x, y = pixel_at(landmarks[POINTER_INDEX], view)
        assert outline.get(x, y) == REGION_PREVIEW  # the outline's corner pixel...
        assert image.get(x, y) == POINTER_COLOUR  # ...is where the Pointer is drawn
        wrist = pixel_at(landmarks[0], view)
        if 0 <= wrist[0] < WIDTH and 0 <= wrist[1] < HEIGHT:
            assert image.get(*wrist) == JOINT


@pytest.mark.parametrize(("rotate", "mirror"), ROTATE_MIRROR)
def test_the_pointer_lands_where_the_prepared_frame_puts_it_in_calibrate(
    rotate: int, mirror: bool
) -> None:
    raw = placed(pointing_hand(), dx=0.2, dy=-0.08)
    landmarks = [prepare_point(point, rotate, mirror) for point in raw]
    width, height = prepared_frame_size(640, 480, rotate)
    view = FrameView(width, height, active_region(width, height, 0.6))

    image = render_calibrate(view, landmarks=landmarks)

    assert image.get(*pixel_at(landmarks[POINTER_INDEX], view)) == POINTER_COLOUR


def test_a_canvas_pixel_is_square_in_the_frame() -> None:
    for view in (FrameView(), view_for(90)):
        origin, across, down = (to_canvas(p, view) for p in ((0, 0), (1, 0), (0, 1)))
        assert (across[0] - origin[0]) / view.width == pytest.approx(
            (down[1] - origin[1]) / view.height
        )


def test_the_default_preview_is_unchanged_by_the_debug_option() -> None:
    hand = placed(open_hand(), dy=-0.08)
    plain = render_preview(State.PAUSED, 0.6, landmarks=hand, camera_on=True, fps=30.0)
    explicit = render_preview(
        State.PAUSED, 0.6, landmarks=hand, camera_on=True, fps=30.0, debug=None
    )

    assert plain.pixels == explicit.pixels


def test_the_readout_never_shows_camera_pixels_without_the_opt_in() -> None:
    readout = DebugReadout(reading(0.5, 1.0, counts=False, steady=True), TIMINGS)

    with_camera = render_preview(State.PAUSED, camera_image=noisy_camera_image(), debug=readout)

    assert with_camera.pixels == render_preview(State.PAUSED, debug=readout).pixels


def test_the_readout_can_show_camera_pixels_only_with_the_opt_in() -> None:
    noisy = noisy_camera_image()
    readout = DebugReadout(reading(0.5, 1.0, counts=False, steady=True), TIMINGS)

    opted_in = render_preview(
        State.PAUSED, camera_image=noisy, show_camera_image=True, debug=readout
    )
    default = render_preview(State.PAUSED, camera_image=noisy, debug=readout)

    assert opted_in.pixels != default.pixels


BAR_LEFT, BAR_TOP = DEBUG_LEFT, DEBUG_TOP + DEBUG_BAR_OFFSET  # the first bar: the palm score


def filled_width(image: Image, bar_top: int, colour: tuple[int, int, int]) -> int:
    row = range(BAR_LEFT, BAR_LEFT + DEBUG_BAR_WIDTH)
    return sum(image.get(x, bar_top + 2) == colour for x in row)


def test_the_score_bar_fills_in_proportion_and_goes_green_when_the_palm_counts() -> None:
    low = render_preview(
        State.PAUSED, debug=DebugReadout(reading(0.25, 0.0, counts=False, steady=True))
    )
    high = render_preview(
        State.PAUSED, debug=DebugReadout(reading(1.0, 0.0, counts=True, steady=True))
    )

    assert filled_width(low, BAR_TOP, TEXT_PAUSED) == DEBUG_BAR_WIDTH // 4
    assert filled_width(high, BAR_TOP, TEXT_ACTIVE) == DEBUG_BAR_WIDTH - 1  # the tick covers one


def test_the_threshold_tick_sits_where_the_threshold_is() -> None:
    image = render_preview(
        State.PAUSED, debug=DebugReadout(reading(0.1, 0.0, counts=False, steady=True))
    )

    tick_x = BAR_LEFT + round(0.6 * DEBUG_BAR_WIDTH)
    assert image.get(tick_x, BAR_TOP + 2) == JOINT
    assert image.get(tick_x, BAR_TOP - 2) == JOINT  # it reaches above the bar
    assert image.get(tick_x + 4, BAR_TOP - 2) == BACKGROUND


def test_the_speed_bar_is_full_at_twice_the_tolerance() -> None:
    image = render_preview(
        State.PAUSED, debug=DebugReadout(reading(0.1, 5.0, counts=False, steady=False))
    )

    assert filled_width(image, BAR_TOP + DEBUG_ROW, TEXT_PAUSED) >= DEBUG_BAR_WIDTH - 2


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

    assert (image.width, image.height) == (WIDTH, HEIGHT)


def test_every_timing_row_is_drawn_on_the_right_below_the_fps() -> None:
    plain = pixels(render_preview(State.ACTIVE, camera_on=True, fps=30.0))
    debug = pixels(
        render_preview(
            State.ACTIVE,
            camera_on=True,
            fps=30.0,
            debug=DebugReadout(reading(None, None, counts=False, steady=True), TIMINGS),
        )
    )

    right = slice(WIDTH - 100, WIDTH - DEBUG_LEFT)
    changed = np.any(plain[:, right] != debug[:, right], axis=(1, 2))
    rows = [y for y in range(HEIGHT) if changed[y]]
    assert min(rows) >= DEBUG_TOP  # below the FPS readout
    assert len({y for y in rows if (y - DEBUG_TOP) % DEBUG_LINE == 0}) == len(TIMINGS)


def test_the_no_hand_state_says_so_and_only_the_label_differs_from_active() -> None:
    active = render_preview(State.ACTIVE, camera_on=True, fps=30.0)
    lost = render_preview(State.ACTIVE, camera_on=True, fps=30.0, no_hand=True)

    assert lost.pixels != active.pixels
    top = LABEL_TOP * WIDTH * 3
    assert lost.pixels[:top] == active.pixels[:top]  # everything above the label is the same


def test_no_hand_while_paused_keeps_the_paused_label() -> None:
    paused = render_preview(State.PAUSED, 0.3)

    assert render_preview(State.PAUSED, 0.3, no_hand=True).pixels == paused.pixels


def test_every_state_has_a_render_of_its_own() -> None:
    renders = state_cases()
    labels = {
        name: label_band(renders[name]).tobytes()
        for name in (
            "hand_paused",
            "hand_active",
            "pinching",
            "dragging",
            "no_hand_active",
            "clutch",
            "hold",
        )
    }

    assert len(set(labels.values())) == len(labels)
    assert renders["hand_charging"].pixels != renders["hand_paused"].pixels


def test_rendering_is_repeatable() -> None:
    first = render_preview(State.PAUSED, 0.37, landmarks=open_hand(), camera_on=True, fps=30.0)
    second = render_preview(State.PAUSED, 0.37, landmarks=open_hand(), camera_on=True, fps=30.0)

    assert first.pixels == second.pixels


def test_the_clutch_says_so_and_only_the_label_differs_from_active() -> None:
    active = render_preview(State.ACTIVE, landmarks=FIST, camera_on=True, fps=30.0)
    clutch = render_preview(State.ACTIVE, landmarks=FIST, camera_on=True, fps=30.0, clutch=True)

    assert clutch.pixels != active.pixels
    top = LABEL_TOP * WIDTH * 3
    assert clutch.pixels[:top] == active.pixels[:top]


def test_paused_and_no_hand_outrank_the_clutch_and_a_clutch_shows_no_pinch() -> None:
    paused = render_preview(State.PAUSED, 0.3, landmarks=PINCHED)
    lost = render_preview(State.ACTIVE, no_hand=True)
    clutched = render_preview(State.ACTIVE, landmarks=PINCHED, clutch=True)

    assert render_preview(State.PAUSED, 0.3, landmarks=PINCHED, clutch=True).pixels == (
        paused.pixels
    )
    assert render_preview(State.ACTIVE, no_hand=True, clutch=True).pixels == lost.pixels
    for phase in (Phase.PRESSED, Phase.DRAGGING):
        pressed = render_preview(State.ACTIVE, landmarks=PINCHED, clutch=True, phase=phase)
        assert pressed.pixels == clutched.pixels


def test_relative_mode_hides_the_active_region_outline_and_nothing_else() -> None:
    outlined = render_preview(State.ACTIVE, camera_on=True)
    hidden = render_preview(State.ACTIVE, camera_on=True, view=FrameView(outline=False))

    assert REGION_PREVIEW in colours_in(outlined)
    assert REGION_PREVIEW not in colours_in(hidden)
    x, y = (int(v) for v in to_canvas((0.5, 0.5)))
    assert hidden.get(x, y) == outlined.get(x, y) == BACKGROUND


def fist_readout(score: float | None, *, counts: bool) -> DebugReadout:
    fist = FistReading(score=score, threshold=0.6, counts=counts, clutch=False)
    return DebugReadout(reading(0.1, 0.0, counts=False, steady=True), (), fist)


def test_the_fist_bar_fills_in_proportion_with_a_tick_at_the_threshold() -> None:
    bar_top = DEBUG_FIST_TOP + DEBUG_BAR_OFFSET
    low = render_preview(State.ACTIVE, debug=fist_readout(0.25, counts=False))
    high = render_preview(State.ACTIVE, debug=fist_readout(1.0, counts=True))

    assert filled_width(low, bar_top, TEXT_PAUSED) == DEBUG_BAR_WIDTH // 4
    assert filled_width(high, bar_top, TEXT_ACTIVE) == DEBUG_BAR_WIDTH - 1
    assert low.get(BAR_LEFT + round(0.6 * DEBUG_BAR_WIDTH), bar_top + 2) == JOINT


def test_the_fist_bar_is_below_the_palm_lines_and_empty_with_no_hand() -> None:
    bar_top = DEBUG_FIST_TOP + DEBUG_BAR_OFFSET
    without = render_preview(State.ACTIVE, debug=fist_readout(None, counts=False))
    plain = render_preview(
        State.ACTIVE, debug=DebugReadout(reading(0.1, 0.0, counts=False, steady=True))
    )

    assert DEBUG_FIST_TOP >= DEBUG_TOP + 2 * DEBUG_ROW + 2 * DEBUG_LINE
    assert filled_width(without, bar_top, TEXT_PAUSED) == 0
    assert filled_width(without, bar_top, TEXT_ACTIVE) == 0
    assert without.pixels != plain.pixels  # the empty bar and its text are still drawn
    top = DEBUG_FIST_TOP * WIDTH * 3
    assert without.pixels[:top] == plain.pixels[:top]  # nothing above it changed


def test_the_hold_says_so_and_only_the_label_differs_from_active() -> None:
    active = render_preview(State.ACTIVE, landmarks=HALF_CLOSED, camera_on=True)
    hold = render_preview(State.ACTIVE, landmarks=HALF_CLOSED, camera_on=True, holding=True)

    assert hold.pixels != active.pixels
    top = LABEL_TOP * WIDTH * 3
    assert hold.pixels[:top] == active.pixels[:top]


def test_paused_no_hand_and_the_clutch_outrank_the_hold() -> None:
    def pair(state: State, *, no_hand: bool = False, clutch: bool = False) -> tuple[Image, Image]:
        def draw(holding: bool) -> Image:
            return render_preview(
                state, landmarks=PINCHED, no_hand=no_hand, clutch=clutch, holding=holding
            )

        return draw(False), draw(True)

    for plain, held in (
        pair(State.PAUSED),
        pair(State.ACTIVE, no_hand=True),
        pair(State.ACTIVE, clutch=True),
    ):
        assert held.pixels == plain.pixels


def test_the_curl_bar_shows_the_finger_curl_against_the_hold_threshold() -> None:
    def curl_readout(curl: float, *, holding: bool) -> DebugReadout:
        fist = FistReading(
            score=0.0,
            threshold=0.6,
            counts=False,
            clutch=False,
            curl=curl,
            hold_threshold=0.3,
            holding=holding,
        )
        return DebugReadout(reading(0.1, 0.0, counts=False, steady=True), (), fist)

    bar_top = DEBUG_FIST_TOP + DEBUG_ROW + DEBUG_BAR_OFFSET
    low = render_preview(State.ACTIVE, debug=curl_readout(0.25, holding=False))
    high = render_preview(State.ACTIVE, debug=curl_readout(1.0, holding=True))

    assert filled_width(low, bar_top, TEXT_ACTIVE) == DEBUG_BAR_WIDTH // 4
    assert filled_width(high, bar_top, TEXT_PAUSED) == DEBUG_BAR_WIDTH - 1
    assert low.get(BAR_LEFT + round(0.3 * DEBUG_BAR_WIDTH), bar_top + 2) == JOINT


def scroll_debug(reading_: ScrollReading) -> DebugReadout:
    return DebugReadout(reading(0.1, 0.0, counts=False, steady=True), (), None, reading_)


def test_the_two_finger_bar_shows_the_score_against_its_threshold() -> None:
    bar_top = DEBUG_SCROLL_TOP + DEBUG_BAR_OFFSET
    low = render_preview(State.ACTIVE, debug=scroll_debug(scroll_reading(0.25)))
    high = render_preview(State.ACTIVE, debug=scroll_debug(scroll_reading(1.0)))

    assert filled_width(low, bar_top, TEXT_PAUSED) == DEBUG_BAR_WIDTH // 4
    assert filled_width(high, bar_top, TEXT_ACTIVE) == DEBUG_BAR_WIDTH - 1
    assert low.get(BAR_LEFT + round(0.5 * DEBUG_BAR_WIDTH), bar_top + 2) == JOINT


def test_the_offset_and_rate_bars_fill_only_while_scrolling() -> None:
    offset_top = DEBUG_SCROLL_STATE_TOP + DEBUG_LINE + DEBUG_BAR_OFFSET
    rate_top = offset_top + DEBUG_ROW
    idle = render_preview(State.ACTIVE, debug=scroll_debug(scroll_reading(0.9)))
    moving = render_preview(
        State.ACTIVE, debug=scroll_debug(scroll_reading(0.9, offset=-0.5, speed=-750.0))
    )

    for top in (offset_top, rate_top):
        assert filled_width(idle, top, TEXT_ACTIVE) == 0
        assert filled_width(idle, top, TEXT_PAUSED) == 0
    assert filled_width(moving, offset_top, TEXT_ACTIVE) == DEBUG_BAR_WIDTH // 2 - 1  # the tick
    assert filled_width(moving, rate_top, TEXT_ACTIVE) == DEBUG_BAR_WIDTH // 2


def test_the_flick_bar_shows_the_flick_measure_against_the_flick_speed() -> None:
    flick_top = DEBUG_SCROLL_STATE_TOP + DEBUG_LINE + 2 * DEBUG_ROW + DEBUG_BAR_OFFSET
    slow = render_preview(
        State.ACTIVE, debug=scroll_debug(scroll_reading(0.9, offset=0.0, flick=1.5))
    )
    fast = render_preview(
        State.ACTIVE, debug=scroll_debug(scroll_reading(0.9, offset=0.0, flick=-6.0))
    )

    assert filled_width(slow, flick_top, TEXT_PAUSED) == DEBUG_BAR_WIDTH // 4
    assert filled_width(fast, flick_top, TEXT_ACTIVE) == DEBUG_BAR_WIDTH - 1  # less the tick


def test_the_scroll_state_line_changes_with_the_state_and_nothing_else_moves() -> None:
    def draw(state: ScrollState) -> Image:
        return render_preview(
            State.ACTIVE, debug=scroll_debug(scroll_reading(0.9, offset=0.0, state=state))
        )

    images = {state: draw(state) for state in ScrollState}
    line = slice(DEBUG_SCROLL_STATE_TOP * WIDTH * 3, (DEBUG_SCROLL_STATE_TOP + 8) * WIDTH * 3)
    scrolling = images[ScrollState.SCROLLING]

    for state, image in images.items():
        if state is not ScrollState.SCROLLING:
            assert image.pixels[line] != scrolling.pixels[line]
        if state in (ScrollState.GRACE, ScrollState.COOLDOWN):  # still scrolling: same marks
            assert image.pixels[: line.start] == scrolling.pixels[: line.start]
    assert TEXT_ACTIVE in colours_in(scrolling)


def test_the_scroll_readout_sits_below_the_fist_and_leaves_everything_above() -> None:
    plain = render_preview(
        State.ACTIVE, debug=DebugReadout(reading(0.1, 0.0, counts=False, steady=True))
    )
    with_scroll = render_preview(State.ACTIVE, debug=scroll_debug(scroll_reading(None)))

    assert DEBUG_SCROLL_TOP >= DEBUG_FIST_TOP + 2 * DEBUG_ROW
    assert with_scroll.pixels != plain.pixels
    top = DEBUG_SCROLL_TOP * WIDTH * 3
    assert with_scroll.pixels[:top] == plain.pixels[:top]


def test_scrolling_says_so_and_only_the_label_differs_from_active() -> None:
    active = render_preview(State.ACTIVE, landmarks=TWO_FINGERS, camera_on=True)
    scroll = render_preview(State.ACTIVE, landmarks=TWO_FINGERS, camera_on=True, scrolling=True)

    assert scroll.pixels != active.pixels
    top = LABEL_TOP * WIDTH * 3
    assert scroll.pixels[:top] == active.pixels[:top]


def test_paused_and_no_hand_outrank_the_scroll_label() -> None:
    paused = render_preview(State.PAUSED, 0.3, landmarks=TWO_FINGERS)
    lost = render_preview(State.ACTIVE, no_hand=True)

    assert render_preview(State.PAUSED, 0.3, landmarks=TWO_FINGERS, scrolling=True).pixels == (
        paused.pixels
    )
    assert render_preview(State.ACTIVE, no_hand=True, scrolling=True).pixels == lost.pixels
