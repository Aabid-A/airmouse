from pathlib import Path

import pytest

from airmouse.cli import main
from airmouse.config import Config, ConfigError, format_config, load_config
from airmouse.permissions import PermissionProbe


@pytest.fixture(autouse=True)
def no_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_defaults_match_the_spec() -> None:
    config = load_config()

    assert config == Config()
    assert (config.camera.index, config.camera.rotate, config.camera.mirror) == (0, 0, True)
    assert config.active_region.width_fraction == 0.6
    assert config.control.mode == "absolute"
    assert (config.pinch.close_threshold, config.pinch.open_threshold) == (0.25, 0.40)
    assert config.pinch.click_window_ms == 300
    assert config.timing.unpause_hold_s == 0.8
    assert config.timing.pause_debounce_ms == 150
    assert config.timing.no_hand_timeout_ms == 250


def test_file_overrides_defaults(tmp_path: Path) -> None:
    path = write(tmp_path, "[camera]\nindex = 2\nmirror = false\n[filter]\nbeta = 1\n")

    config = load_config(path)

    assert config.camera.index == 2
    assert config.camera.mirror is False
    assert config.filter.beta == 1.0
    assert config.camera.width == Config().camera.width


def test_default_file_location_is_read(tmp_path: Path) -> None:
    default = tmp_path / "home" / ".config" / "airmouse" / "config.toml"
    default.parent.mkdir(parents=True)
    default.write_text("[camera]\nindex = 3\n")

    assert load_config().camera.index == 3


def test_default_camera_is_the_spike_verified_640x480_at_30() -> None:
    camera = load_config().camera

    assert (camera.width, camera.height, camera.fps) == (640, 480, 30)


def test_720p_is_a_config_option(tmp_path: Path) -> None:
    path = write(tmp_path, "[camera]\nwidth = 1280\nheight = 720\n")

    camera = load_config(path).camera

    assert (camera.width, camera.height) == (1280, 720)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("active_region", "width_fraction", "nan"),
        ("timing", "unpause_hold_s", "inf"),
        ("filter", "beta", "-inf"),
    ],
)
def test_non_finite_numbers_are_rejected(
    tmp_path: Path, section: str, key: str, value: str
) -> None:
    path = write(tmp_path, f"[{section}]\n{key} = {value}\n")

    with pytest.raises(ConfigError, match=f"{section}.{key}"):
        load_config(path)


def test_flags_override_the_file(tmp_path: Path) -> None:
    path = write(tmp_path, "[camera]\nindex = 2\nwidth = 640\n")

    config = load_config(path, {"camera": {"index": 5}})

    assert config.camera.index == 5
    assert config.camera.width == 640


def test_cli_flag_overrides_file_in_print_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], granted_probe: PermissionProbe
) -> None:
    path = write(tmp_path, "[camera]\nindex = 2\n")

    argv = ["--config", str(path), "--camera", "7", "--print-config"]
    assert main(argv, probe=granted_probe) == 0

    assert "index = 7" in capsys.readouterr().out


def test_print_config_lists_every_effective_value(
    capsys: pytest.CaptureFixture[str], granted_probe: PermissionProbe
) -> None:
    assert main(["--print-config"], probe=granted_probe) == 0

    out = capsys.readouterr().out
    for expected in [
        "index = 0",
        "width = 640",
        "height = 480",
        "fps = 30",
        "rotate = 0",
        "mirror = true",
        "width_fraction = 0.6",
        'mode = "absolute"',
        "min_cutoff = 1.0",
        "beta = 0.007",
        "close_threshold = 0.25",
        "open_threshold = 0.4",
        "click_window_ms = 300.0",
        "unpause_hold_s = 0.8",
        "pause_debounce_ms = 150.0",
        "no_hand_timeout_ms = 250.0",
    ]:
        assert expected in out


def test_printed_config_loads_back_unchanged(tmp_path: Path) -> None:
    path = write(tmp_path, format_config(Config()))

    assert load_config(path) == Config()


@pytest.mark.parametrize(
    ("toml", "key"),
    [
        ("[camera]\nindx = 1\n", "camera.indx"),
        ("[cmaera]\nindex = 1\n", "cmaera"),
        ('[camera]\nindex = "one"\n', "camera.index"),
        ("[camera]\nindex = true\n", "camera.index"),
        ("[camera]\nrotate = 45\n", "camera.rotate"),
        ("[camera]\nfps = 0\n", "camera.fps"),
        ("[active_region]\nwidth_fraction = 1.5\n", "active_region.width_fraction"),
        ('[control]\nmode = "relative"\n', "control.mode"),
        ("[pinch]\nclose_threshold = 0.5\nopen_threshold = 0.4\n", "pinch.close_threshold"),
        ("[timing]\nunpause_hold_s = -1\n", "timing.unpause_hold_s"),
    ],
)
def test_invalid_file_names_the_key(tmp_path: Path, toml: str, key: str) -> None:
    with pytest.raises(ConfigError, match=key.replace(".", r"\.")):
        load_config(write(tmp_path, toml))


def test_unknown_control_mode_lists_valid_ones(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="valid values are absolute"):
        load_config(write(tmp_path, '[control]\nmode = "teleport"\n'))


def test_invalid_flag_value_names_the_key() -> None:
    with pytest.raises(ConfigError, match=r"camera\.index"):
        load_config(None, {"camera": {"index": -1}})


def test_missing_explicit_file_and_bad_toml_are_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "nope.toml")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(write(tmp_path, "[camera\n"))


def test_cli_exits_non_zero_and_names_the_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], granted_probe: PermissionProbe
) -> None:
    path = write(tmp_path, "[camera]\nindx = 1\n")

    with pytest.raises(SystemExit) as exit_info:
        main(["--config", str(path), "--print-config"], probe=granted_probe)

    assert exit_info.value.code != 0
    assert "camera.indx" in capsys.readouterr().err
