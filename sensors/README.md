# Ch3 sensor kit — Grove × Arduino UNO R4 Minima, Acconeer XE125

- `Sensor_Kit_Setup.md` — **read first.** Toolchain traps, which sensors coexist, I2C addresses, per-sensor quirks.
- `iPhone_Sensor_Spec.md` — the same signal feeds off a phone instead, part by part, including the four things a phone cannot do. Nothing downstream has to know.
- `XE125_Setup_Windows.md` — radar driver → flash → connect.
- `Echo_Measurement.md` — measure a space with a sweep and a recorder, and get a confidence that rises as repeats agree. Reaches hundreds of metres, where the radar reaches 40 cm.
- `xe125_peak.py` — prints distance to the strongest reflector. Smoke test.
- `kitlib radar` — radar → `/sensor/radar <cm> <mag>` over OSC. Add `--normalise --smooth 0.15 --rate 60` to get a control signal rather than a firehose.
- `kitlib arduino COM5` — `name value` lines from the UNO → `/sensor/<name>` over OSC. `--scale force=fsr402` applies the real range from the setup doc.

`xe125_to_osc.py` and `arduino_serial_to_osc.py` still work and do the same thing.

Chain: sensor → OSC :9000 → `kitlib wwise` (or Pd, SC `OSCdef`, anything). `kitlib monitor` shows you what is actually on the bus.

In Pure Data use `[netreceive -u -b 9001]` → `[oscparse]` → `[list trim]`, both objects vanilla, and point `kitlib forward --to 127.0.0.1:9001` at it. Pd cannot bind 9000 itself because the bus already holds it. The mrpeach `[udpreceive]` route works too but needs that external plus `[unpackOSC]` after it.
