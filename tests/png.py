"""Decode the PNGs the renderer writes (8-bit RGB, no filtering), so snapshots compare pixels."""

import struct
import zlib

from airmouse.renderer import Image


def decode_png(data: bytes) -> Image:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    position = 8
    width = height = 0
    compressed = b""
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        position += 12 + length
        if kind == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
        elif kind == b"IDAT":
            compressed += body
    raw = zlib.decompress(compressed)
    stride = width * 3
    pixels = bytearray()
    for row in range(height):
        start = row * (stride + 1)
        assert raw[start] == 0  # filter type "none"
        pixels += raw[start + 1 : start + 1 + stride]
    return Image(width, height, pixels)
