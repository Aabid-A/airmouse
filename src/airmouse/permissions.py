"""First-run permission check.

macOS grants Accessibility and Camera to the terminal app that runs airmouse,
not to airmouse itself. `check_permissions` turns a missing grant into a message
that says so. The real probe is behind `PermissionProbe` so tests use a fake.
The probe only reads permission status; it never opens the camera or captures a
frame (ADR 0001).
"""

import ctypes
import ctypes.util
import sys
from typing import Protocol

_SETTINGS = "System Settings > Privacy & Security"


class PermissionProbe(Protocol):
    def accessibility_granted(self) -> bool: ...

    def camera_granted(self) -> bool: ...


class MacPermissionProbe:
    """Reads the macOS permission status without prompting or capturing.

    Uses ctypes so no dependency is added. Unverified until run on the Mac.
    """

    def accessibility_granted(self) -> bool:
        library = ctypes.util.find_library("ApplicationServices")
        if library is None:
            return False
        services = ctypes.cdll.LoadLibrary(library)
        services.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(services.AXIsProcessTrusted())

    def camera_granted(self) -> bool:
        # AVAuthorizationStatus: 0 not determined, 1 restricted, 2 denied, 3 authorized.
        # "Not determined" passes: macOS asks the terminal app when the camera first opens.
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc") or "libobjc.dylib")
        ctypes.cdll.LoadLibrary(ctypes.util.find_library("AVFoundation") or "AVFoundation")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
        video = send(
            objc.objc_getClass(b"NSString"), objc.sel_registerName(b"stringWithUTF8String:"), b"vid"
        )
        send.restype = ctypes.c_long
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        status = send(
            objc.objc_getClass(b"AVCaptureDevice"),
            objc.sel_registerName(b"authorizationStatusForMediaType:"),
            video,
        )
        return status not in (1, 2)


def default_probe() -> PermissionProbe:
    return MacPermissionProbe()


def _message(permission: str, pane: str) -> str:
    return (
        f"airmouse needs the {permission} permission.\n"
        f"It is granted to your terminal app (Terminal, iTerm, ...), not to airmouse.\n"
        f"Open {_SETTINGS} > {pane}, turn on your terminal app, then restart the terminal "
        f"and run airmouse again."
    )


def check_permissions(probe: PermissionProbe) -> str | None:
    """Return a message for the first missing permission, or None when all are granted."""
    if not probe.accessibility_granted():
        return _message("Accessibility", "Accessibility")
    if not probe.camera_granted():
        return _message("Camera", "Camera")
    return None


def platform_probe_or_none() -> PermissionProbe | None:
    """The real probe on macOS; None elsewhere (nothing to check yet)."""
    return default_probe() if sys.platform == "darwin" else None
