#!/usr/bin/env python3
"""Arduino serial → OSC. Reads lines like `name value` or `name:value` (one sensor per line)
from the UNO R4 and forwards each as /sensor/<name> <float>.
pip install pyserial python-osc
python arduino_serial_to_osc.py COM5 [--baud 115200] [--host 127.0.0.1] [--port 9000]

Arduino side, e.g.:
    Serial.print("light "); Serial.println(analogRead(A3));
    Serial.print("temp ");  Serial.println(sht31.getTemperature());"""
import argparse, re, serial
from pythonosc.udp_client import SimpleUDPClient

p = argparse.ArgumentParser(); p.add_argument("serial")
p.add_argument("--baud", type=int, default=115200)
p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=9000)
a = p.parse_args()
osc = SimpleUDPClient(a.host, a.port)
pat = re.compile(r"^\s*([A-Za-z_][\w]*)\s*[:=\s]\s*(-?\d+(?:\.\d+)?)\s*$")
with serial.Serial(a.serial, a.baud, timeout=1) as s:
    while True:
        line = s.readline().decode(errors="ignore")
        m = pat.match(line)
        if m:
            osc.send_message(f"/sensor/{m.group(1)}", float(m.group(2)))
