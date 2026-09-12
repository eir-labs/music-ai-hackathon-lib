"""Acconeer XE125 mmWave radar onto the bus.

The board returns Sparse IQ: one sweep of 160 complex points, 2.5 mm apart, so
about 40 cm of range. The magnitude at each point is how hard something there
reflects, and the strongest one is your distance reading.

Publishes ``/sensor/radar <cm> <magnitude>``.

The board is not a Grove module and must not go near the Arduino. It plugs into
the PC over USB-C and needs its firmware flashed once; see
``sensors/XE125_Setup_Windows.md``. Needs ``pip install kitlib[radar]``.
"""
from __future__ import annotations

from typing import Iterator, Optional, Tuple

from ..bus import Bus
from ..signal import Stage

#: 160 points at Acconeer's 2.5 mm base step length.
STEP_CM = 0.25
POINTS = 160
RANGE_CM = POINTS * STEP_CM

ADDRESS = "/sensor/radar"

#: The XE125 carries a Silicon Labs CP2105, which presents two serial ports.
#: Only the Enhanced one talks to the radar.
_PORT_HINTS = ("Enhanced", "CP2105")


def find_port() -> Optional[str]:
    """Guess the Enhanced COM port, or ``None`` if nothing looks right."""
    from serial.tools import list_ports

    for candidate in list_ports.comports():
        if any(hint in (candidate.description or "") for hint in _PORT_HINTS):
            return candidate.device
    return None


def readings(port: Optional[str] = None) -> Iterator[Tuple[float, float]]:
    """Yield ``(distance_cm, magnitude)`` at the sweep rate, up to 650 Hz.

    Close the Exploration Tool first. Only one process can hold the port.
    """
    import numpy as np
    from acconeer.exptool import a121

    port = port or find_port()
    if not port:
        raise RuntimeError(
            "No XE125 found. Pass the Enhanced COM port explicitly, e.g. COM3 "
            "or /dev/tty.usbserial-xxx. If Device Manager shows a warning icon, "
            "the CP210x driver is not applied; see sensors/XE125_Setup_Windows.md.")

    client = a121.Client.open(serial_port=port)
    client.setup_session(a121.SessionConfig({1: a121.SensorConfig()}))
    client.start_session()
    try:
        while True:
            amplitude = np.abs(client.get_next().frame[0])
            peak = int(np.argmax(amplitude))
            yield peak * STEP_CM, float(amplitude[peak])
    finally:
        client.stop_session()
        client.close()


def run(port: Optional[str] = None, bus: Optional[Bus] = None,
        stage: Optional[Stage] = None, address: str = ADDRESS,
        verbose: bool = False) -> None:
    """Pump the radar onto the bus until interrupted.

    ``stage`` conditions the distance only; the magnitude is always passed
    through raw, because it is how you tell a real reflection from noise::

        run(stage=signal.RADAR_CM >> signal.Median(5) >> signal.RateLimit(60))
    """
    bus = bus or Bus()
    try:
        for centimetres, magnitude in readings(port):
            value = centimetres
            if stage is not None:
                value = stage(centimetres)
                if value is None:
                    continue
            bus.send(address, value, magnitude)
            if verbose:
                print(f"{address} {value:g} {magnitude:g}")
    except KeyboardInterrupt:
        pass
