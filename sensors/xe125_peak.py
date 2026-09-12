#!/usr/bin/env python3
"""Print the strongest radar reflection distance from an Acconeer XE125.
pip install acconeer-exptool   (no [app] extra needed)
Close the Exploration Tool first — only one process can hold the port."""
import sys, numpy as np
from acconeer.exptool import a121
from serial.tools import list_ports

port = sys.argv[1] if len(sys.argv) > 1 else next(
    (p.device for p in list_ports.comports() if "Enhanced" in p.description or "CP2105" in p.description), None)
if not port:
    sys.exit("no XE125 port found — pass it explicitly, e.g. COM3 or /dev/tty.usbserial-xxx")
client = a121.Client.open(serial_port=port)
client.setup_session(a121.SessionConfig({1: a121.SensorConfig()}))
client.start_session()
try:
    while True:
        frame = client.get_next().frame          # complex (1, 160), 2.5 mm per point
        peak = int(np.argmax(np.abs(frame)))
        print(f"\r≈ {peak * 0.25:5.1f} cm", end="", flush=True)
except KeyboardInterrupt:
    pass
finally:
    client.stop_session(); client.close()
