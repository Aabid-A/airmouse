"""Preview rendering: state in, image out. Pure, so it can be snapshot-tested.

The Preview is drawn on a plain near-black background and never contains camera
pixels (ADR 0001). This is the smallest version: a state label and the Hold
ring. The privacy preview (#6) extends it with the skeleton and Active region.
The only dependency is the standard library, so PNGs are written by hand.
"""

import math
import struct
import zlib
from dataclasses import dataclass

from airmouse.controller import State

WIDTH = 320
HEIGHT = 240

type Colour = tuple[int, int, int]

BACKGROUND: Colour = (16, 16, 16)
TEXT_PAUSED: Colour = (230, 180, 60)
TEXT_ACTIVE: Colour = (90, 200, 120)
RING_FILLED: Colour = (230, 180, 60)
RING_TRACK: Colour = (60, 60, 60)

RING_CENTRE = (WIDTH // 2, 95)
RING_INNER = 55
RING_OUTER = 68
LABEL_TOP = 175
LABEL_SCALE = 4

# 5x7 glyphs, one string per row, for the letters the state labels need.
FONT: dict[str, tuple[str, ...]] = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
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


def render_preview(state: State, hold_progress: float = 0.0) -> Image:
    """The Preview for a state. `hold_progress` (0 to 1) fills the Hold ring while Paused."""
    image = Image.blank(WIDTH, HEIGHT, BACKGROUND)
    if state is State.PAUSED:
        _draw_hold_ring(image, hold_progress)
        _draw_label(image, "PAUSED", TEXT_PAUSED)
    else:
        _draw_label(image, "ACTIVE", TEXT_ACTIVE)
    return image


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
    advance = (GLYPH_WIDTH + GLYPH_GAP) * LABEL_SCALE
    left = (image.width - (len(text) * advance - GLYPH_GAP * LABEL_SCALE)) // 2
    for index, letter in enumerate(text):
        for row, bits in enumerate(FONT[letter]):
            for column, bit in enumerate(bits):
                if bit == "#":
                    _fill_block(
                        image,
                        left + index * advance + column * LABEL_SCALE,
                        LABEL_TOP + row * LABEL_SCALE,
                        colour,
                    )


def _fill_block(image: Image, x: int, y: int, colour: Colour) -> None:
    for dy in range(LABEL_SCALE):
        for dx in range(LABEL_SCALE):
            image.set(x + dx, y + dy, colour)
