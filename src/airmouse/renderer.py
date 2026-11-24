"""Preview rendering: state in, image out. Pure, so it can be snapshot-tested.

The Preview is drawn on a plain near-black background and never contains camera
pixels (ADR 0001) unless the caller passes a camera image AND explicitly opts in
with `show_camera_image=True`. It shows the Hand skeleton, the Camera-on
indicator, an FPS readout, a state label and the Hold ring.
The only dependency is the standard library, so PNGs are written by hand.
"""

import math
import struct
import zlib
from dataclasses import dataclass

from airmouse.controller import State
from airmouse.frame import Region
from airmouse.gestures import LANDMARK_COUNT, Landmarks

WIDTH = 320
HEIGHT = 240

type Colour = tuple[int, int, int]

BACKGROUND: Colour = (16, 16, 16)
TEXT_PAUSED: Colour = (230, 180, 60)
TEXT_ACTIVE: Colour = (90, 200, 120)
RING_FILLED: Colour = (230, 180, 60)
RING_TRACK: Colour = (60, 60, 60)
BONE: Colour = (60, 110, 150)
JOINT: Colour = (210, 225, 240)
POINTER_COLOUR: Colour = (110, 230, 255)
CAMERA_ON_DOT: Colour = (235, 70, 70)
STATUS_TEXT: Colour = (150, 150, 150)
REGION_OUTLINE: Colour = (240, 200, 90)
TEXT_CALIBRATE: Colour = (240, 200, 90)

# Every colour the Privacy preview can contain. A test uses it to prove no camera pixel gets in.
PALETTE = frozenset(
    {
        BACKGROUND,
        TEXT_PAUSED,
        TEXT_ACTIVE,
        RING_FILLED,
        RING_TRACK,
        BONE,
        JOINT,
        POINTER_COLOUR,
        CAMERA_ON_DOT,
        STATUS_TEXT,
        REGION_OUTLINE,
        TEXT_CALIBRATE,
    }
)

# MediaPipe's hand skeleton: pairs of landmark indices (0 is the wrist, 4/8/12/16/20 the tips).
HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),  # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),  # index finger
    (9, 10), (10, 11), (11, 12),  # middle finger
    (13, 14), (14, 15), (15, 16),  # ring finger
    (17, 18), (18, 19), (19, 20),  # little finger
    (5, 9), (9, 13), (13, 17), (0, 17),  # palm
)  # fmt: skip
POINTER_INDEX = 8  # the index fingertip
BONE_RADIUS = 1
JOINT_RADIUS = 3
POINTER_RADIUS = 5

REGION_OUTLINE_WIDTH = 2

INDICATOR_SCALE = 2
INDICATOR_MARGIN = 10
CAMERA_DOT_RADIUS = 4

RING_CENTRE = (WIDTH // 2, 95)
RING_INNER = 55
RING_OUTER = 68
LABEL_TOP = 216
LABEL_SCALE = 2

# 5x7 glyphs, one string per row, for the characters the labels and readouts need.
FONT: dict[str, tuple[str, ...]] = {
    " ": (".....",) * 7,
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
}
GLYPH_WIDTH = 5
GLYPH_HEIGHT = 7
GLYPH_GAP = 1


@dataclass
class Image:
    """An RGB image, row-major, three bytes per pixel."""

    width: int
    height: int
    pixels: bytearray

    @classmethod
    def blank(cls, width: int, height: int, colour: Colour) -> "Image":
        return cls(width, height, bytearray(colour * (width * height)))

    def set(self, x: int, y: int, colour: Colour) -> None:
        offset = (y * self.width + x) * 3
        self.pixels[offset : offset + 3] = bytes(colour)

    def get(self, x: int, y: int) -> Colour:
        offset = (y * self.width + x) * 3
        return (self.pixels[offset], self.pixels[offset + 1], self.pixels[offset + 2])

    def to_png(self) -> bytes:
        stride = self.width * 3
        rows = b"".join(
            b"\x00" + bytes(self.pixels[y * stride : (y + 1) * stride]) for y in range(self.height)
        )
        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(rows, 9))
            + _chunk(b"IEND", b"")
        )


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def render_preview(
    state: State,
    hold_progress: float = 0.0,
    *,
    landmarks: Landmarks | None = None,
    camera_on: bool = False,
    fps: float | None = None,
    camera_image: Image | None = None,
    show_camera_image: bool = False,
) -> Image:
    """The Preview for a state.

    `hold_progress` (0 to 1) fills the Hold ring while Paused. `landmarks` is the
    Hand's 21 normalised landmarks (None when no Hand is seen). The Camera-on
    indicator appears when `camera_on`, and the FPS readout when `fps` is given.
    `camera_image` is drawn behind everything only when `show_camera_image` is
    True: the default Privacy preview ignores it.
    """
    image = _background(camera_image, show_camera_image)
    if state is State.PAUSED:
        _draw_hold_ring(image, hold_progress)
        _draw_label(image, "PAUSED", TEXT_PAUSED)
    else:
        _draw_label(image, "ACTIVE", TEXT_ACTIVE)
    if landmarks is not None:
        _draw_skeleton(image, landmarks)
    if camera_on:
        _draw_camera_on(image)
    if fps is not None:
        _draw_fps(image, fps)
    return image


def render_calibrate(
    region: Region,
    *,
    landmarks: Landmarks | None = None,
    camera_on: bool = False,
    fps: float | None = None,
    camera_image: Image | None = None,
    show_camera_image: bool = False,
) -> Image:
    """Calibrate mode: the Hand and the outline of the Active `region` (normalised edges).

    The Hand and the region are both in the prepared frame (rotated and mirrored),
    so moving the hand right moves the skeleton right. It never shows a state:
    calibrate mode makes no cursor input. Camera pixels follow the same opt-in as
    `render_preview`.
    """
    image = _background(camera_image, show_camera_image)
    _draw_region(image, region)
    _draw_label(image, "CALIBRATE", TEXT_CALIBRATE)
    if landmarks is not None:
        _draw_skeleton(image, landmarks)
    if camera_on:
        _draw_camera_on(image)
    if fps is not None:
        _draw_fps(image, fps)
    return image


def _background(camera_image: Image | None, show_camera_image: bool) -> Image:
    if show_camera_image and camera_image is not None:
        if (camera_image.width, camera_image.height) != (WIDTH, HEIGHT):
            raise ValueError(f"camera image must be {WIDTH}x{HEIGHT}")
        return Image(WIDTH, HEIGHT, bytearray(camera_image.pixels))
    return Image.blank(WIDTH, HEIGHT, BACKGROUND)


def _draw_region(image: Image, region: Region) -> None:
    left, top, right, bottom = region
    x0, x1 = round(left * (image.width - 1)), round(right * (image.width - 1))
    y0, y1 = round(top * (image.height - 1)), round(bottom * (image.height - 1))
    for offset in range(REGION_OUTLINE_WIDTH):
        for x in range(x0, x1 + 1):
            _plot(image, x, y0 + offset, REGION_OUTLINE)
            _plot(image, x, y1 - offset, REGION_OUTLINE)
        for y in range(y0, y1 + 1):
            _plot(image, x0 + offset, y, REGION_OUTLINE)
            _plot(image, x1 - offset, y, REGION_OUTLINE)


def _draw_hold_ring(image: Image, progress: float) -> None:
    """Fill clockwise from the top; the unfilled part is a dim track."""
    progress = max(0.0, min(1.0, progress))
    cx, cy = RING_CENTRE
    for y in range(cy - RING_OUTER, cy + RING_OUTER + 1):
        for x in range(cx - RING_OUTER, cx + RING_OUTER + 1):
            radius = math.hypot(x - cx, y - cy)
            if not RING_INNER <= radius <= RING_OUTER:
                continue
            turn = (math.atan2(x - cx, cy - y) % math.tau) / math.tau
            image.set(x, y, RING_FILLED if turn < progress else RING_TRACK)


def _draw_label(image: Image, text: str, colour: Colour) -> None:
    left = (image.width - _text_width(text, LABEL_SCALE)) // 2
    _draw_text(image, text, left, LABEL_TOP, LABEL_SCALE, colour)


def _text_width(text: str, scale: int) -> int:
    return (len(text) * (GLYPH_WIDTH + GLYPH_GAP) - GLYPH_GAP) * scale


def _draw_text(image: Image, text: str, left: int, top: int, scale: int, colour: Colour) -> None:
    advance = (GLYPH_WIDTH + GLYPH_GAP) * scale
    for index, letter in enumerate(text):
        for row, bits in enumerate(FONT[letter]):
            for column, bit in enumerate(bits):
                if bit == "#":
                    _fill_block(
                        image,
                        left + index * advance + column * scale,
                        top + row * scale,
                        scale,
                        colour,
                    )


def _fill_block(image: Image, x: int, y: int, size: int, colour: Colour) -> None:
    for dy in range(size):
        for dx in range(size):
            _plot(image, x + dx, y + dy, colour)


def _plot(image: Image, x: int, y: int, colour: Colour) -> None:
    """Set a pixel, ignoring anything off the image (landmarks can leave the frame)."""
    if 0 <= x < image.width and 0 <= y < image.height:
        image.set(x, y, colour)


def _fill_disc(image: Image, cx: int, cy: int, radius: int, colour: Colour) -> None:
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if math.hypot(x - cx, y - cy) <= radius + 0.5:
                _plot(image, x, y, colour)


def _draw_line(
    image: Image, start: tuple[int, int], end: tuple[int, int], radius: int, colour: Colour
) -> None:
    steps = max(abs(end[0] - start[0]), abs(end[1] - start[1]), 1)
    for step in range(steps + 1):
        x = round(start[0] + (end[0] - start[0]) * step / steps)
        y = round(start[1] + (end[1] - start[1]) * step / steps)
        _fill_disc(image, x, y, radius, colour)


def _draw_skeleton(image: Image, landmarks: Landmarks) -> None:
    """Bones first, then joints, with the Pointer on top. Coordinates are 0 to 1."""
    if len(landmarks) != LANDMARK_COUNT:
        return
    points = [(round(x * (image.width - 1)), round(y * (image.height - 1))) for x, y in landmarks]
    for first, second in HAND_CONNECTIONS:
        _draw_line(image, points[first], points[second], BONE_RADIUS, BONE)
    for index, (x, y) in enumerate(points):
        if index != POINTER_INDEX:
            _fill_disc(image, x, y, JOINT_RADIUS, JOINT)
    x, y = points[POINTER_INDEX]
    _fill_disc(image, x, y, POINTER_RADIUS, POINTER_COLOUR)


def _draw_camera_on(image: Image) -> None:
    """A red dot and "CAMERA ON", top left: the camera is capturing."""
    dot_x = INDICATOR_MARGIN + CAMERA_DOT_RADIUS
    dot_y = INDICATOR_MARGIN + (GLYPH_HEIGHT * INDICATOR_SCALE) // 2
    _fill_disc(image, dot_x, dot_y, CAMERA_DOT_RADIUS, CAMERA_ON_DOT)
    left = dot_x + CAMERA_DOT_RADIUS + INDICATOR_MARGIN // 2
    _draw_text(image, "CAMERA ON", left, INDICATOR_MARGIN, INDICATOR_SCALE, STATUS_TEXT)


def _draw_fps(image: Image, fps: float) -> None:
    """The frame rate in whole frames per second, top right."""
    text = f"{max(0, min(999, round(fps)))} FPS"
    left = image.width - INDICATOR_MARGIN - _text_width(text, INDICATOR_SCALE)
    _draw_text(image, text, left, INDICATOR_MARGIN, INDICATOR_SCALE, STATUS_TEXT)
