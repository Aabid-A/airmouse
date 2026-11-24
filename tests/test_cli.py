import pytest

from airmouse import __version__
from airmouse.cli import main
from airmouse.permissions import PermissionProbe


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


def test_no_arguments_shows_help_and_succeeds(
    capsys: pytest.CaptureFixture[str], granted_probe: PermissionProbe
) -> None:
    assert main([], probe=granted_probe) == 0
    assert "usage: airmouse" in capsys.readouterr().out


def test_unknown_flag_is_an_error(
    capsys: pytest.CaptureFixture[str], granted_probe: PermissionProbe
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--nope"], probe=granted_probe)

    assert exit_info.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
