# Ch3 sensor kit — Grove × Arduino UNO R4 Minima, Acconeer XE125

- `Sensor_Kit_Setup.md` — **read first.** Toolchain traps, which sensors coexist, I2C addresses, per-sensor quirks.
- `XE125_Setup_Windows.md` — radar driver → flash → connect.
- `xe125_peak.py` — prints distance to the strongest reflector. Smoke test.
- `kitlib radar` — radar → `/sensor/radar <cm> <mag>` over OSC. Add `--normalise --smooth 0.15 --rate 60` to get a control signal rather than a firehose.
- `kitlib arduino COM5` — `name value` lines from the UNO → `/sensor/<name>` over OSC. `--scale force=fsr402` applies the real range from the setup doc.

`xe125_to_osc.py` and `arduino_serial_to_osc.py` still work and do the same thing.

Chain: sensor → OSC :9000 → `kitlib wwise` (or Pd `[udpreceive]`, SC `OSCdef`, anything). `kitlib monitor` shows you what is actually on the bus.
