"""Calibrate mode (`--calibrate`): see the Hand and the Active region, set up the camera.

The view is the prepared frame (rotate and mirror already applied), so a hand
moved right shows the skeleton moving right. It makes no cursor input: no Controller is
built, and the Preview draws `renderer.render_calibrate`.
"""

from airmouse.config import Config
from airmouse.frame import DEFAULT_SCREEN_ASPECT, Frame, Region, active_region


def region_for(
    config: Config, frame: Frame, screen_aspect: float = DEFAULT_SCREEN_ASPECT
) -> Region:
    """The Active region for a prepared frame, from the config."""
    height, width = frame.shape[:2]
    return active_region(width, height, config.active_region.width_fraction, screen_aspect)
