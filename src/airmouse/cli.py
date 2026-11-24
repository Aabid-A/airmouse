"""The `airmouse` command."""

import argparse
from collections.abc import Sequence

from airmouse import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="airmouse",
        description="Control your Mac's cursor by moving your hand in the air.",
    )
    parser.add_argument("--version", action="version", version=f"airmouse {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    # Nothing to run yet: later issues add the camera, tracker and cursor output.
    parser.print_help()
    return 0
