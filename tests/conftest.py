import threading
from collections.abc import Iterator
from typing import NoReturn

import pytest

from airmouse.config import Config
from airmouse.pipeline import WORKER_NAME


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


@pytest.fixture(autouse=True)
def no_live_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("a test reached the real camera; pass a fake `preview` to main()")

    monkeypatch.setattr("airmouse.cli.run_live_preview", fail)


@pytest.fixture(autouse=True)
def no_leftover_worker() -> Iterator[None]:
    """Every test that starts the worker thread must see it end: none is left running."""
    yield
    for thread in threading.enumerate():
        if thread.name == WORKER_NAME:
            thread.join(5.0)
            if thread.is_alive():
                pytest.fail("a test left the worker thread running")


class FakePreview:
    """Stands in for the live Preview: records what main() asked for."""

    def __init__(self) -> None:
        self.calls: list[tuple[Config, bool]] = []
        self.calibrate: list[bool] = []
        self.debug_gestures: list[bool] = []

    def __call__(
        self, config: Config, *, show_camera_image: bool, calibrate: bool, debug_gestures: bool
    ) -> int:
        self.calls.append((config, show_camera_image))
        self.calibrate.append(calibrate)
        self.debug_gestures.append(debug_gestures)
        return 0


@pytest.fixture
def fake_preview() -> FakePreview:
    return FakePreview()
