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

CONTROL_MODES = ("absolute",)
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
    mode: str = _bounded("absolute", choices=CONTROL_MODES)


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
class Config:
    camera: CameraConfig = CameraConfig()
    active_region: ActiveRegionConfig = ActiveRegionConfig()
    control: ControlConfig = ControlConfig()
    filter: FilterConfig = FilterConfig()
    pinch: PinchConfig = PinchConfig()
    timing: TimingConfig = TimingConfig()


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
