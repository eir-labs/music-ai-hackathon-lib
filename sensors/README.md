# Ch3 sensor kit — Grove × Arduino UNO R4 Minima, Acconeer XE125

- `Sensor_Kit_Setup.md` — **read first.** Toolchain traps, which sensors coexist, I2C addresses, per-sensor quirks.
- `XE125_Setup_Windows.md` — radar driver → flash → connect.
- `xe125_peak.py` — prints distance to the strongest reflector. Smoke test.
- `xe125_to_osc.py` — radar → `/sensor/radar <cm> <mag>` over OSC.
- `arduino_serial_to_osc.py` — `name value` lines from the UNO → `/sensor/<name>` over OSC.

Chain: sensor → OSC :9000 → `../wwise/osc2wwise.py` (or Pd `[udpreceive]`, SC `OSCdef`, anything).
