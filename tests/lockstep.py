"""Lock step for tests that check the Preview frame by frame.

The worker and the Preview run on their own threads, so the worker can track
several frames while the Preview shows one. Tests that compare the Nth image with
the Nth frame wrap their fake camera and window with `lockstep`: the camera then
gives the next frame only once the window has shown the Snapshot of the last one,
so image N is frame N. Once the window quits (or is closed, or raises) the gate
opens for good and the worker runs freely until it is stopped. Every wait has a
timeout, so a bug fails the test instead of hanging it.
"""

import threading
from typing import Any

from airmouse.camera import Camera
from airmouse.renderer import Image
from airmouse.window import Window

WAIT_S = 5.0


class LockstepStalled(AssertionError):
    """The worker waited too long for the window to show a frame."""


class Gate:
    def __init__(self) -> None:
        self._changed = threading.Condition()
        self._credits = 0
        self._open = False

    def give(self) -> None:
        with self._changed:
            self._credits += 1
            self._changed.notify_all()

    def open(self) -> None:
        with self._changed:
            self._open = True
            self._changed.notify_all()

    def take(self) -> None:
        with self._changed:
            if not self._changed.wait_for(lambda: self._open or self._credits > 0, WAIT_S):
                raise LockstepStalled("the window never showed the last frame")
            if not self._open:
                self._credits -= 1


class LockstepCamera:
    def __init__(self, camera: Camera, gate: Gate) -> None:
        self._camera = camera
        self._gate = gate
        self._gave_frame = False  # the last read gave a frame, so the window must show it first

    def read(self) -> Any:
        if self._gave_frame:
            self._gate.take()
        frame = self._camera.read()
        self._gave_frame = frame is not None
        return frame

    def release(self) -> None:
        self._gate.open()
        self._camera.release()


class LockstepWindow:
    def __init__(self, window: Window, gate: Gate) -> None:
        self._window = window
        self._gate = gate

    def show(self, image: Image) -> None:
        try:
            self._window.show(image)
        except BaseException:
            self._gate.open()
            raise
        self._gate.give()

    def quit_requested(self) -> bool:
        try:
            quit_requested = self._window.quit_requested()
        except BaseException:
            self._gate.open()
            raise
        if quit_requested:
            self._gate.open()
        return quit_requested

    def close(self) -> None:
        self._gate.open()
        self._window.close()


def lockstep(camera: Camera, window: Window) -> tuple[LockstepCamera, LockstepWindow]:
    gate = Gate()
    return LockstepCamera(camera, gate), LockstepWindow(window, gate)


class ThreadClock:
    """A fake timer that steps by `step` per call, counted separately on each thread.

    The worker and the Preview both read the timer; one shared counter would make
    the timings depend on how the threads interleave.
    """

    def __init__(self, step: float) -> None:
        self._step = step
        self._local = threading.local()

    def __call__(self) -> float:
        now: float = getattr(self._local, "now", 0.0) + self._step
        self._local.now = now
        return now
