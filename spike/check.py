# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mediapipe",
#     "pyobjc-framework-Quartz; sys_platform == 'darwin'",
# ]
# ///
"""Spike for issue #2: do the three risky assumptions hold on this Mac?

Run it from the repo root on the Mac:

    uv run spike/check.py --model path/to/hand_landmarker.task 2>/dev/null

The `2>/dev/null` hides MediaPipe's and OpenCV's native log lines, so what you
paste is only the result lines. Drop it if you want to see everything.

It checks three things and prints PASS or FAIL for each:

1. mediapipe: the hand landmarker loads and processes a frame.
2. camera: the camera opens at the size you ask for and delivers frames.
3. accessibility: this terminal may move the cursor (Quartz CGEvent).

The hand model is not bundled with mediapipe. Download it once yourself (this
script never touches the network) and pass its path with --model:

    https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task

This script saves no frame and makes no network call. (`uv run` itself fetches
the script's dependencies the first time.) Paste the output into issue #2.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import platform
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ACCESSIBILITY_LIB = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
ACCESSIBILITY_PATH = "System Settings > Privacy & Security > Accessibility"
CAMERA_PATH = "System Settings > Privacy & Security > Camera"
MIN_FRAME_SHARE = 0.9  # a few dropped frames are fine; most must arrive


@dataclass(frozen=True)
class Step:
    name: str
    ok: bool
    detail: str


def guarded(name: str, check: Callable[[], Step]) -> Step:
    """Turn an unexpected exception into a FAIL, so one step never hides the others."""
    try:
        return check()
    except Exception as error:
        return Step(name, False, f"{type(error).__name__}: {error}")


def check_mediapipe(model: Path | None) -> tuple[Step, Any, Any]:
    """Load the hand landmarker and run it on a blank frame."""
    try:
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions
    except Exception as error:
        detail = f"cannot import mediapipe: {type(error).__name__}: {error}"
        return Step("mediapipe", False, detail), None, None
    version = getattr(mp, "__version__", "?")
    if model is None or not model.is_file():
        detail = (
            f"mediapipe {version} imports, but there is no model file. Download "
            "hand_landmarker.task once (URL in `--help`) and pass it with --model PATH"
        )
        return Step("mediapipe", False, detail), None, None
    try:
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=1,
        )
        landmarker = vision.HandLandmarker.create_from_options(options)
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=blank))
    except Exception as error:
        return Step("mediapipe", False, f"{type(error).__name__}: {error}"), None, None
    detail = f"mediapipe {version} processed a 640x480 frame, {len(result.hand_landmarks)} hands"
    return Step("mediapipe", True, detail), mp, landmarker


def check_camera(args: argparse.Namespace, mp: Any, landmarker: Any) -> Step:
    """Open the camera at the asked size and read frames. Nothing is saved."""
    try:
        import cv2
    except Exception as error:  # ImportError, or a missing system library
        return Step("camera", False, f"cannot import cv2: {type(error).__name__}: {error}")

    backend = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY
    capture = cv2.VideoCapture(args.camera, backend)
    try:
        if not capture.isOpened():
            hint = (
                "On the first run macOS asks for camera access: approve the prompt for "
                f"your terminal and run again. Otherwise check {CAMERA_PATH}."
            )
            return Step("camera", False, f"camera {args.camera} did not open. {hint}")
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        capture.set(cv2.CAP_PROP_FPS, args.fps)
        for _ in range(5):  # let the camera settle
            capture.read()
        delivered = 0
        hands_seen = 0
        width = height = 0
        started = time.perf_counter()
        for _ in range(args.frames):
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            delivered += 1
            height, width = frame.shape[:2]
            if landmarker is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                hands_seen += bool(landmarker.detect(image).hand_landmarks)
        elapsed = time.perf_counter() - started
    finally:
        capture.release()

    rate = delivered / elapsed if elapsed > 0 else 0.0
    rate_label = "pipeline fps (capture + hand detection)" if landmarker else "fps"
    got = f"{width}x{height}"
    asked = f"{args.width}x{args.height}"
    detail = f"asked {asked}, got {got}; {delivered}/{args.frames} frames, {rate:.1f} {rate_label}"
    if landmarker is not None:
        detail += f"; hand seen in {hands_seen}/{delivered} frames (hold a hand up to test)"
    if got != asked:
        detail += ". A different size can just mean the camera snapped to the nearest mode"
    ok = delivered >= args.frames * MIN_FRAME_SHARE and got == asked
    return Step("camera", ok, detail)


def terminal_name() -> str:
    return (
        os.environ.get("TERM_PROGRAM") or os.environ.get("__CFBundleIdentifier") or "your terminal"
    )


def accessibility_trusted() -> bool | None:
    """Ask macOS whether this process may control the computer. None if unknown."""
    try:
        library = ctypes.cdll.LoadLibrary(ACCESSIBILITY_LIB)
        library.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(library.AXIsProcessTrusted())
    except (OSError, AttributeError):
        return None


def check_accessibility(move_points: int) -> Step:
    """Move the cursor and back with Quartz, and read the position to prove it.

    Quartz positions are in points (a Retina point is two pixels).
    """
    if sys.platform != "darwin":
        return Step("accessibility", False, f"not macOS ({platform.system()}): cannot check")
    if accessibility_trusted() is False:
        detail = f"not granted. Add {terminal_name()} under {ACCESSIBILITY_PATH}, then run again"
        return Step("accessibility", False, detail)

    import Quartz

    def cursor() -> tuple[float, float]:
        location = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        return location.x, location.y

    def move_to(x: float, y: float) -> None:
        event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventMouseMoved, (x, y), Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    screen_width = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.width
    x0, y0 = cursor()
    delta = move_points if x0 + move_points < screen_width - 1 else -move_points
    try:
        move_to(x0 + delta, y0)
        time.sleep(0.15)
        x1, y1 = cursor()
    finally:
        move_to(x0, y0)  # always put the cursor back
        time.sleep(0.15)
    x2, y2 = cursor()

    moved = abs((x1 - x0) - delta) <= 2 and abs(y1 - y0) <= 2
    returned = abs(x2 - x0) <= 2 and abs(y2 - y0) <= 2
    if moved and returned:
        return Step("accessibility", True, f"cursor moved {abs(delta)} points and back")
    detail = (
        f"events were posted but the cursor did not follow (moved {x1 - x0:+.0f},{y1 - y0:+.0f}, "
        f"back to {x2 - x0:+.0f},{y2 - y0:+.0f} points). Don't touch the trackpad during the "
        f"test, or add {terminal_name()} under {ACCESSIBILITY_PATH}"
    )
    return Step("accessibility", False, detail)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uv run spike/check.py",
        description="Spike for issue #2: MediaPipe, the camera and Accessibility on this Mac.",
        epilog="Model (download once, by hand): "
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task",
    )
    parser.add_argument("--model", type=Path, help="path to hand_landmarker.task")
    parser.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    parser.add_argument("--width", type=int, default=640, help="frame width (default 640)")
    parser.add_argument("--height", type=int, default=480, help="frame height (default 480)")
    parser.add_argument("--fps", type=int, default=30, help="frames per second (default 30)")
    parser.add_argument("--frames", type=int, default=60, help="frames to read (default 60)")
    parser.add_argument(
        "--move-points",
        type=int,
        default=50,
        help="cursor test distance in points (default 50; a Retina point is 2 pixels)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"airmouse spike (issue #2): {platform.platform()}, {platform.machine()}")
    print(
        f"python {platform.python_version()}. This script saves no frame and makes no network call."
    )
    mediapipe_step, mp, landmarker = check_mediapipe(args.model)
    try:
        steps = [
            mediapipe_step,
            guarded("camera", lambda: check_camera(args, mp, landmarker)),
            guarded("accessibility", lambda: check_accessibility(args.move_points)),
        ]
    finally:
        if landmarker is not None:
            landmarker.close()  # otherwise it fails noisily at interpreter exit
    for step in steps:
        print(f"{'PASS' if step.ok else 'FAIL'}  {step.name}: {step.detail}")
    failed = [step.name for step in steps if not step.ok]
    print("RESULT: all three passed" if not failed else f"RESULT: failed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
