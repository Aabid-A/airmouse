"""Configuration: defaults in code, an optional TOML file, then CLI overrides.

`load_config` is the one entry point. Every problem (unknown key, wrong type,
out-of-range value, unreadable file) raises `ConfigError` naming the key.
"""

import dataclasses
import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

DEFAULT_CONFIG_PATH = Path("~/.config/airmouse/config.toml")

CONTROL_MODES = ("relative", "absolute")
ROTATIONS = (0, 90, 180, 270)


class ConfigError(Exception):
    """The configuration is invalid. The message names the offending key."""


# Keys that older versions accepted, with what replaced them, so an old config file
# fails with a pointer to the new keys instead of a bare "unknown key".
REMOVED_KEYS = {
    "relative.acceleration": (
        "removed; the gain now rises smoothly from relative.gain to relative.max_gain "
        "between relative.slow_speed and relative.fast_speed"
    ),
}


def _bounded(
    default: Any,
    *,
    low: float | None = None,
    high: float | None = None,
    choices: tuple[Any, ...] | None = None,
) -> Any:
    return field(default=default, metadata={"low": low, "high": high, "choices": choices})


@dataclass(frozen=True)
class CameraConfig:
    """Defaults are the 640x480 at 30 fps the spike (#2) verified on the Mac.

    A sharper picture is a config option: set `width = 1280` and `height = 720`
    under `[camera]` (or use an external or Continuity Camera). It is not the
    default because it has not been verified yet.
    """

    index: int = _bounded(0, low=0)
    width: int = _bounded(640, low=1)
    height: int = _bounded(480, low=1)
    fps: int = _bounded(30, low=1)
    rotate: int = _bounded(0, choices=ROTATIONS)
    mirror: bool = True


@dataclass(frozen=True)
class ActiveRegionConfig:
    """The Active region is centred and keeps the screen's aspect ratio."""

    width_fraction: float = _bounded(0.6, low=0.0, high=1.0)


@dataclass(frozen=True)
class ControlConfig:
    """`relative` (the default) moves the cursor by the Pointer's movement, across all
    displays; `absolute` maps the Active region to the main display (ADR 0002)."""

    mode: str = _bounded("relative", choices=CONTROL_MODES)


@dataclass(frozen=True)
class RelativeConfig:
    """Relative control mode: how far the cursor moves for a Pointer movement, and how
    much the Pointer is smoothed first.

    Gain is display points per hand size of Pointer movement, and speed is in hand
    sizes per second, so the feel is the same near or far from the camera. At
    `slow_speed` or slower the gain is `gain`, for fine aiming; at `fast_speed` or
    faster it is `max_gain`, to cross the screen. In between it rises smoothly (a
    smoothstep curve, with no steps or kinks), so `max_gain` is also the cap.

    `min_cutoff` (Hz) and `beta` (Hz per hand size per second) set the One Euro
    filter on the Pointer in relative mode: its cutoff is `min_cutoff + beta * speed`,
    so it smooths hardest when the hand is slow, which keeps tremor off the cursor,
    and relaxes as the hand speeds up, so a fast move does not lag. Lower `min_cutoff`
    is steadier at rest; higher `beta` is less lag in fast moves.
    """

    gain: float = _bounded(400.0, low=1.0, high=20000.0)
    max_gain: float = _bounded(2500.0, low=1.0, high=50000.0)
    slow_speed: float = _bounded(0.2, low=0.0, high=50.0)
    fast_speed: float = _bounded(3.0, low=0.01, high=50.0)
    min_cutoff: float = _bounded(0.5, low=0.01, high=30.0)
    beta: float = _bounded(5.0, low=0.0, high=100.0)


@dataclass(frozen=True)
class ClutchConfig:
    """The Fist clutch (relative mode): a Fist held for `debounce_ms` stops the cursor.

    Each of the four fingers (index included) is scored from 0 (open) to 1 (curled)
    by two measures, and the lower one counts, so both must agree a finger is curled:

    - where its tip lies along the hand's axis (wrist to the middle finger's base),
      past its own base, in hand sizes: `tip_curled` or less is curled (the tip has
      folded back to the palm) and `tip_open` or more is open. A finger pointing at
      the camera looks short, but its tip still lies beyond its base.
    - wrist-to-tip over wrist-to-base distance: `finger_curled` or less is curled and
      `finger_open` or more is open.

    The finger curl is the least curled finger, so one finger out (the Pointer pose)
    scores 0. The Fist score is the finger curl, except that a thumb tip closer than
    `pinch_gap` hand sizes to the index tip (a Pinch) scores 0. The clutch counts at
    `score_threshold` or more. While the finger curl is at `hold_threshold` or more
    (the fingers may be closing into a Fist) the cursor holds still and the Preview
    says HOLD; below it the cursor follows.
    """

    score_threshold: float = _bounded(0.6, low=0.0, high=1.0)
    hold_threshold: float = _bounded(0.3, low=0.0, high=1.0)
    tip_curled: float = _bounded(-0.15, low=-1.0, high=1.0)
    tip_open: float = _bounded(0.0, low=-1.0, high=1.0)
    finger_curled: float = _bounded(1.0, low=0.0, high=3.0)
    finger_open: float = _bounded(1.4, low=0.0, high=3.0)
    pinch_gap: float = _bounded(0.1, low=0.0, high=2.0)
    debounce_ms: float = _bounded(100.0, low=0.0, high=2000.0)


@dataclass(frozen=True)
class FilterConfig:
    """One Euro filter settings for absolute control mode, in display pixels.

    Relative mode has its own, in hand sizes (`RelativeConfig.min_cutoff`, `beta`).
    """

    min_cutoff: float = _bounded(1.0, low=0.0)
    beta: float = _bounded(0.007, low=0.0)


@dataclass(frozen=True)
class PinchConfig:
    close_threshold: float = _bounded(0.25, low=0.0)
    open_threshold: float = _bounded(0.40, low=0.0)
    click_window_ms: float = _bounded(300.0, low=0.0)


@dataclass(frozen=True)
class TimingConfig:
    unpause_hold_s: float = _bounded(0.8, low=0.0)
    pause_debounce_ms: float = _bounded(150.0, low=0.0)
    no_hand_timeout_ms: float = _bounded(250.0, low=0.0)


@dataclass(frozen=True)
class OpenPalmConfig:
    """The Open palm check and the steadiness the Hold ring needs.

    The score runs from 0 to 1 and the palm counts at `score_threshold` or more.
    Each of the four fingers earns 0 when its tip is `finger_curled` hand sizes
    from the wrist and 1 at `finger_extended` or more. The thumb and the spread
    of the fingertips add a weak bonus (their weights), so fingers held close
    together still count. A thumb tip closer than `pinch_gap` hand sizes to the
    index tip is a Pinch, never an Open palm. `steady_max_speed` is how fast the
    wrist may move, in hand sizes per second, for the Hold ring to keep filling.
    """

    score_threshold: float = _bounded(0.6, low=0.0, high=1.0)
    finger_curled: float = _bounded(1.1, low=0.0, high=3.0)
    finger_extended: float = _bounded(1.6, low=0.0, high=3.0)
    thumb_weight: float = _bounded(0.1, low=0.0, high=0.5)
    spread_weight: float = _bounded(0.05, low=0.0, high=0.5)
    pinch_gap: float = _bounded(0.2, low=0.0, high=2.0)
    steady_max_speed: float = _bounded(2.5, low=0.0, high=50.0)


@dataclass(frozen=True)
class ScrollConfig:
    """The Scroll: index and middle raised together, ring and pinky curled, then the Hand
    moved up or down from where the pose started (the anchor). Works in both control modes.

    Pose: each finger is scored by how far its tip is from the wrist, in hand sizes. A
    raised finger (index, middle) earns 0 at `finger_curled` or less and 1 at
    `finger_extended` or more; a curled finger (ring, pinky) the other way round. The
    two-finger score is the weakest of the four and counts at `score_threshold` or more,
    held for `debounce_ms` before scrolling starts. The defaults are loose, so a relaxed
    two-finger pose counts; `--debug-gestures` shows the score for tuning.

    Motion: rate-based. A vertical offset from the anchor of `deadzone` hand sizes or
    less does nothing; past it the speed is `gain` pixels per second for each hand size
    beyond the deadzone, capped at `max_speed` pixels per second. The Hand up scrolls up
    (content above comes into view); `invert = true` flips that.
    """

    deadzone: float = _bounded(0.15, low=0.0, high=2.0)
    gain: float = _bounded(2500.0, low=1.0, high=50000.0)
    max_speed: float = _bounded(1500.0, low=1.0, high=20000.0)
    invert: bool = False
    score_threshold: float = _bounded(0.5, low=0.01, high=1.0)  # above 0: a score of 0 never counts
    finger_curled: float = _bounded(1.0, low=0.0, high=3.0)
    finger_extended: float = _bounded(1.4, low=0.0, high=3.0)
    debounce_ms: float = _bounded(120.0, low=0.0, high=2000.0)


@dataclass(frozen=True)
class Config:
    camera: CameraConfig = CameraConfig()
    active_region: ActiveRegionConfig = ActiveRegionConfig()
    control: ControlConfig = ControlConfig()
    filter: FilterConfig = FilterConfig()
    pinch: PinchConfig = PinchConfig()
    timing: TimingConfig = TimingConfig()
    open_palm: OpenPalmConfig = OpenPalmConfig()
    relative: RelativeConfig = RelativeConfig()
    clutch: ClutchConfig = ClutchConfig()
    scroll: ScrollConfig = ScrollConfig()


def _check_value(key: str, spec: dataclasses.Field[Any], value: Any) -> Any:
    expected = spec.type
    if expected is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if not isinstance(expected, type) or type(value) is not expected:
        raise ConfigError(
            f"{key}: expected {getattr(expected, '__name__', expected)}, "
            f"got {type(value).__name__} ({value!r})"
        )
    choices = spec.metadata.get("choices")
    if choices is not None and value not in choices:
        valid = ", ".join(str(c) for c in choices)
        raise ConfigError(f"{key}: {value!r} is not valid; valid values are {valid}")
    if expected is float and not math.isfinite(value):
        raise ConfigError(f"{key}: {value!r} is not a finite number")
    low, high = spec.metadata.get("low"), spec.metadata.get("high")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ConfigError(f"{key}: {value!r} is out of range ({_range_text(low, high)})")
    return value


def _range_text(low: float | None, high: float | None) -> str:
    if low is not None and high is not None:
        return f"{low} to {high}"
    return f"at least {low}" if low is not None else f"at most {high}"


def _build_section(name: str, cls: type, raw: Mapping[str, Any]) -> Any:
    specs = {f.name: f for f in dataclasses.fields(cls)}
    values: dict[str, Any] = {}
    for key, value in raw.items():
        removed = REMOVED_KEYS.get(f"{name}.{key}")
        if removed is not None:
            raise ConfigError(f"{name}.{key}: {removed}")
        if key not in specs:
            raise ConfigError(f"{name}.{key}: unknown key; valid keys are {', '.join(specs)}")
        values[key] = _check_value(f"{name}.{key}", specs[key], value)
    return cls(**values)


def _build(raw: Mapping[str, Any]) -> Config:
    sections: dict[str, Any] = {f.name: f.type for f in dataclasses.fields(Config)}
    built: dict[str, Any] = {}
    for name, value in raw.items():
        if name not in sections:
            raise ConfigError(f"{name}: unknown section; valid sections are {', '.join(sections)}")
        if not isinstance(value, Mapping):
            raise ConfigError(f"{name}: expected a table, got {type(value).__name__}")
        built[name] = _build_section(name, sections[name], cast("Mapping[str, Any]", value))
    config = Config(**built)
    if config.pinch.close_threshold >= config.pinch.open_threshold:
        raise ConfigError("pinch.close_threshold: must be below pinch.open_threshold")
    palm = config.open_palm
    if palm.finger_curled >= palm.finger_extended:
        raise ConfigError("open_palm.finger_curled: must be below open_palm.finger_extended")
    if palm.thumb_weight + palm.spread_weight >= 1:
        raise ConfigError("open_palm.thumb_weight: with open_palm.spread_weight must total below 1")
    relative = config.relative
    if relative.max_gain < relative.gain:
        raise ConfigError("relative.max_gain: must be at least relative.gain")
    if relative.slow_speed >= relative.fast_speed:
        raise ConfigError("relative.slow_speed: must be below relative.fast_speed")
    clutch = config.clutch
    if clutch.finger_curled >= clutch.finger_open:
        raise ConfigError("clutch.finger_curled: must be below clutch.finger_open")
    if clutch.tip_curled >= clutch.tip_open:
        raise ConfigError("clutch.tip_curled: must be below clutch.tip_open")
    if clutch.hold_threshold > clutch.score_threshold:
        raise ConfigError("clutch.hold_threshold: must be at most clutch.score_threshold")
    if config.scroll.finger_curled >= config.scroll.finger_extended:
        raise ConfigError("scroll.finger_curled: must be below scroll.finger_extended")
    return config


def _merge(base: dict[str, Any], extra: Mapping[str, Mapping[str, Any]]) -> None:
    for section, values in extra.items():
        merged: dict[str, Any] = {}
        existing: Any = base.get(section)
        if isinstance(existing, dict):
            merged.update(cast("dict[str, Any]", existing))
        merged.update(values)
        base[section] = merged


def read_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError as error:
        raise ConfigError(f"{path}: cannot read config file ({error.strerror})") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: invalid TOML ({error})") from error


def load_config(
    path: Path | None = None,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> Config:
    """Defaults, then the TOML file, then `overrides` ({section: {key: value}}).

    An explicit `path` must exist. With no path, the default file is used only
    if it exists.
    """
    raw: dict[str, Any] = {}
    if path is not None:
        raw = read_file(path.expanduser())
    else:
        default = DEFAULT_CONFIG_PATH.expanduser()
        if default.is_file():
            raw = read_file(default)
    _merge(raw, overrides or {})
    return _build(raw)


def format_config(config: Config) -> str:
    """The effective values as TOML, so the output can be saved as a config file."""
    lines: list[str] = []
    for section in dataclasses.fields(config):
        lines.append(f"[{section.name}]")
        values = getattr(config, section.name)
        for item in dataclasses.fields(values):
            lines.append(f"{item.name} = {_toml_value(getattr(values, item.name))}")
        lines.append("")
    return "\n".join(lines)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)
