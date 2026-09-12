"""Arduino serial lines onto the bus.

The sketch prints one reading per line, name then value::

    Serial.print("light "); Serial.println(analogRead(A3));
    Serial.print("temp ");  Serial.println(sht31.getTemperature());

and each becomes ``/sensor/light``, ``/sensor/temp``. Separator can be a space,
a colon or an equals sign, so most existing sketches already fit.

Needs ``pip install kitlib[arduino]``.
"""
from __future__ import annotations

import re
from typing import Dict, Iterator, Optional, Tuple

from ..bus import Bus
from ..contract import sensor
from ..signal import Stage

#: One reading per line. Anything else on the wire is ignored, so a sketch can
#: still print banners and debug text without corrupting the stream.
LINE = re.compile(r"^\s*([A-Za-z_][\w]*)\s*[:=\s]\s*(-?\d+(?:\.\d+)?)\s*$")


def parse(line: str) -> Optional[Tuple[str, float]]:
    """``"light 512"`` -> ``("light", 512.0)``. ``None`` if the line is not one."""
    match = LINE.match(line)
    return (match.group(1), float(match.group(2))) if match else None


def readings(port: str, baud: int = 115200,
             timeout: float = 1.0) -> Iterator[Tuple[str, float]]:
    """Yield ``(name, value)`` forever. Closes the port on exit."""
    import serial  # optional extra; imported late so a Pd team need not have it

    with serial.Serial(port, baud, timeout=timeout) as handle:
        while True:
            reading = parse(handle.readline().decode(errors="ignore"))
            if reading is not None:
                yield reading


def run(port: str, baud: int = 115200, bus: Optional[Bus] = None,
        stages: Optional[Dict[str, Stage]] = None, verbose: bool = False) -> None:
    """Pump the serial port onto the bus until interrupted.

    ``stages`` conditions individual sensors by name, so the force sensor can
    be scaled to its real 0..650 range while the temperature passes untouched::

        run("COM5", stages={"force": signal.FSR402, "light": signal.LIGHT_LS06S})

    A stage returning ``None`` drops that sample and sends nothing.
    """
    bus = bus or Bus()
    stages = stages or {}
    try:
        for name, raw in readings(port, baud):
            value = raw
            stage = stages.get(name)
            if stage is not None:
                value = stage(raw)
                if value is None:
                    continue
            bus.send(sensor(name), value)
            if verbose:
                print(f"{sensor(name)} {value:g}")
    except KeyboardInterrupt:
        pass
