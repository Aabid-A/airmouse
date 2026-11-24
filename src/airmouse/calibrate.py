"""Calibrate mode (`--calibrate`): see the Hand and the Active region, set up the camera.

The view is the prepared frame (rotate and mirror already applied), so a hand
moved right shows the skeleton moving right. It makes no cursor input.
"""

from airmouse.config import Config
from airmouse.frame import DEFAULT_SCREEN_ASPECT, Frame, Region, active_region
from airmouse.gestures import Landmarks
from airmouse.renderer import Image, render_calibrate


def region_for(
    config: Config, frame: Frame, screen_aspect: float = DEFAULT_SCREEN_ASPECT
) -> Region:
    """The Active region for a prepared frame, from the config."""
    height, width = frame.shape[:2]
    return active_region(width, height, config.active_region.width_fraction, screen_aspect)


def render_calibration(
    config: Config,
    frame: Frame,
    landmarks: Landmarks | None,
    *,
    fps: float | None,
    camera_image: Image | None,
    show_camera_image: bool,
) -> Image:
    """One calibrate-mode view of a prepared `frame` and the Hand found in it."""
    return render_calibrate(
        region_for(config, frame),
        landmarks=landmarks,
        camera_on=True,
        fps=fps,
        camera_image=camera_image,
        show_camera_image=show_camera_image,
    )
