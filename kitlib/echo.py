"""Measuring a space by listening to it, and knowing how sure you are.

Play an exponential sine sweep, record it, deconvolve, and what comes back is
the impulse response of wherever you are standing. The peaks in it are the
surfaces that reflected the sound, and the delay of each peak is how far away
that surface is.

    sw = sweep(seconds=10)
    # play sw.signal, record it, then
    ir = deconvolve(recording, sw)
    for r in reflections(ir):
        print(r.distance(celsius=5))

The second half is the part that matters musically. Measure the same place
several times and the readings from a still scene agree, while a moving one
does not. ``Survey`` accumulates repeats and turns that agreement into a
confidence between 0 and 1 which rises as evidence accumulates and falls when
the medium will not sit still. No model is trained and none needs to be: the
number is the standard error of the estimate, so it improves with evidence on
its own.

    survey = Survey(celsius=5)
    for recording in captures:
        survey.add(reflections(deconvolve(recording, sw)))
    survey.confidence      # 0 after one capture, rising as repeats agree

Needs ``pip install kitlib[echo]`` for NumPy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

#: What a field recorder and a laptop interface both do without being asked.
RATE = 48000

#: Room temperature, for anyone who does not pass one. At a mountain lake in
#: September this will be wrong by enough to matter; measure it and pass it.
ROOM_C = 20.0


#: Student's t at 95% for small samples, so that agreement between two
#: captures is not mistaken for agreement between ten. Beyond this table the
#: normal value is close enough.
_T_95 = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57, 7: 2.45,
         8: 2.36, 9: 2.31, 10: 2.26, 12: 2.20, 15: 2.14, 20: 2.09}


def _STUDENT(count: int) -> float:
    if count in _T_95:
        return _T_95[count]
    known = [n for n in _T_95 if n <= count]
    return _T_95[max(known)] if known and count < 20 else 1.96


def speed_of_sound(celsius: float = ROOM_C) -> float:
    """Metres per second in dry air at ``celsius``.

    Temperature is the term that matters. Altitude and humidity move this by
    far less than the difference between a warm room and a cold lake, and using
    the 343 m/s everyone quotes puts every distance out by about three percent
    at 5 degrees.
    """
    return 331.3 + 0.606 * float(celsius)


# -- the excitation ------------------------------------------------------

@dataclass(frozen=True)
class Sweep:
    """An exponential sine sweep and the filter that inverts it.

    The two belong together because the inverse only undoes the sweep it was
    derived from, and pairing them by hand is how a measurement session ends up
    with a smeared impulse response nobody can explain.
    """

    signal: np.ndarray
    inverse: np.ndarray
    seconds: float
    rate: int
    low: float
    high: float

    def __len__(self) -> int:
        return len(self.signal)

    def __repr__(self) -> str:
        return (f"Sweep({self.seconds:g}s, {self.low:g}-{self.high:g} Hz, "
                f"{self.rate} Hz)")


def sweep(seconds: float = 10.0, rate: int = RATE, low: float = 50.0,
          high: float = 18000.0, fade: float = 0.05) -> Sweep:
    """An exponential sine sweep, with its inverse filter.

    Exponential rather than linear because it spends equal time in every
    octave, which puts energy where a large cold space actually reflects, and
    because it pushes the loudspeaker's harmonic distortion into a separate
    lump ahead of the impulse response where it can be windowed away.

    Outdoors, shorter and repeated beats longer and once. A sweep only averages
    correctly while the air holds still, and over tens of seconds at a lake it
    will not. Ten seconds is a reasonable compromise; drop to five if it is
    windy, and let ``Survey`` tell you whether it worked.

    ``fade`` is the raised-cosine taper at each end, in seconds, which stops
    the loudspeaker being asked to start and stop instantaneously.
    """
    if seconds <= 0:
        raise ValueError("a sweep needs a positive duration")
    if not 0 < low < high:
        raise ValueError(f"need 0 < low < high, got low={low}, high={high}")
    if high > rate / 2:
        raise ValueError(
            f"high of {high:g} Hz is above the Nyquist limit of {rate / 2:g} Hz")

    count = int(round(seconds * rate))
    t = np.arange(count) / float(rate)
    ratio = math.log(high / low)

    signal = np.sin((2 * np.pi * low * seconds / ratio)
                    * (np.exp(t * ratio / seconds) - 1.0))
    envelope = _taper(count, rate, fade)
    signal = signal * envelope

    # Farina's inverse: the sweep backwards, with the amplitude falling at the
    # same exponential rate, which undoes the pink tilt an exponential sweep
    # has by construction.
    inverse = signal[::-1] * np.exp(-t * ratio / seconds)
    inverse = inverse / np.sqrt(np.sum(inverse ** 2))

    return Sweep(signal=signal, inverse=inverse, seconds=float(seconds),
                 rate=int(rate), low=float(low), high=float(high))


def _taper(count: int, rate: int, fade: float) -> np.ndarray:
    """A raised-cosine window on each end, flat in between."""
    window = np.ones(count)
    edge = min(int(round(fade * rate)), count // 2)
    if edge > 0:
        ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(edge) / edge))
        window[:edge] = ramp
        window[-edge:] = ramp[::-1]
    return window


# -- recovering the impulse response -------------------------------------

def deconvolve(recording: Sequence[float], excitation: Sweep) -> np.ndarray:
    """The impulse response of whatever the recording was made in.

    Convolution with the inverse filter, done through the frequency domain
    because a ten-second sweep against a fifteen-second recording is tens of
    billions of multiplies done directly and about a second done this way.

    The result is not trimmed. Everything downstream measures delays relative
    to the direct arrival rather than to the start of the array, so there is
    no alignment to get wrong and no need to know when the sweep began.
    """
    recorded = np.asarray(recording, dtype=float).ravel()
    if recorded.size == 0:
        raise ValueError("nothing to deconvolve: the recording is empty")
    return _convolve(recorded, excitation.inverse)


def _convolve(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    total = len(a) + len(b) - 1
    size = 1 << (total - 1).bit_length()
    spectrum = np.fft.rfft(a, size) * np.fft.rfft(b, size)
    return np.fft.irfft(spectrum, size)[:total]


# -- reading the geometry out of it --------------------------------------

@dataclass(frozen=True)
class Reflection:
    """One surface that sent the sound back.

    ``delay`` is measured from the direct arrival, not from the start of the
    recording, which is what makes several recorders usable together without
    synchronising a single clock between them. Each one is its own reference.
    """

    delay: float        #: seconds after the direct arrival
    amplitude: float    #: relative to the direct arrival, so 1.0 is as loud

    def path(self, celsius: float = ROOM_C) -> float:
        """Extra distance the sound travelled, in metres."""
        return self.delay * speed_of_sound(celsius)

    def distance(self, celsius: float = ROOM_C) -> float:
        """Metres to the surface, assuming the speaker and microphone are together.

        Separate them and a delay no longer describes a circle around one point
        but an ellipse with the speaker and microphone at its foci, and this
        number becomes half the total path instead of the distance. Co-locate
        them if you want this to mean what it says.
        """
        return self.path(celsius) / 2.0

    def __repr__(self) -> str:
        return f"Reflection({self.delay * 1000:.1f} ms, {self.amplitude:.3f})"


def reflections(ir: Sequence[float], rate: int = RATE, floor_db: float = -30.0,
                separation: float = 0.002, limit: int = 16,
                blank: Optional[float] = None) -> List[Reflection]:
    """The surfaces an impulse response says are out there, loudest first found.

    The direct arrival is the largest peak and becomes the reference rather
    than a reflection. Everything after it that rises above ``floor_db``
    relative to that peak, and stands at least ``separation`` seconds clear of
    a louder neighbour, is reported.

    ``blank`` is how long after the direct arrival to ignore, defaulting to
    ``separation``. Deconvolution leaves small sidelobes either side of the
    direct peak, and without this they are reported as surfaces a few
    centimetres away, which is both wrong and the kind of wrong that looks
    plausible in a list.

    Outdoors this list is usually short and that is correct. Open water in
    front and rock behind gives a handful of discrete echoes rather than the
    dense tail a room would, which is harder to make reverb from and much
    easier to measure distances with.
    """
    envelope = np.abs(np.asarray(ir, dtype=float).ravel())
    if envelope.size < 3:
        return []

    direct = int(np.argmax(envelope))
    loudest = envelope[direct]
    if loudest <= 0:
        return []

    threshold = loudest * (10.0 ** (floor_db / 20.0))
    skip = int(round((separation if blank is None else blank) * rate))
    start = direct + 1 + max(skip, 0)
    tail = envelope[start:]
    if tail.size < 3:
        return []
    offset = start - direct

    # Local maxima above the floor, strongest first, each one blocking its
    # neighbours so a single wide peak is not reported as several.
    rising = tail[1:-1] > tail[:-2]
    falling = tail[1:-1] >= tail[2:]
    loud = tail[1:-1] > threshold
    candidates = np.nonzero(rising & falling & loud)[0] + 1

    gap = max(int(round(separation * rate)), 1)
    taken: List[int] = []
    for index in candidates[np.argsort(tail[candidates])[::-1]]:
        if all(abs(int(index) - other) >= gap for other in taken):
            taken.append(int(index))
            if len(taken) >= limit:
                break

    return [Reflection(delay=(index + offset) / float(rate),
                       amplitude=float(tail[index] / loudest))
            for index in sorted(taken)]


# -- how sure the measurement is -----------------------------------------

@dataclass(frozen=True)
class Estimate:
    """One surface, as several measurements agree about it."""

    delay: float         #: mean, seconds after the direct arrival
    distance: float      #: metres, speaker and microphone together
    spread: float        #: metres, standard error of that distance
    seen: int            #: how many captures found it
    confidence: float    #: 0 to 1

    def __repr__(self) -> str:
        return (f"Estimate({self.distance:.2f} m ±{self.spread:.2f}, "
                f"seen {self.seen}, {self.confidence:.2f})")


class Survey:
    """The same place, measured repeatedly, and how much the repeats agree.

    Add the reflections from each capture. Reflections that land within
    ``tolerance`` of each other across captures are treated as the same
    surface, and the scatter of their delays becomes an uncertainty.

    Confidence rises for two separate reasons, which is what makes it behave
    like something learning rather than something averaging. A surface found in
    every capture beats one found in two, and the standard error of its
    distance shrinks with the square root of the number of captures even if the
    scatter itself does not improve. So more evidence always helps, and
    evidence that disagrees never pretends to.

    One capture gives a confidence of zero. Nothing has been corroborated yet,
    and saying otherwise would be a lie the music would then be built on.
    """

    def __init__(self, celsius: float = ROOM_C, resolution: float = 0.05,
                 tolerance: float = 0.001, rate: int = RATE):
        self.rate = int(rate)
        self.celsius = float(celsius)
        self.resolution = float(resolution)    #: metres you care about resolving
        self.tolerance = float(tolerance)      #: seconds within which two peaks are one surface
        self._captures = 0
        self._clusters: List[List[Reflection]] = []

    @property
    def captures(self) -> int:
        return self._captures

    def add(self, found: Sequence[Reflection]) -> "Survey":
        """Fold one capture in. Chainable."""
        self._captures += 1
        for reflection in found:
            match = self._nearest(reflection.delay)
            if match is None:
                self._clusters.append([reflection])
            else:
                match.append(reflection)
        return self

    def _nearest(self, delay: float) -> Optional[List[Reflection]]:
        best, closest = None, self.tolerance
        for cluster in self._clusters:
            mean = sum(r.delay for r in cluster) / len(cluster)
            distance = abs(mean - delay)
            if distance <= closest:
                best, closest = cluster, distance
        return best

    def estimates(self) -> List[Estimate]:
        """Every surface seen, nearest first."""
        speed = speed_of_sound(self.celsius)
        out = []
        for cluster in self._clusters:
            delays = np.array([r.delay for r in cluster], dtype=float)
            seen = len(delays)
            mean = float(delays.mean())
            if seen > 1:
                # Two captures agreeing exactly do not make a certainty, so the
                # scatter carries the Student factor for this many samples, and
                # cannot claim to beat the time between two samples of audio.
                scatter = max(float(delays.std(ddof=1)), 1.0 / self.rate)
                error = _STUDENT(seen) * scatter / math.sqrt(seen)
            else:
                error = math.inf
            spread = error * speed / 2.0
            agreement = math.exp(-spread / self.resolution) if seen > 1 else 0.0
            out.append(Estimate(
                delay=mean,
                distance=mean * speed / 2.0,
                spread=spread,
                seen=seen,
                confidence=(seen / self._captures) * agreement))
        return sorted(out, key=lambda e: e.delay)

    @property
    def confidence(self) -> float:
        """How much the captures agree about this place, 0 to 1.

        A surface that only ever turned up once counts against it, because a
        peak that will not reappear is usually wind rather than rock.
        """
        found = self.estimates()
        if not found:
            return 0.0
        return float(np.mean([e.confidence for e in found]))

    def publish(self, bus, name: str = "echo") -> "Survey":
        """Put the confidence and the distances on the bus.

        Two addresses, because the confidence drives a parameter on its own and
        the distances are read as a group the way the radar's pair is.
        """
        from .contract import sensor

        bus.send(sensor(f"{name}_confidence"), self.confidence)
        bus.send(sensor(name), *[e.distance for e in self.estimates()])
        return self

    def __repr__(self) -> str:
        return (f"Survey({self._captures} captures, {len(self._clusters)} "
                f"surfaces, confidence {self.confidence:.2f})")


# -- files ---------------------------------------------------------------

def write_wav(path: str, samples: Sequence[float], rate: int = RATE,
              headroom: float = 0.89) -> str:
    """Write mono 16-bit PCM, the format every player and recorder agrees on.

    ``headroom`` leaves about a decibel below full scale so the loudspeaker is
    not asked to reproduce a square wave at the peaks, which is the usual way a
    measurement ends up with distortion baked into it.
    """
    import wave

    data = np.asarray(samples, dtype=float).ravel()
    loudest = float(np.max(np.abs(data))) if data.size else 0.0
    if loudest > 0:
        data = data / loudest * headroom
    encoded = np.clip(data * 32767.0, -32768, 32767).astype("<i2")

    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(rate))
        handle.writeframes(encoded.tobytes())
    return path


def read_wav(path: str, channel: int = 0):
    """Read one channel of a WAV as floats from -1 to 1, with its sample rate.

    Handles the 24-bit files field recorders write by default, which NumPy has
    no native type for, as well as the usual 16 and 32-bit ones.
    """
    import wave

    with wave.open(path, "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())

    if width == 1:                                  # unsigned, offset binary
        flat = (np.frombuffer(raw, dtype=np.uint8).astype(float) - 128.0) / 128.0
    elif width == 2:
        flat = np.frombuffer(raw, dtype="<i2").astype(float) / 32768.0
    elif width == 3:                                # no NumPy type for this
        packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        widened = np.zeros((len(packed), 4), dtype=np.uint8)
        widened[:, 1:] = packed                     # sign lands in the top byte
        flat = widened.view("<i4").ravel().astype(float) / (1 << 31)
    elif width == 4:
        flat = np.frombuffer(raw, dtype="<i4").astype(float) / (1 << 31)
    else:
        raise ValueError(f"unsupported sample width of {width * 8} bits in {path}")

    if channels > 1:
        if not 0 <= channel < channels:
            raise ValueError(
                f"{path} has {channels} channels, so there is no channel {channel}")
        flat = flat.reshape(-1, channels)[:, channel]
    return flat, int(rate)
