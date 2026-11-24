import subprocess
from dataclasses import dataclass

import pytest

from airmouse.cli import main
from airmouse.permissions import MacPermissionProbe, check_permissions


@dataclass
class FakeProbe:
    accessibility: bool = True
    camera: bool = True
    unreadable: str | None = None

    def accessibility_granted(self) -> bool:
        if self.unreadable == "accessibility":
            raise OSError("the ApplicationServices framework was not found")
        return self.accessibility

    def camera_granted(self) -> bool:
        if self.unreadable == "camera":
            raise OSError("AVFoundation could not be loaded")
        return self.camera


def test_all_granted_starts_without_noise(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([], probe=FakeProbe()) == 0
    assert capsys.readouterr().err == ""


def test_missing_accessibility_names_it_and_the_terminal_app(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([], probe=FakeProbe(accessibility=False)) == 1

    err = capsys.readouterr().err
    assert "Accessibility" in err
    assert "terminal app" in err
    assert "not to airmouse" in err
    assert "System Settings > Privacy & Security > Accessibility" in err


def test_missing_camera_names_it_and_the_terminal_app(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([], probe=FakeProbe(camera=False)) == 1

    err = capsys.readouterr().err
    assert "Camera" in err
    assert "terminal app" in err
    assert "System Settings > Privacy & Security > Camera" in err


def test_print_config_needs_no_permissions(capsys: pytest.CaptureFixture[str]) -> None:
    probe = FakeProbe(accessibility=False, camera=False)
    assert main(["--print-config"], probe=probe) == 0
    assert "camera" in capsys.readouterr().out


def test_check_permissions_is_none_when_granted() -> None:
    assert check_permissions(FakeProbe()) is None


@pytest.mark.parametrize(
    ("which", "name"), [("accessibility", "Accessibility"), ("camera", "Camera")]
)
def test_unreadable_status_is_not_reported_as_a_missing_permission(
    capsys: pytest.CaptureFixture[str], which: str, name: str
) -> None:
    assert main([], probe=FakeProbe(unreadable=which)) == 1

    err = capsys.readouterr().err
    assert f"could not check the {name} permission" in err
    assert "not a missing permission" in err
    assert "Privacy & Security" not in err


@dataclass
class FakeChild:
    returncode: int = 0
    stdout: str = ""


def mac_probe(
    returncode: int = 0, stdout: str = "", raises: Exception | None = None
) -> MacPermissionProbe:
    def run(*args: object, **kwargs: object) -> FakeChild:
        if raises is not None:
            raise raises
        return FakeChild(returncode, stdout)

    return MacPermissionProbe(run=run)


@pytest.mark.parametrize(
    ("status", "granted"), [("0", True), ("3", True), ("1", False), ("2", False)]
)
def test_camera_status_from_the_child_process(status: str, granted: bool) -> None:
    assert mac_probe(stdout=f"{status}\n").camera_granted() is granted


@pytest.mark.parametrize(
    "probe",
    [
        mac_probe(returncode=-6),
        mac_probe(returncode=1),
        mac_probe(raises=subprocess.TimeoutExpired(cmd="python", timeout=5)),
        mac_probe(stdout="garbage"),
        mac_probe(stdout=""),
        mac_probe(stdout="7"),
    ],
)
def test_a_broken_camera_check_raises_oserror(probe: MacPermissionProbe) -> None:
    with pytest.raises(OSError, match="camera status check"):
        probe.camera_granted()


def test_an_aborted_camera_check_reports_the_signal() -> None:
    with pytest.raises(OSError, match="signal 6"):
        mac_probe(returncode=-6).camera_granted()


def test_an_aborted_camera_check_is_not_a_missing_permission(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class AccessibleMac(MacPermissionProbe):
        def accessibility_granted(self) -> bool:
            return True

    def run(*args: object, **kwargs: object) -> FakeChild:
        return FakeChild(returncode=-6)

    assert main([], probe=AccessibleMac(run=run)) == 1

    err = capsys.readouterr().err
    assert "could not check the Camera permission" in err
    assert "not a missing permission" in err
