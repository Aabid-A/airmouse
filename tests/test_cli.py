import pytest

from airmouse import __version__
from airmouse.cli import main
from airmouse.config import Config
from airmouse.permissions import PermissionProbe
from conftest import FakePreview


def test_version_flag_prints_the_version(
    capsys: pytest.CaptureFixture[str], granted_probe: PermissionProbe
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"], probe=granted_probe)

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"airmouse {__version__}"


def test_help_flag_describes_the_command(
    capsys: pytest.CaptureFixture[str], granted_probe: PermissionProbe
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"], probe=granted_probe)

    out = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert "usage: airmouse" in out
    assert "--version" in out


def test_no_arguments_runs_the_privacy_preview(
    granted_probe: PermissionProbe, fake_preview: FakePreview
) -> None:
    assert main([], probe=granted_probe, preview=fake_preview) == 0

    [(config, show_camera_image)] = fake_preview.calls
    assert config.camera.index == 0
    assert show_camera_image is False


def test_camera_flags_reach_the_preview_config(
    granted_probe: PermissionProbe, fake_preview: FakePreview
) -> None:
    argv = ["--camera", "1", "--width", "1280", "--height", "720", "--fps", "60"]

    assert main(argv, probe=granted_probe, preview=fake_preview) == 0

    [(config, _)] = fake_preview.calls
    assert (config.camera.index, config.camera.width, config.camera.height) == (1, 1280, 720)
    assert config.camera.fps == 60


def test_the_camera_image_needs_an_explicit_flag(
    granted_probe: PermissionProbe, fake_preview: FakePreview
) -> None:
    assert main(["--show-camera-image"], probe=granted_probe, preview=fake_preview) == 0

    assert fake_preview.calls[0][1] is True


def test_the_preview_does_not_start_without_permissions(fake_preview: FakePreview) -> None:
    class NoCamera:
        def accessibility_granted(self) -> bool:
            return True

        def camera_granted(self) -> bool:
            return False

    assert main([], probe=NoCamera(), preview=fake_preview) == 1
    assert fake_preview.calls == []


def test_the_exit_status_is_the_previews(granted_probe: PermissionProbe) -> None:
    def failing(
        config: Config, *, show_camera_image: bool, calibrate: bool, debug_gestures: bool
    ) -> int:
        return 1

    assert main([], probe=granted_probe, preview=failing) == 1


def test_unknown_flag_is_an_error(
    capsys: pytest.CaptureFixture[str], granted_probe: PermissionProbe
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--nope"], probe=granted_probe)

    assert exit_info.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_calibrate_flag_reaches_the_preview_runner(
    granted_probe: PermissionProbe, fake_preview: FakePreview
) -> None:
    assert main(["--calibrate"], probe=granted_probe, preview=fake_preview) == 0

    assert fake_preview.calibrate == [True]


def test_calibrate_is_off_by_default(
    granted_probe: PermissionProbe, fake_preview: FakePreview
) -> None:
    assert main([], probe=granted_probe, preview=fake_preview) == 0

    assert fake_preview.calibrate == [False]


def test_debug_gestures_is_off_by_default_and_reaches_the_preview_runner(
    granted_probe: PermissionProbe, fake_preview: FakePreview
) -> None:
    assert main([], probe=granted_probe, preview=fake_preview) == 0
    assert main(["--debug-gestures"], probe=granted_probe, preview=fake_preview) == 0

    assert fake_preview.debug_gestures == [False, True]
