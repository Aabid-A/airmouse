from pathlib import Path

import pytest

from airmouse.cli import main
from airmouse.config import Config, ConfigError, format_config, load_config
from airmouse.permissions import PermissionProbe
from conftest import FakePreview


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
    assert config.control.mode == "relative"
    assert (config.relative.gain, config.relative.acceleration) == (800, 0.5)
    assert config.relative.max_gain == 3000
    assert (config.clutch.score_threshold, config.clutch.debounce_ms) == (0.6, 100)
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
        ("open_palm", "score_threshold", "nan"),
        ("open_palm", "steady_max_speed", "inf"),
        ("relative", "gain", "nan"),
        ("relative", "acceleration", "inf"),
        ("relative", "max_gain", "inf"),
        ("clutch", "score_threshold", "nan"),
        ("clutch", "debounce_ms", "inf"),
        ("clutch", "hold_threshold", "nan"),
        ("clutch", "tip_curled", "-inf"),
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
        'mode = "relative"',
        "min_cutoff = 1.0",
        "beta = 0.007",
        "close_threshold = 0.25",
        "open_threshold = 0.4",
        "click_window_ms = 300.0",
        "unpause_hold_s = 0.8",
        "pause_debounce_ms = 150.0",
        "no_hand_timeout_ms = 250.0",
        "score_threshold = 0.6",
        "finger_curled = 1.1",
        "finger_extended = 1.6",
        "thumb_weight = 0.1",
        "spread_weight = 0.05",
        "pinch_gap = 0.2",
        "steady_max_speed = 2.5",
        "[relative]",
        "gain = 800.0",
        "acceleration = 0.5",
        "max_gain = 3000.0",
        "[clutch]",
        "finger_open = 1.4",
        "hold_threshold = 0.3",
        "tip_curled = -0.15",
        "tip_open = 0.0",
        "pinch_gap = 0.1",
        "debounce_ms = 100.0",
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
        ('[control]\nmode = "joystick"\n', "control.mode"),
        ("[relative]\ngain = 0\n", "relative.gain"),
        ("[relative]\nacceleration = -1\n", "relative.acceleration"),
        ("[relative]\ngain = 900\nmax_gain = 800\n", "relative.max_gain"),
        ("[relative]\ngian = 900\n", "relative.gian"),
        ("[clutch]\nscore_threshold = 2\n", "clutch.score_threshold"),
        ("[clutch]\ndebounce_ms = -5\n", "clutch.debounce_ms"),
        ("[clutch]\ntip_curled = 0.1\ntip_open = 0.0\n", "clutch.tip_curled"),
        ("[clutch]\nhold_threshold = 0.7\n", "clutch.hold_threshold"),
        ("[clutch]\nhold_threshold = -0.1\n", "clutch.hold_threshold"),
        ("[clutch]\nfinger_curled = 1.6\nfinger_open = 1.4\n", "clutch.finger_curled"),
        ("[pinch]\nclose_threshold = 0.5\nopen_threshold = 0.4\n", "pinch.close_threshold"),
        ("[timing]\nunpause_hold_s = -1\n", "timing.unpause_hold_s"),
        ("[open_palm]\nscore_threshold = 1.5\n", "open_palm.score_threshold"),
        ("[open_palm]\nsteady_max_speed = -1\n", "open_palm.steady_max_speed"),
        ("[open_palm]\nsteady_max_speed = 99\n", "open_palm.steady_max_speed"),
        ('[open_palm]\nscore_threshold = "high"\n', "open_palm.score_threshold"),
        ("[open_palm]\nthumb_weight = 0.9\n", "open_palm.thumb_weight"),
        ("[open_palm]\nfinger_curled = 2.0\nfinger_extended = 1.5\n", "open_palm.finger_curled"),
        (
            "[open_palm]\nthumb_weight = 0.5\nspread_weight = 0.5\n",
            "open_palm.thumb_weight",
        ),
        ("[open_palm]\nspred_weight = 0.1\n", "open_palm.spred_weight"),
    ],
)
def test_invalid_file_names_the_key(tmp_path: Path, toml: str, key: str) -> None:
    with pytest.raises(ConfigError, match=key.replace(".", r"\.")):
        load_config(write(tmp_path, toml))


def test_unknown_control_mode_lists_valid_ones(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="control.mode.*valid values are relative, absolute"):
        load_config(write(tmp_path, '[control]\nmode = "teleport"\n'))


@pytest.mark.parametrize("mode", ["relative", "absolute"])
def test_both_control_modes_come_from_the_file_and_the_flag(tmp_path: Path, mode: str) -> None:
    other = "absolute" if mode == "relative" else "relative"
    path = write(tmp_path, f'[control]\nmode = "{mode}"\n')

    assert load_config(path).control.mode == mode
    assert load_config(path, {"control": {"mode": other}}).control.mode == other


def test_control_mode_flag_reaches_the_preview_config(
    fake_preview: FakePreview, granted_probe: PermissionProbe
) -> None:
    assert main(["--control-mode", "absolute"], probe=granted_probe, preview=fake_preview) == 0

    assert fake_preview.calls[0][0].control.mode == "absolute"


def test_relative_and_clutch_values_come_from_the_file(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "[relative]\ngain = 500\nacceleration = 0\nmax_gain = 500\n"
        "[clutch]\nscore_threshold = 0.7\ndebounce_ms = 50\n",
    )

    config = load_config(path)

    assert (config.relative.gain, config.relative.acceleration) == (500.0, 0.0)
    assert config.relative.max_gain == 500.0
    assert (config.clutch.score_threshold, config.clutch.debounce_ms) == (0.7, 50.0)


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


def test_open_palm_defaults_are_looser_than_the_values_tuned_on_synthetic_frames() -> None:
    palm = load_config().open_palm

    assert palm.steady_max_speed > 1.0  # the old fixed tolerance, in hand sizes per second
    assert palm.thumb_weight + palm.spread_weight <= 0.2  # thumb and spread are weak terms
    assert palm.finger_extended <= 1.6  # the old rule wanted every fingertip 1.5 hand sizes out
    assert 0.0 < palm.score_threshold < 1.0


def test_open_palm_values_come_from_the_file(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "[open_palm]\nscore_threshold = 0.7\nsteady_max_speed = 4\npinch_gap = 0.3\n",
    )

    palm = load_config(path).open_palm

    assert palm.score_threshold == 0.7
    assert palm.steady_max_speed == 4.0
    assert palm.pinch_gap == 0.3
    assert palm.finger_curled == Config().open_palm.finger_curled


def test_open_palm_values_can_be_overridden_after_the_file(tmp_path: Path) -> None:
    path = write(tmp_path, "[open_palm]\nscore_threshold = 0.7\n")

    config = load_config(path, {"open_palm": {"score_threshold": 0.8}})

    assert config.open_palm.score_threshold == 0.8
