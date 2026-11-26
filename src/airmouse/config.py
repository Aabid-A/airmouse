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
    """Relative control mode: how far the cursor moves for a Pointer movement.

    `gain` is display points per hand size of Pointer movement, so the feel is the
    same near or far from the camera. `acceleration` adds gain as the Pointer speeds
    up: the gain is `gain * (1 + acceleration * speed)`, speed in hand sizes per
    second, so 0 means none. `max_gain` caps the gain however fast the hand moves.
    """

    gain: float = _bounded(800.0, low=1.0, high=20000.0)
    acceleration: float = _bounded(0.5, low=0.0, high=10.0)
    max_gain: float = _bounded(3000.0, low=1.0, high=50000.0)


@dataclass(frozen=True)
class ClutchConfig:
    """The Fist clutch: a closed fist held for `debounce_ms` stops the cursor following.

    Each of the four fingers (index included) is measured as wrist-to-tip over
    wrist-to-base distance: `finger_curled` or less counts as fully curled (1) and
    `finger_open` or more as open (0), a straight line between. The Fist score is the
    least curled finger, so one finger out (the Pointer pose) scores 0. The clutch
    counts at `score_threshold` or more. A thumb tip closer than `pinch_gap` hand
    sizes to the index tip is a Pinch, never a Fist.
    """

    score_threshold: float = _bounded(0.6, low=0.0, high=1.0)
    finger_curled: float = _bounded(1.0, low=0.0, high=3.0)
    finger_open: float = _bounded(1.4, low=0.0, high=3.0)
    pinch_gap: float = _bounded(0.3, low=0.0, high=2.0)
    debounce_ms: float = _bounded(100.0, low=0.0, high=2000.0)


@dataclass(frozen=True)
class FilterConfig:
    """One Euro filter settings."""

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
    if config.relative.max_gain < config.relative.gain:
        raise ConfigError("relative.max_gain: must be at least relative.gain")
    if config.clutch.finger_curled >= config.clutch.finger_open:
        raise ConfigError("clutch.finger_curled: must be below clutch.finger_open")
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
