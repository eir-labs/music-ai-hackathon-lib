"""Turning raw readings into control signals you can actually play.

A sensor gives you a number. A musician needs that number in a known range,
free of jitter, and arriving slowly enough that the far end can keep up. These
are the four or five transforms that sit between the two, as small composable
stages.

    from kitlib.signal import Scale, Smooth, RateLimit

    prox = Scale(0, 40) >> Smooth(0.15) >> RateLimit(60)
    value = prox(raw_cm)          # None means "drop this sample"

A stage returns ``None`` to say the sample should not be passed on. Deadband
and RateLimit use this; a chain short-circuits on the first ``None``, so you
never send a message that nothing downstream wanted.

Stages that track time take a ``time_fn`` so they behave identically whether
they are fed by a 650 Hz radar or a 10 Hz thermal camera, and so tests can run
without sleeping.
"""
from __future__ import annotations

import math
import statistics
import time
from collections import deque
from typing import Callable, Optional

Value = Optional[float]


class Stage:
    """One transform. Compose with ``>>``."""

    def __call__(self, value: float) -> Value:
        raise NotImplementedError

    def reset(self) -> None:
        """Forget accumulated state. Safe to call on any stage."""

    def __rshift__(self, other: "Stage") -> "Chain":
        return Chain(self, other)


class Chain(Stage):
    """Stages applied in order, short-circuiting on the first ``None``."""

    def __init__(self, *stages: Stage):
        flat = []
        for stage in stages:
            flat.extend(stage.stages if isinstance(stage, Chain) else [stage])
        self.stages = tuple(flat)

    def __call__(self, value: float) -> Value:
        for stage in self.stages:
            value = stage(value)
            if value is None:
                return None
        return value

    def reset(self) -> None:
        for stage in self.stages:
            stage.reset()

    def __repr__(self) -> str:
        return " >> ".join(repr(s) for s in self.stages)


class Scale(Stage):
    """Map an input range onto an output range, 0..1 by default.

    Clamping is on by default because a sensor that briefly reads outside its
    documented range should not send an RTPC past its own limits.
    """

    def __init__(self, lo: float, hi: float, out_lo: float = 0.0,
                 out_hi: float = 1.0, clamp: bool = True):
        if lo == hi:
            raise ValueError("Scale needs a non-empty input range")
        self.lo, self.hi = float(lo), float(hi)
        self.out_lo, self.out_hi = float(out_lo), float(out_hi)
        self.clamp = clamp

    def __call__(self, value: float) -> Value:
        t = (float(value) - self.lo) / (self.hi - self.lo)
        if self.clamp:
            t = min(max(t, 0.0), 1.0)
        return self.out_lo + t * (self.out_hi - self.out_lo)

    def __repr__(self) -> str:
        return f"Scale({self.lo:g}, {self.hi:g} -> {self.out_lo:g}, {self.out_hi:g})"


class Smooth(Stage):
    """One-pole low pass with a time constant in seconds, not in samples.

    ``tau`` is roughly how long the output takes to cover two thirds of a step.
    Smaller is twitchier. 0.05 keeps a gesture crisp, 0.5 makes a slow swell.
    """

    def __init__(self, tau: float, time_fn: Callable[[], float] = time.monotonic):
        if tau <= 0:
            raise ValueError("Smooth needs a positive time constant")
        self.tau = float(tau)
        self._time = time_fn
        self.reset()

    def reset(self) -> None:
        self._y: Value = None
        self._t = 0.0

    def __call__(self, value: float) -> Value:
        now = self._time()
        if self._y is None:
            self._y, self._t = float(value), now
            return self._y
        dt, self._t = now - self._t, now
        alpha = 1.0 - math.exp(-dt / self.tau) if dt > 0 else 0.0
        self._y += alpha * (float(value) - self._y)
        return self._y

    def __repr__(self) -> str:
        return f"Smooth({self.tau:g})"


class Deadband(Stage):
    """Drop samples that have not moved far enough to be worth sending.

    The reference is the last value that got through, so slow drift still
    accumulates and eventually passes. Use it to stop a resting sensor from
    filling the bus with noise.
    """

    def __init__(self, threshold: float):
        if threshold < 0:
            raise ValueError("Deadband threshold cannot be negative")
        self.threshold = float(threshold)
        self.reset()

    def reset(self) -> None:
        self._last: Value = None

    def __call__(self, value: float) -> Value:
        value = float(value)
        if self._last is None or abs(value - self._last) >= self.threshold:
            self._last = value
            return value
        return None

    def __repr__(self) -> str:
        return f"Deadband({self.threshold:g})"


class RateLimit(Stage):
    """Pass at most ``hz`` samples per second, dropping the rest.

    The radar sweeps at up to 650 Hz. Wwise does not want 650 RTPC writes a
    second and neither does your terminal.
    """

    def __init__(self, hz: float, time_fn: Callable[[], float] = time.monotonic):
        if hz <= 0:
            raise ValueError("RateLimit needs a positive rate")
        self.hz = float(hz)
        self.interval = 1.0 / self.hz
        self._time = time_fn
        self.reset()

    def reset(self) -> None:
        self._last: Value = None

    def __call__(self, value: float) -> Value:
        now = self._time()
        if self._last is None or now - self._last >= self.interval:
            self._last = now
            return float(value)
        return None

    def __repr__(self) -> str:
        return f"RateLimit({self.hz:g})"


class Median(Stage):
    """Rolling median over the last ``n`` samples. Kills isolated spikes.

    The radar reports whichever bin reflects hardest, so a passing hand or a
    metal table leg can jump the reading by a long way for one frame. A median
    of 5 removes that without the lag a mean of 5 would add.
    """

    def __init__(self, n: int = 5):
        if n < 1:
            raise ValueError("Median needs a window of at least 1")
        self.n = int(n)
        self.reset()

    def reset(self) -> None:
        self._window: deque = deque(maxlen=self.n)

    def __call__(self, value: float) -> Value:
        self._window.append(float(value))
        return statistics.median(self._window)

    def __repr__(self) -> str:
        return f"Median({self.n})"


# Ranges taken from sensors/Sensor_Kit_Setup.md, so nobody has to rediscover
# that the force sensor never reaches 1023. Each maps its sensor onto 0..1.
FSR402 = Scale(0, 650)          # non-linear; good for thresholds, not measurement
LIGHT_LS06S = Scale(45, 800)    # dark 45, indoors 600, bright 754; not lux
LOUDNESS = Scale(0, 1023)       # an envelope, not dB; the trimmer changes the gain
JOYSTICK = Scale(200, 800)      # centre sits at X 516 / Y 507, not 512
RADAR_CM = Scale(0, 40)         # 160 points at 2.5 mm

PRESETS = {
    "fsr402": FSR402,
    "light": LIGHT_LS06S,
    "loudness": LOUDNESS,
    "joystick": JOYSTICK,
    "radar": RADAR_CM,
}
