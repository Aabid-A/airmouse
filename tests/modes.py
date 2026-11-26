"""Run a test module in both control modes.

A module that should hold in absolute and relative mode alike says
`pytestmark = pytest.mark.usefixtures("control_mode")` (the fixture is in
conftest.py), and builds its configs with `base_config()` instead of `Config()`.
Every test in the module then runs twice, once per mode, with every assertion
unchanged.
"""

from airmouse.config import ClutchConfig, Config, ControlConfig

MODES = ("absolute", "relative")
_current = [Config(control=ControlConfig(mode="absolute"))]


def base_config() -> Config:
    """The default Config, in the control mode the running test was given."""
    return _current[0]


def clutch_for(config: Config) -> ClutchConfig | None:
    """The clutch the app gives the Controller: relative mode only."""
    return config.clutch if config.control.mode == "relative" else None


def use_mode(mode: str) -> Config:
    """Make `base_config()` give `mode` until the next call; returns the old default."""
    previous = _current[0]
    _current[0] = Config(control=ControlConfig(mode=mode))
    return previous


def restore(previous: Config) -> None:
    _current[0] = previous
