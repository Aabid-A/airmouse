from dataclasses import dataclass

import pytest

from airmouse.cli import main
from airmouse.permissions import check_permissions


@dataclass
class FakeProbe:
    accessibility: bool = True
    camera: bool = True

    def accessibility_granted(self) -> bool:
        return self.accessibility

    def camera_granted(self) -> bool:
        return self.camera


def test_all_granted_starts_without_noise(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([], probe=FakeProbe()) == 0
    assert capsys.readouterr().err == ""


def test_missing_accessibility_names_it_and_the_terminal_app(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([], probe=FakeProbe(accessibility=False)) == 1

    err = capsys.readouterr().err
    print(err)
    assert "Accessibility" in err
    assert "terminal app" in err
    assert "not to airmouse" in err
    assert "System Settings > Privacy & Security > Accessibility" in err


def test_missing_camera_names_it_and_the_terminal_app(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([], probe=FakeProbe(camera=False)) == 1

    err = capsys.readouterr().err
    print(err)
    assert "Camera" in err
    assert "terminal app" in err
    assert "System Settings > Privacy & Security > Camera" in err


def test_print_config_needs_no_permissions(capsys: pytest.CaptureFixture[str]) -> None:
    probe = FakeProbe(accessibility=False, camera=False)
    assert main(["--print-config"], probe=probe) == 0
    assert "camera" in capsys.readouterr().out


def test_check_permissions_is_none_when_granted() -> None:
    assert check_permissions(FakeProbe()) is None
