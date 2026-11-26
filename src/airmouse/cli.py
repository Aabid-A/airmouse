"""The `airmouse` command."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from airmouse import __version__
from airmouse.app import run_live_preview
from airmouse.config import (
    CONTROL_MODES,
    ROTATIONS,
    Config,
    ConfigError,
    format_config,
    load_config,
)
from airmouse.permissions import PermissionProbe, check_permissions, platform_probe_or_none


class PreviewRunner(Protocol):
    def __call__(
        self, config: Config, *, show_camera_image: bool, calibrate: bool, debug_gestures: bool
    ) -> int: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="airmouse",
        description="Control your Mac's cursor by moving your hand in the air.",
    )
    parser.add_argument("--version", action="version", version=f"airmouse {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="config file (default: ~/.config/airmouse/config.toml)",
    )
    parser.add_argument(
        "--print-config", action="store_true", help="print every effective setting and exit"
    )
    # Flags override the config file. `default=None` means "not given".
    parser.add_argument("--camera", type=int, metavar="N", help="camera index")
    parser.add_argument("--width", type=int, help="camera frame width in pixels")
    parser.add_argument("--height", type=int, help="camera frame height in pixels")
    parser.add_argument("--fps", type=int, help="camera frames per second")
    parser.add_argument("--rotate", type=int, choices=ROTATIONS, help="rotate the frame (degrees)")
    parser.add_argument(
        "--mirror", action=argparse.BooleanOptionalAction, default=None, help="mirror the frame"
    )
    parser.add_argument(
        "--active-region-width",
        type=float,
        metavar="FRACTION",
        help="Active region width as a fraction of the frame width",
    )
    parser.add_argument(
        "--control-mode",
        metavar="MODE",
        help=f"one of: {', '.join(CONTROL_MODES)} (default: relative, across all displays; "
        "absolute maps the Active region to the main display)",
    )
    parser.add_argument(
        "--show-camera-image",
        action="store_true",
        help="show the camera image in the Preview (default: only the skeleton on a plain "
        "background, so no face or room appears)",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="show the Hand and the Active region to set rotate, mirror and the region "
        "(no cursor input)",
    )
    parser.add_argument(
        "--debug-gestures",
        action="store_true",
        help="draw the Open palm score, the Fist score, the wrist speed against the Hold "
        "ring's steadiness tolerance and per-stage timings in the Preview, to tune the "
        "open_palm and clutch config "
        "(no camera pixels; ignored with --calibrate)",
    )
    return parser


def _overrides(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    flags = {
        ("camera", "index"): args.camera,
        ("camera", "width"): args.width,
        ("camera", "height"): args.height,
        ("camera", "fps"): args.fps,
        ("camera", "rotate"): args.rotate,
        ("camera", "mirror"): args.mirror,
        ("active_region", "width_fraction"): args.active_region_width,
        ("control", "mode"): args.control_mode,
    }
    overrides: dict[str, dict[str, Any]] = {}
    for (section, key), value in flags.items():
        if value is not None:
            overrides.setdefault(section, {})[key] = value
    return overrides


def main(
    argv: Sequence[str] | None = None,
    probe: PermissionProbe | None = None,
    preview: PreviewRunner | None = None,
) -> int:
    """Run the command. `probe` and `preview` are for tests; they default to the real ones."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config, _overrides(args))
    except ConfigError as error:
        parser.error(str(error))
    if args.print_config:
        print(format_config(config))
        return 0
    probe = probe or platform_probe_or_none()
    if probe is not None:
        problem = check_permissions(probe)
        if problem:
            print(problem, file=sys.stderr)
            return 1
    run = preview or run_live_preview
    return run(
        config,
        show_camera_image=args.show_camera_image,
        calibrate=args.calibrate,
        debug_gestures=args.debug_gestures,
    )
