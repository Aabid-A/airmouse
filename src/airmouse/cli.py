"""The `airmouse` command."""

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from airmouse import __version__
from airmouse.config import CONTROL_MODES, ROTATIONS, ConfigError, format_config, load_config


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
        "--control-mode", metavar="MODE", help=f"one of: {', '.join(CONTROL_MODES)}"
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config, _overrides(args))
    except ConfigError as error:
        parser.error(str(error))
    if args.print_config:
        print(format_config(config))
        return 0
    # Nothing to run yet: later issues add the camera, tracker and cursor output.
    parser.print_help()
    return 0
