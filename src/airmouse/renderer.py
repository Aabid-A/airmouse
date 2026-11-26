"""Preview rendering: state in, image out. Pure, so it can be snapshot-tested.

The Preview is a fixed 16:9 canvas on a near-black background. The prepared
camera frame (4:3, or 3:4 after a quarter turn) is fitted inside it without
stretching, and the Hand skeleton and the Active region outline are drawn in that
fitted frame through one mapping (`to_canvas`), so they agree with `frame.py`.
The HUD (Camera-on indicator, FPS, state label, Hold ring) sits on top. It never
contains camera pixels (ADR 0001) unless the caller passes a camera image AND
opts in with `show_camera_image=True`. With `--debug-gestures` it also draws the
gesture readout (bars and numbers, never camera pixels).

Drawing uses numpy (already used by `frame.py`), with only elementwise IEEE
arithmetic and round-half-to-even, so the same inputs give the same pixels on
every platform. Static layers (background, Active region outline, Camera-on
indicator) and text are cached, so a frame only redraws what changes.
"""

import math
import struct
import zlib
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from airmouse.controller import FistReading, PalmReading, Phase, ScrollReading, State
from airmouse.frame import Region, active_region
from airmouse.gestures import LANDMARK_COUNT, Landmarks, Point

# The canvas: 16:9 so a screen recording of the window is a standard video shape.
# 640x360 is shown at 2x (1280x720) by the window. All layout below is in canvas pixels.
WIDTH = 640
HEIGHT = 360

type Colour = tuple[int, int, int]
type Canvas = np.ndarray  # (HEIGHT, WIDTH, 3) uint8, RGB
type Alpha = np.ndarray  # (h, w) float32 coverage, 0 to 1

# Colour tokens. State colours always come with a text label, never alone.
BACKGROUND: Colour = (10, 11, 14)
MUTED: Colour = (120, 126, 138)  # HUD labels and hints
TEXT_PAUSED: Colour = (240, 180, 70)  # amber: Paused, No hand, the Hold ring
TEXT_ACTIVE: Colour = (100, 220, 150)  # green: active
TEXT_PINCH: Colour = (110, 220, 255)  # cyan: Pinch and drag, the Pointer
TEXT_CALIBRATE: Colour = (240, 200, 90)
RING_FILLED: Colour = TEXT_PAUSED
RING_TRACK: Colour = (38, 41, 48)
BONE: Colour = (80, 160, 225)
BONE_PAUSED: Colour = (95, 105, 120)
GLOW: Colour = (40, 130, 230)
GLOW_PAUSED: Colour = (70, 80, 95)
JOINT: Colour = (225, 235, 245)
JOINT_PAUSED: Colour = (165, 172, 184)
POINTER_COLOUR: Colour = TEXT_PINCH
CAMERA_ON_DOT: Colour = (240, 70, 70)
STATUS_TEXT: Colour = MUTED
REGION_OUTLINE: Colour = (240, 200, 90)  # Calibrate mode, where the region is the point
REGION_PREVIEW: Colour = (88, 96, 112)  # the Preview: there, but quiet

# MediaPipe's hand skeleton: pairs of landmark indices (0 is the wrist, 4/8/12/16/20 the tips).
HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),  # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),  # index finger
    (9, 10), (10, 11), (11, 12),  # middle finger
    (13, 14), (14, 15), (15, 16),  # ring finger
    (17, 18), (18, 19), (19, 20),  # little finger
    (5, 9), (9, 13), (13, 17), (0, 17),  # palm
)  # fmt: skip
THUMB_TIP = 4
POINTER_INDEX = 8  # the index fingertip

# Sizes in canvas pixels (radii are half-widths of the anti-aliased shapes).
MARGIN = 16
BONE_RADIUS = 1.0
JOINT_RADIUS = 2.5
POINTER_RADIUS = 4.5
PRESS_RING_RADIUS = 10.0  # the ring round the Pointer while the Pinch holds the button down
PRESS_RING_HALF_WIDTH = 0.75
GLOW_REACH = 9.0  # how far the soft halo spreads from a bone or joint
GLOW_STRENGTH = 0.35  # the halo's opacity at the stroke
POINTER_GLOW_REACH = 14.0
POINTER_GLOW_STRENGTH = 0.5
REGION_HALF_WIDTH = 0.5  # a 1 px outline
CAMERA_DOT_RADIUS = 3.5

RING_RADIUS = 60.0
RING_HALF_WIDTH = 3.0
RING_GLOW_REACH = 8.0
TURN_STEPS = 65536  # the Hold ring's fill position is exact to this fraction of a turn
RING_INNER = RING_RADIUS - RING_HALF_WIDTH
RING_OUTER = RING_RADIUS + RING_HALF_WIDTH

# Type: one mono font in three sizes, tracked (extra letter spacing) for labels.
LABEL_SIZE = 3.0  # canvas pixels per font pixel: the state label
SMALL_SIZE = 1.5  # HUD labels and hints
DEBUG_SIZE = 1  # the gesture readout, pixel-exact
TRACKING = 2  # font pixels between letters in labels
DEBUG_TRACKING = 1
LABEL_GAP = 6  # between the state label and its hint

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
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
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
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    ".": (".....", ".....", ".....", ".....", ".....", "..##.", "..##."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
}
GLYPH_WIDTH = 5
GLYPH_HEIGHT = 7

# The state label, bottom centre, always at the same height, with an optional hint under it.
HINT_TOP = HEIGHT - MARGIN - round(GLYPH_HEIGHT * SMALL_SIZE)
LABEL_TOP = HINT_TOP - LABEL_GAP - round(GLYPH_HEIGHT * LABEL_SIZE)
HUD_TEXT_TOP = MARGIN  # Camera-on indicator and FPS, top corners
# The prepared frame is fitted between these, so the Hand never runs under the label.
STAGE_TOP = MARGIN // 2
STAGE_BOTTOM = LABEL_TOP - MARGIN // 2

# The gesture readout (`--debug-gestures`): two bars on the left, status lines under
# them, and the per-stage timings in ms on the right, all below the top HUD line.
DEBUG_LEFT = MARGIN
DEBUG_TOP = 44
DEBUG_ROW = 20
DEBUG_BAR_WIDTH = 80
DEBUG_BAR_HEIGHT = 6
DEBUG_BAR_OFFSET = GLYPH_HEIGHT + 3  # from the top of a meter's text to its bar
DEBUG_TICK_OVERHANG = 2
DEBUG_LINE = 10
DEBUG_FIST_TOP = DEBUG_TOP + 2 * DEBUG_ROW + 2 * DEBUG_LINE + 4  # under COUNTS and STEADY
DEBUG_SCROLL_TOP = DEBUG_FIST_TOP + 2 * DEBUG_ROW  # under the Fist meters (or their place)
DEBUG_OFFSET_RANGE = 1.0  # the scroll offset bar is full at this many hand sizes
DEBUG_RATE_CAP = 99999.0  # scroll speeds are shown in whole pixels per second
DEBUG_SPEED_RANGE = 2.0  # the speed bar is full at this many times its limit
DEBUG_NUMBER_CAP = 99.9


@dataclass(frozen=True)
class FrameView:
    """The prepared frame as the Preview draws it: its size in pixels and the Active region.

    `region` is in the prepared frame's normalised coordinates, the same ones the
    landmarks use, so it must be the region the cursor mapping uses. `outline` is
    False in relative control mode, where no region maps to the screen, so none is drawn.
    """

    width: int = 640
    height: int = 480
    region: Region = active_region(640, 480, 0.6)
    outline: bool = True


DEFAULT_VIEW = FrameView()


@dataclass(frozen=True)
class DebugReadout:
    """What `--debug-gestures` draws: the palm reading, then rows of (name, value) on the right:
    stage timings in ms and, last, the tracking and window rates in frames per second.
    `fist`, when given (relative mode), adds the Fist score against the clutch threshold
    and the finger curl against the hold threshold under the palm. `scroll`, when given,
    adds the two-finger score against its threshold, the scroll offset from the anchor
    against the deadzone and the scroll speed against its cap, under the Fist's place."""

    palm: PalmReading
    timings: tuple[tuple[str, float], ...] = ()
    fist: FistReading | None = None
    scroll: ScrollReading | None = None


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


@dataclass(frozen=True)
class Stage:
    """Where the prepared frame sits on the canvas: the largest unstretched fit, centred."""

    left: float
    top: float
    width: float
    height: float


def stage_for(view: FrameView) -> Stage:
    room = STAGE_BOTTOM - STAGE_TOP
    scale = min(WIDTH / view.width, room / view.height)
    width, height = view.width * scale, view.height * scale
    return Stage((WIDTH - width) / 2, STAGE_TOP + (room - height) / 2, width, height)


def to_canvas(point: Point, view: FrameView = DEFAULT_VIEW) -> Point:
    """A normalised point of the prepared frame to canvas pixels (pixel centres at +0.5).

    The one mapping for the skeleton, the Pointer and the Active region outline.
    """
    stage = stage_for(view)
    return (stage.left + point[0] * stage.width, stage.top + point[1] * stage.height)


def hold_ring_centre(view: FrameView = DEFAULT_VIEW) -> Point:
    """The Hold ring's centre in canvas pixels: the middle of the fitted frame."""
    return to_canvas((0.5, 0.5), view)


def render_preview(
    state: State,
    hold_progress: float = 0.0,
    *,
    landmarks: Landmarks | None = None,
    camera_on: bool = False,
    fps: float | None = None,
    camera_image: Image | None = None,
    show_camera_image: bool = False,
    debug: DebugReadout | None = None,
    no_hand: bool = False,
    phase: Phase = Phase.IDLE,
    view: FrameView = DEFAULT_VIEW,
    clutch: bool = False,
    holding: bool = False,
    scrolling: bool = False,
) -> Image:
    """The Preview for a state.

    `hold_progress` (0 to 1) fills the Hold ring while Paused. `landmarks` is the
    Hand's 21 normalised landmarks in the prepared frame (None when no Hand is
    seen). `phase` is the Controller's Pinch phase: PINCH while the button is down
    and undecided, DRAG while dragging. The Camera-on indicator appears when
    `camera_on`, and the FPS readout when `fps` is given. `camera_image` (the
    prepared frame, `view` sized) is drawn behind everything only when
    `show_camera_image` is True: the default Privacy preview ignores it. `debug`
    adds the gesture readout. `no_hand` (the No hand state) shows NO HAND, and
    `clutch` (the Fist clutch is held) shows CLUTCH, and `holding` (the cursor holds
    still while the fingers are curled) shows HOLD, and `scrolling` (a Scroll is in
    progress) shows SCROLL. `view` is the prepared frame's size and the Active region.
    """
    canvas = _base(view, camera_on, REGION_PREVIEW, camera_image, show_camera_image)
    paused = state is State.PAUSED
    still = no_hand or clutch or holding or scrolling
    pressed = not paused and not still and phase is not Phase.IDLE
    if paused:
        _draw_hold_ring(canvas, view, hold_progress)
        _draw_label(canvas, "PAUSED", TEXT_PAUSED, "HOLD AN OPEN PALM TO START")
    elif no_hand:
        _draw_label(canvas, "NO HAND", TEXT_PAUSED, "SHOW YOUR HAND TO THE CAMERA")
    elif clutch:
        _draw_label(canvas, "CLUTCH", TEXT_PAUSED, "POINT TO MOVE AGAIN")
    elif scrolling:
        _draw_label(canvas, "SCROLL", TEXT_PINCH, "MOVE UP OR DOWN")
    elif holding:
        _draw_label(canvas, "HOLD", TEXT_PAUSED, "STRAIGHTEN YOUR FINGER TO MOVE")
    elif phase is Phase.DRAGGING:
        _draw_label(canvas, "DRAG", TEXT_PINCH, "OPEN THE PINCH TO DROP")
    elif phase is Phase.PRESSED:
        _draw_label(canvas, "PINCH", TEXT_PINCH, "MOVE TO DRAG")
    else:
        _draw_label(canvas, "ACTIVE", TEXT_ACTIVE, "PINCH TO CLICK")
    if landmarks is not None:
        _draw_skeleton(canvas, landmarks, view, dim=paused, pressed=pressed)
    if fps is not None:
        _draw_fps(canvas, fps)
    if debug is not None:
        _draw_debug(canvas, debug)
    return _to_image(canvas)


def render_calibrate(
    view: FrameView,
    *,
    landmarks: Landmarks | None = None,
    camera_on: bool = False,
    fps: float | None = None,
    camera_image: Image | None = None,
    show_camera_image: bool = False,
) -> Image:
    """Calibrate mode: the Hand and the outline of the Active region of `view`.

    The Hand and the region are both in the prepared frame (rotated and mirrored),
    so moving the hand right moves the skeleton right. It never shows a state:
    calibrate mode makes no cursor input. Camera pixels follow the same opt-in as
    `render_preview`.
    """
    canvas = _base(view, camera_on, REGION_OUTLINE, camera_image, show_camera_image)
    _draw_label(canvas, "CALIBRATE", TEXT_CALIBRATE, "NO CURSOR INPUT")
    if landmarks is not None:
        _draw_skeleton(canvas, landmarks, view, dim=False, pressed=False)
    if fps is not None:
        _draw_fps(canvas, fps)
    return _to_image(canvas)


def _to_image(canvas: Canvas) -> Image:
    return Image(WIDTH, HEIGHT, bytearray(canvas.tobytes()))


# --- the static layer: background, Active region outline, Camera-on indicator ---


def _base(
    view: FrameView,
    camera_on: bool,
    region_colour: Colour,
    camera_image: Image | None,
    show_camera_image: bool,
) -> Canvas:
    if show_camera_image and camera_image is not None:
        canvas = np.full((HEIGHT, WIDTH, 3), BACKGROUND, dtype=np.uint8)
        _draw_camera_image(canvas, camera_image, view)
        _draw_static(canvas, view, camera_on, region_colour)
        return canvas
    return _cached_base(view, camera_on, region_colour).copy()


@lru_cache(maxsize=16)
def _cached_base(view: FrameView, camera_on: bool, region_colour: Colour) -> Canvas:
    canvas = np.full((HEIGHT, WIDTH, 3), BACKGROUND, dtype=np.uint8)
    _draw_static(canvas, view, camera_on, region_colour)
    canvas.flags.writeable = False  # callers copy it
    return canvas


def _draw_static(canvas: Canvas, view: FrameView, camera_on: bool, region_colour: Colour) -> None:
    if view.outline:
        _draw_region(canvas, view, region_colour)
    if camera_on:
        _draw_camera_on(canvas)


def _draw_camera_image(canvas: Canvas, camera_image: Image, view: FrameView) -> None:
    """The prepared frame, scaled (nearest pixel) into the stage. Opt-in only."""
    if (camera_image.width, camera_image.height) != (view.width, view.height):
        raise ValueError(f"camera image must be {view.width}x{view.height}")
    source = np.frombuffer(bytes(camera_image.pixels), dtype=np.uint8)
    source = source.reshape(camera_image.height, camera_image.width, 3)
    stage = stage_for(view)
    left, top = round(stage.left), round(stage.top)
    width, height = round(stage.width), round(stage.height)
    rows = (np.arange(height) * camera_image.height) // height
    columns = (np.arange(width) * camera_image.width) // width
    canvas[top : top + height, left : left + width] = source[rows[:, None], columns[None, :]]


def _draw_region(canvas: Canvas, view: FrameView, colour: Colour) -> None:
    """A crisp 1 px rectangle through the canvas pixels that hold the Active region's edges."""
    left, top, right, bottom = view.region
    x0, y0 = (math.floor(v) + 0.5 for v in to_canvas((left, top), view))
    x1, y1 = (math.floor(v) + 0.5 for v in to_canvas((right, bottom), view))
    box = _Box.around(x0, y0, x1, y1, 2.0)
    if box is None:
        return
    xs, ys = box.centres()
    # Distance to the rectangle's outline: inside, the nearest edge; outside, the box.
    outside_x = np.maximum(np.maximum(x0 - xs, xs - x1), 0.0)
    outside_y = np.maximum(np.maximum(y0 - ys, ys - y1), 0.0)
    outside = np.sqrt(outside_x * outside_x + outside_y * outside_y)
    inside = np.minimum(np.minimum(xs - x0, x1 - xs), np.minimum(ys - y0, y1 - ys))
    edge = np.where(outside > 0, outside, np.maximum(inside, 0.0))
    patch = _Patch(canvas, box)
    patch.paint(_stroke(edge, REGION_HALF_WIDTH), colour)
    patch.commit()


def _draw_camera_on(canvas: Canvas) -> None:
    """A red dot and "CAMERA ON", top left: the camera is capturing."""
    text_height = GLYPH_HEIGHT * SMALL_SIZE
    cx, cy = MARGIN + CAMERA_DOT_RADIUS, HUD_TEXT_TOP + text_height / 2
    box = _Box.around(cx, cy, cx, cy, CAMERA_DOT_RADIUS + 4)
    if box is not None:
        distance = _point_distance(box, cx, cy)
        patch = _Patch(canvas, box)
        patch.paint(_glow(distance - CAMERA_DOT_RADIUS, 4.0, 0.4), CAMERA_ON_DOT)
        patch.paint(_stroke(distance, CAMERA_DOT_RADIUS), CAMERA_ON_DOT)
        patch.commit()
    left = round(cx + CAMERA_DOT_RADIUS + 6)
    _draw_text(canvas, "CAMERA ON", left, HUD_TEXT_TOP, SMALL_SIZE, TRACKING, STATUS_TEXT)


# --- the dynamic layer ---


def _draw_hold_ring(canvas: Canvas, view: FrameView, progress: float) -> None:
    """A thin ring at the stage centre, filling clockwise from the top; the rest is a dim track."""
    progress = max(0.0, min(1.0, progress))
    box, band, turn, radius = _ring_geometry(*hold_ring_centre(view))
    if box is None:
        return
    patch = _Patch(canvas, box)
    patch.paint(band, RING_TRACK)
    if progress <= 0:
        patch.commit()
        return
    if progress >= 1:
        filled = np.ones_like(turn)
    else:
        # Anti-alias both ends of the arc by their distance along it, in pixels.
        along = np.minimum(np.float32(progress) - turn, turn) * radius * np.float32(math.tau)
        filled = np.clip(along + np.float32(0.5), 0.0, 1.0)
    halo = _glow(np.abs(radius - np.float32(RING_RADIUS)) - RING_HALF_WIDTH, RING_GLOW_REACH, 0.3)
    patch.paint(halo * filled, RING_FILLED)
    patch.paint(band * filled, RING_FILLED)
    patch.commit()


@lru_cache(maxsize=4)
def _ring_geometry(cx: float, cy: float) -> tuple["_Box | None", Alpha, Alpha, Alpha]:
    """The ring's box, band coverage, turn from the top (0 to 1, clockwise) and radius."""
    reach = RING_OUTER + RING_GLOW_REACH + 1
    box = _Box.around(cx, cy, cx, cy, reach)
    if box is None:
        empty = np.zeros((0, 0), dtype=np.float32)
        return None, empty, empty, empty
    xs, ys = box.centres()
    dx, dy = xs - np.float32(cx), ys - np.float32(cy)
    radius = np.sqrt(dx * dx + dy * dy)
    band = _stroke(np.abs(radius - np.float32(RING_RADIUS)), RING_HALF_WIDTH)
    # arctan2 is the one call here that libm or SIMD code may round differently by
    # platform, so its result is snapped to 1/65536 of a turn: the pixels stay the same.
    angle = np.arctan2(dx.astype(np.float64), -dy.astype(np.float64))
    turn = (np.round((angle / math.tau % 1.0) * TURN_STEPS) / TURN_STEPS).astype(np.float32)
    for array in (band, turn, radius):
        array.flags.writeable = False
    return box, band, turn, radius


def _draw_skeleton(
    canvas: Canvas, landmarks: Landmarks, view: FrameView, *, dim: bool, pressed: bool
) -> None:
    """A soft halo, then bones, joints and the Pointer on top. Coordinates are 0 to 1.

    `dim` (Paused) draws it in greys: the Hand is seen but makes no input.
    `pressed` (Pinch or drag) rings the Pointer and lights the thumb-to-index line.
    """
    if len(landmarks) != LANDMARK_COUNT:
        return
    points = [to_canvas(point, view) for point in landmarks]
    xs_all, ys_all = [x for x, _ in points], [y for _, y in points]
    reach = max(GLOW_REACH, POINTER_GLOW_REACH + POINTER_RADIUS, PRESS_RING_RADIUS + 2) + 1
    box = _Box.around(min(xs_all), min(ys_all), max(xs_all), max(ys_all), reach)
    if box is None:
        return
    bones = box.distances()
    for first, second in HAND_CONNECTIONS:
        box.stamp_segment(bones, points[first], points[second], GLOW_REACH + 1)
    joints = box.distances()
    for index, point in enumerate(points):
        if index != POINTER_INDEX:
            box.stamp_segment(joints, point, point, GLOW_REACH + JOINT_RADIUS + 1)
    nearest = np.minimum(bones - np.float32(BONE_RADIUS), joints - np.float32(JOINT_RADIUS))
    bone, joint, glow = (BONE_PAUSED, JOINT_PAUSED, GLOW_PAUSED) if dim else (BONE, JOINT, GLOW)
    patch = _Patch(canvas, box)
    patch.paint(_glow(nearest, GLOW_REACH, GLOW_STRENGTH), glow)
    patch.paint(_stroke(bones, BONE_RADIUS), bone)
    if pressed:
        pinch = box.distances()
        box.stamp_segment(pinch, points[THUMB_TIP], points[POINTER_INDEX], GLOW_REACH + 1)
        patch.paint(_stroke(pinch, BONE_RADIUS), POINTER_COLOUR)
    patch.paint(_stroke(joints, JOINT_RADIUS), joint)
    px, py = points[POINTER_INDEX]
    pointer = _point_distance(box, px, py)
    pointer_colour = JOINT_PAUSED if dim else POINTER_COLOUR
    patch.paint(
        _glow(pointer - POINTER_RADIUS, POINTER_GLOW_REACH, POINTER_GLOW_STRENGTH), pointer_colour
    )
    if pressed:
        ring = np.abs(pointer - np.float32(PRESS_RING_RADIUS))
        patch.paint(_stroke(ring, PRESS_RING_HALF_WIDTH), POINTER_COLOUR)
    patch.paint(_stroke(pointer, POINTER_RADIUS), pointer_colour)
    patch.commit()


def _draw_label(canvas: Canvas, text: str, colour: Colour, hint: str) -> None:
    """The state label, bottom centre, with a muted hint under it: what to do next."""
    _draw_centred(canvas, text, LABEL_TOP, LABEL_SIZE, colour)
    _draw_centred(canvas, hint, HINT_TOP, SMALL_SIZE, MUTED)


def _draw_centred(canvas: Canvas, text: str, top: int, size: float, colour: Colour) -> None:
    mask = _text_mask(text, size, TRACKING)
    _draw_mask(canvas, mask, (WIDTH - mask.shape[1]) // 2, top, colour)


def _draw_fps(canvas: Canvas, fps: float) -> None:
    """The frame rate in whole frames per second, top right."""
    text = f"{max(0, min(999, round(fps)))} FPS"
    mask = _text_mask(text, SMALL_SIZE, TRACKING)
    _draw_mask(canvas, mask, WIDTH - MARGIN - mask.shape[1], HUD_TEXT_TOP, STATUS_TEXT)


# --- text ---


def _draw_text(
    canvas: Canvas, text: str, left: int, top: int, size: float, tracking: int, colour: Colour
) -> None:
    _draw_mask(canvas, _text_mask(text, size, tracking), left, top, colour)


def _text_width(text: str, size: float, tracking: int = TRACKING) -> int:
    """The width in canvas pixels of `text` drawn at `size` with `tracking`."""
    return _text_mask(text, size, tracking).shape[1]


@lru_cache(maxsize=256)
def _text_mask(text: str, size: float, tracking: int) -> Alpha:
    """Anti-aliased coverage of `text` in the 5x7 font at `size` canvas pixels per font pixel.

    The glyph bitmap is sampled bilinearly at each canvas pixel centre and cut at
    half, with a one-pixel ramp: corners round off and diagonals smooth out, and
    at a whole-number size the cut lands on whole font pixels (a crisp bitmap).
    """
    advance = GLYPH_WIDTH + tracking
    columns = len(text) * advance - tracking
    bitmap = np.zeros((GLYPH_HEIGHT + 2, columns + 2), dtype=np.float32)  # a blank border
    for index, letter in enumerate(text):
        for row, bits in enumerate(FONT[letter]):
            for column, bit in enumerate(bits):
                if bit == "#":
                    bitmap[row + 1, index * advance + column + 1] = 1.0
    width, height = round(columns * size), round(GLYPH_HEIGHT * size)
    field = _resample(_resample(bitmap, height, size, axis=0), width, size, axis=1)
    mask = np.clip((field - np.float32(0.5)) * np.float32(max(size, 1.0)) + np.float32(0.5), 0, 1)
    mask.flags.writeable = False
    return mask


def _resample(bitmap: np.ndarray, count: int, size: float, *, axis: int) -> np.ndarray:
    """Linear interpolation of a bordered bitmap at `count` canvas pixel centres along `axis`."""
    position = (np.arange(count, dtype=np.float32) + np.float32(0.5)) / np.float32(size)
    position = position - np.float32(0.5) + np.float32(1.0)  # font pixel centres, past the border
    low = np.floor(position).astype(np.intp)
    weight = (position - low.astype(np.float32)).astype(np.float32)
    first = np.take(bitmap, low, axis=axis)
    second = np.take(bitmap, low + 1, axis=axis)
    shape = (-1, 1) if axis == 0 else (1, -1)
    weight = weight.reshape(shape)
    return first + (second - first) * weight


def _draw_mask(canvas: Canvas, mask: Alpha, left: int, top: int, colour: Colour) -> None:
    height, width = mask.shape
    _blend(canvas, _Box(left, top, width, height), mask, colour)


# --- anti-aliased shapes on numpy ---


@dataclass(frozen=True)
class _Box:
    """A rectangle of whole canvas pixels where a shape is computed."""

    left: int
    top: int
    width: int
    height: int

    @classmethod
    def around(cls, x0: float, y0: float, x1: float, y1: float, reach: float) -> "_Box | None":
        """The pixels within `reach` of the rectangle x0..x1, y0..y1, clipped to the canvas."""
        left = max(0, math.floor(min(x0, x1) - reach))
        top = max(0, math.floor(min(y0, y1) - reach))
        right = min(WIDTH, math.ceil(max(x0, x1) + reach))
        bottom = min(HEIGHT, math.ceil(max(y0, y1) + reach))
        if right <= left or bottom <= top:
            return None
        return cls(left, top, right - left, bottom - top)

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        """Pixel centre coordinates: x as a row, y as a column (broadcast to the box)."""
        xs = np.arange(self.left, self.left + self.width, dtype=np.float32) + np.float32(0.5)
        ys = np.arange(self.top, self.top + self.height, dtype=np.float32) + np.float32(0.5)
        return xs.reshape(1, -1), ys.reshape(-1, 1)

    def distances(self) -> np.ndarray:
        """A distance field for `stamp_segment`, far from everything."""
        return np.full((self.height, self.width), np.float32(1e6), dtype=np.float32)

    def stamp_segment(self, field: np.ndarray, start: Point, end: Point, reach: float) -> None:
        """Lower `field` to the distance from the segment, within `reach` of it."""
        local = _Box.around(start[0], start[1], end[0], end[1], reach)
        if local is None:
            return
        left = max(local.left, self.left)
        top = max(local.top, self.top)
        right = min(local.left + local.width, self.left + self.width)
        bottom = min(local.top + local.height, self.top + self.height)
        if right <= left or bottom <= top:
            return
        part = _Box(left, top, right - left, bottom - top)
        xs, ys = part.centres()
        ax, ay = np.float32(start[0]), np.float32(start[1])
        dx, dy = np.float32(end[0]) - ax, np.float32(end[1]) - ay
        length = dx * dx + dy * dy
        if length > 0:
            t = np.clip(((xs - ax) * dx + (ys - ay) * dy) / length, 0.0, 1.0)
            ox, oy = xs - (ax + t * dx), ys - (ay + t * dy)
        else:
            ox, oy = xs - ax, ys - ay
        distance = np.sqrt(ox * ox + oy * oy)
        window = field[top - self.top : bottom - self.top, left - self.left : right - self.left]
        np.minimum(window, distance, out=window)


def _point_distance(box: _Box, cx: float, cy: float) -> np.ndarray:
    xs, ys = box.centres()
    dx, dy = xs - np.float32(cx), ys - np.float32(cy)
    return np.sqrt(dx * dx + dy * dy)


def _stroke(distance: np.ndarray, half_width: float) -> Alpha:
    """Coverage within `half_width` of a line or point (a stroke or a disc), with a 1 px ramp."""
    return np.clip(np.float32(half_width + 0.5) - distance, 0.0, 1.0)


def _glow(edge_distance: np.ndarray, reach: float, strength: float) -> Alpha:
    """A soft halo outside a shape: `strength` at its edge, fading to nothing at `reach`."""
    fade = np.clip(np.float32(1.0) - np.maximum(edge_distance, 0.0) / np.float32(reach), 0.0, 1.0)
    return fade * fade * np.float32(strength)


class _Patch:
    """A box of the canvas (inside it) lifted to float, so layers blend with one rounding."""

    def __init__(self, canvas: Canvas, box: _Box) -> None:
        self._canvas = canvas
        self._rows = slice(box.top, box.top + box.height)
        self._columns = slice(box.left, box.left + box.width)
        self._under = canvas[self._rows, self._columns].astype(np.float32)

    def paint(self, alpha: Alpha, colour: Colour) -> None:
        """`colour` over what is there, with coverage `alpha` (the box's shape)."""
        change = np.array(colour, dtype=np.float32) - self._under
        change *= alpha[:, :, None]
        self._under += change

    def commit(self) -> None:
        self._canvas[self._rows, self._columns] = np.rint(self._under)


def _blend(canvas: Canvas, box: _Box, alpha: Alpha, colour: Colour) -> None:
    """Paint `colour` at `box` with coverage `alpha`, clipped to the canvas."""
    left, top = max(box.left, 0), max(box.top, 0)
    right, bottom = min(box.left + box.width, WIDTH), min(box.top + box.height, HEIGHT)
    if right <= left or bottom <= top:
        return
    coverage = alpha[top - box.top : bottom - box.top, left - box.left : right - box.left]
    patch = _Patch(canvas, _Box(left, top, right - left, bottom - top))
    patch.paint(coverage, colour)
    patch.commit()


# --- the gesture readout ---


def _number(value: float | None, cap: float = DEBUG_NUMBER_CAP, places: int = 1) -> str:
    """A short fixed-point number, or `--` when there is none."""
    if value is None or not math.isfinite(value):
        return "--"
    return f"{max(0.0, min(cap, value)):.{places}f}"


def _draw_debug(canvas: Canvas, readout: DebugReadout) -> None:
    palm = readout.palm
    _draw_meter(
        canvas,
        DEBUG_TOP,
        f"PALM {_number(palm.score, places=2)}/{_number(palm.threshold, places=2)}",
        fraction=palm.score,
        mark=palm.threshold,
        full=1.0,
        good=palm.counts,
    )
    _draw_meter(
        canvas,
        DEBUG_TOP + DEBUG_ROW,
        f"SPEED {_number(palm.speed)}/{_number(palm.speed_limit)}",
        fraction=palm.speed,
        mark=palm.speed_limit,
        full=palm.speed_limit * DEBUG_SPEED_RANGE,
        good=palm.steady,
    )
    top = DEBUG_TOP + 2 * DEBUG_ROW
    for line, (label, good) in enumerate((("COUNTS", palm.counts), ("STEADY", palm.steady))):
        text = f"{label} {'YES' if good else 'NO'}"
        colour = TEXT_ACTIVE if good else TEXT_PAUSED
        _draw_text(canvas, text, DEBUG_LEFT, top + line * DEBUG_LINE, DEBUG_SIZE, 1, colour)
    fist = readout.fist
    if fist is not None:
        _draw_meter(
            canvas,
            DEBUG_FIST_TOP,
            f"FIST {_number(fist.score, places=2)}/{_number(fist.threshold, places=2)}",
            fraction=fist.score,
            mark=fist.threshold,
            full=1.0,
            good=fist.counts,
        )
        _draw_meter(
            canvas,
            DEBUG_FIST_TOP + DEBUG_ROW,
            f"CURL {_number(fist.curl, places=2)}/{_number(fist.hold_threshold, places=2)}",
            fraction=fist.curl,
            mark=fist.hold_threshold,
            full=1.0,
            good=fist.curl is not None and fist.curl < fist.hold_threshold,
        )
    if readout.scroll is not None:
        _draw_scroll_debug(canvas, readout.scroll)
    for line, (name, milliseconds) in enumerate(readout.timings):
        text = f"{name} {_number(milliseconds)}"
        left = WIDTH - DEBUG_LEFT - _text_width(text, DEBUG_SIZE, DEBUG_TRACKING)
        top = DEBUG_TOP + line * DEBUG_LINE
        _draw_text(canvas, text, left, top, DEBUG_SIZE, DEBUG_TRACKING, STATUS_TEXT)


def _direction(value: float | None) -> str:
    """UP or DOWN for a signed scroll offset or speed, nothing for none or zero."""
    if value is None or value == 0:
        return ""
    return "UP " if value > 0 else "DOWN "


def _draw_scroll_debug(canvas: Canvas, scroll: ScrollReading) -> None:
    _draw_meter(
        canvas,
        DEBUG_SCROLL_TOP,
        f"TWO {_number(scroll.score, places=2)}/{_number(scroll.threshold, places=2)}",
        fraction=scroll.score,
        mark=scroll.threshold,
        full=1.0,
        good=scroll.counts,
    )
    offset = None if scroll.offset is None else abs(scroll.offset)
    _draw_meter(
        canvas,
        DEBUG_SCROLL_TOP + DEBUG_ROW,
        f"OFFSET {_direction(scroll.offset)}"
        f"{_number(offset, places=2)}/{_number(scroll.deadzone, places=2)}",
        fraction=offset,
        mark=scroll.deadzone,
        full=DEBUG_OFFSET_RANGE,
        good=offset is not None and offset > scroll.deadzone,
    )
    rate = f"{_number(abs(scroll.speed), DEBUG_RATE_CAP, 0)}"
    _draw_meter(
        canvas,
        DEBUG_SCROLL_TOP + 2 * DEBUG_ROW,
        f"RATE {_direction(scroll.speed)}{rate}/{_number(scroll.max_speed, DEBUG_RATE_CAP, 0)}",
        fraction=abs(scroll.speed) if scroll.scrolling else None,
        mark=scroll.max_speed,
        full=scroll.max_speed,
        good=scroll.scrolling,
    )


def _fill(canvas: Canvas, left: int, top: int, width: int, height: int, colour: Colour) -> None:
    if width > 0 and height > 0:
        canvas[top : top + height, left : left + width] = colour


def _draw_meter(
    canvas: Canvas,
    top: int,
    text: str,
    *,
    fraction: float | None,
    mark: float,
    full: float,
    good: bool,
) -> None:
    """A line of text at `top` over a bar filled to `fraction` of `full`, with a tick at `mark`."""
    _draw_text(canvas, text, DEBUG_LEFT, top, DEBUG_SIZE, DEBUG_TRACKING, STATUS_TEXT)
    bar_top = top + DEBUG_BAR_OFFSET
    _fill(canvas, DEBUG_LEFT, bar_top, DEBUG_BAR_WIDTH, DEBUG_BAR_HEIGHT, RING_TRACK)
    if fraction is not None and math.isfinite(fraction):
        filled = round(max(0.0, min(1.0, fraction / full)) * DEBUG_BAR_WIDTH)
        colour = TEXT_ACTIVE if good else RING_FILLED
        _fill(canvas, DEBUG_LEFT, bar_top, filled, DEBUG_BAR_HEIGHT, colour)
    tick = DEBUG_LEFT + min(DEBUG_BAR_WIDTH - 1, round(max(0.0, mark / full) * DEBUG_BAR_WIDTH))
    overhang = DEBUG_TICK_OVERHANG
    _fill(canvas, tick, bar_top - overhang, 1, DEBUG_BAR_HEIGHT + 2 * overhang, JOINT)
