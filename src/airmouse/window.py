"""The Preview window, behind a small adapter (an OpenCV window)."""

import importlib
from typing import Any, Protocol

from airmouse.renderer import Image

WINDOW_TITLE = "airmouse Preview"
DISPLAY_SCALE = 2  # the Preview is drawn at 640x360 (16:9); show it at 1280x720
QUIT_KEY = "q"


class Window(Protocol):
    def show(self, image: Image) -> None: ...

    def quit_requested(self) -> bool:
        """True once the user pressed `q` or closed the window."""
        ...

    def close(self) -> None: ...


class OpenCvWindow:
    def __init__(self) -> None:
        self._cv2: Any = importlib.import_module("cv2")
        self._numpy: Any = importlib.import_module("numpy")
        self._cv2.namedWindow(WINDOW_TITLE, self._cv2.WINDOW_AUTOSIZE)
        self._shown = False

    def show(self, image: Image) -> None:
        cv2 = self._cv2
        rgb = self._numpy.frombuffer(image.pixels, dtype=self._numpy.uint8)
        rgb = rgb.reshape(image.height, image.width, 3)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        size = (image.width * DISPLAY_SCALE, image.height * DISPLAY_SCALE)
        cv2.imshow(WINDOW_TITLE, cv2.resize(bgr, size, interpolation=cv2.INTER_LINEAR))
        self._shown = True

    def quit_requested(self) -> bool:
        cv2 = self._cv2
        key = cv2.waitKey(1) & 0xFF
        closed = self._shown and cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1
        return key == ord(QUIT_KEY) or closed

    def close(self) -> None:
        self._cv2.destroyAllWindows()
        self._cv2.waitKey(1)  # lets macOS actually close the window
