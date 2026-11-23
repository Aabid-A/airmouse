import pytest

from airmouse import __version__
from airmouse.cli import main


def test_version_flag_prints_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"airmouse {__version__}"


def test_help_flag_describes_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    out = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert "usage: airmouse" in out
    assert "--version" in out


def test_no_arguments_shows_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: airmouse" in capsys.readouterr().out


def test_unknown_flag_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--nope"])

    assert exit_info.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
