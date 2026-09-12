#!/usr/bin/env python3
"""Arduino serial -> OSC. Reads lines like `name value` or `name:value`
(one sensor per line) from the UNO and forwards each as /sensor/<name> <float>.

    python arduino_serial_to_osc.py COM5 [--baud 115200] [--host 127.0.0.1] [--port 9000]

Arduino side, e.g.:
    Serial.print("light "); Serial.println(analogRead(A3));
    Serial.print("temp ");  Serial.println(sht31.getTemperature());

This is a wrapper kept so the documented command still works. The same thing,
plus per-sensor scaling, is `kitlib arduino`. See kitlib/sources/arduino.py.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from kitlib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["arduino", *sys.argv[1:]]))
