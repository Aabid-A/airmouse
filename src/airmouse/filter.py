"""The One Euro filter (Casiez, Roussel, Vogel 2012) for the cursor.

It smooths hard while the Pointer is slow, so the cursor is steady when the
hand is still, and eases off as the Pointer speeds up, so a fast move does not
lag. `min_cutoff` (Hz) sets the smoothing at rest; `beta` sets how quickly the
cutoff rises with speed. The speed estimate has its own fixed cutoff.
"""

import math

# Cutoff (Hz) of the low-pass on the speed estimate. 1 Hz is the paper's default.
DERIVATIVE_CUTOFF = 1.0


def _alpha(cutoff: float, dt: float) -> float:
    """The low-pass weight of the newest sample for `cutoff` Hz at a step of `dt` seconds."""
    tau = 1 / (2 * math.pi * cutoff)
    return 1 / (1 + tau / dt)


class OneEuroFilter:
    """One axis. State is the last time, filtered value and filtered speed."""

    def __init__(self, min_cutoff: float, beta: float) -> None:
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._last: tuple[float, float, float] | None = None  # time, value, speed

    def reset(self) -> None:
        """Forget the past, so the next sample passes through unchanged."""
        self._last = None

    def __call__(self, time_s: float, value: float) -> float:
        if self._last is None:
            self._last = (time_s, value, 0.0)
            return value
        last_time, last_value, last_speed = self._last
        dt = time_s - last_time
        if dt <= 0:
            return last_value
        speed = last_speed + _alpha(DERIVATIVE_CUTOFF, dt) * (
            (value - last_value) / dt - last_speed
        )
        cutoff = self._min_cutoff + self._beta * abs(speed)
        if cutoff <= 0:
            smoothed = last_value  # no cutoff at all: the output never moves
        else:
            smoothed = last_value + _alpha(cutoff, dt) * (value - last_value)
        self._last = (time_s, smoothed, speed)
        return smoothed
