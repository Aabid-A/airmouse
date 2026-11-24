import random
from pathlib import Path

import pytest

from airmouse.controller import State
from airmouse.gestures import Landmarks, is_open_palm
from airmouse.renderer import (
    BACKGROUND,
    BONE,
    CAMERA_ON_DOT,
    HEIGHT,
    JOINT,
    PALETTE,
    POINTER_COLOUR,
    POINTER_INDEX,
    WIDTH,
    Image,
    render_preview,
)
from hands import open_hand, placed, pointing_hand
from png import decode_png

SNAPSHOTS = Path(__file__).parent / "snapshots"


def snapshot_cases() -> dict[str, Image]:
    """Each frame is built from synthetic landmarks only."""
    return {
        "hand_paused": render_preview(
            State.PAUSED, 0.6, landmarks=placed(open_hand(), dy=-0.08), camera_on=True, fps=30.0
        ),
        "hand_active": render_preview(
            State.ACTIVE, landmarks=placed(pointing_hand(), dy=-0.08), camera_on=True, fps=29.6
        ),
        "no_hand": render_preview(State.PAUSED, camera_on=True, fps=30.0),
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


@pytest.mark.parametrize("name", ["hand_paused", "hand_active", "no_hand"])
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
