#!/usr/bin/env python3
"""XE125 radar → OSC. Sends /sensor/radar <distance_cm> <magnitude> at the sweep rate.
pip install acconeer-exptool python-osc
python xe125_to_osc.py [PORT] [--host 127.0.0.1] [--port 9000]
Pairs with wwise/osc2wwise.py --map /sensor/radar=Proximity"""
import argparse, numpy as np
from acconeer.exptool import a121
from pythonosc.udp_client import SimpleUDPClient
from serial.tools import list_ports

p = argparse.ArgumentParser(); p.add_argument("serial", nargs="?")
p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=9000)
a = p.parse_args()
port = a.serial or next((x.device for x in list_ports.comports() if "Enhanced" in x.description or "CP2105" in x.description), None)
osc = SimpleUDPClient(a.host, a.port)
client = a121.Client.open(serial_port=port)
client.setup_session(a121.SessionConfig({1: a121.SensorConfig()}))
client.start_session()
try:
    while True:
        amp = np.abs(client.get_next().frame[0])
        i = int(np.argmax(amp))
        osc.send_message("/sensor/radar", [i * 0.25, float(amp[i])])
except KeyboardInterrupt:
    pass
finally:
    client.stop_session(); client.close()
