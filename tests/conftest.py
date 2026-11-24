from typing import NoReturn

import pytest


class GrantedProbe:
    def accessibility_granted(self) -> bool:
        return True

    def camera_granted(self) -> bool:
        return True


@pytest.fixture
def granted_probe() -> GrantedProbe:
    return GrantedProbe()


@pytest.fixture(autouse=True)
def no_real_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> NoReturn:
        pytest.fail("a test reached the real permission probe; pass a fake probe")

    monkeypatch.setattr("airmouse.cli.platform_probe_or_none", fail)
