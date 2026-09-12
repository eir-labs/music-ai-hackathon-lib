# The iPhone as the sensor kit

Replacing the Grove kit with a phone, feeding the same addresses onto the same
bus, so everything downstream keeps working without being told.

What you lose in sensor variety you gain in setup: no I2C address conflicts, no
socket overlap, no 5V/3.3V switch, no DFU driver, no board package, and no
ceiling of nine sensors. The whole of `Sensor_Kit_Setup.md` stops applying.

## The one rule that makes this drop in

Send to the same addresses, already normalised to 0 and 1.

```
/sensor/<name> <float>        name matching the Grove sensor it replaces
```

The Grove presets in `kitlib/signal.py` exist to turn raw ADC counts into 0 to
1, because the force sensor tops out near 650 rather than 1023 and the light
sensor reads 45 in the dark rather than 0. A phone has no such quirks, so
normalise on the phone and skip the presets entirely.

Do that and a Wwise parameter mapping, a Pd patch or a ChordCat progression
built against the Grove kit works against the phone with nothing changed. The
bus cannot tell the difference, which is the whole point.

**One value per address for anything that will drive a parameter.** The Wwise
bridge's `--map` and the MIDI sink's chord mapping both take the first argument
and ignore the rest, so a message carrying x and y together silently drops the
y. That is also how the Arduino path behaves: its sketches print one name and
one value per line, so a Grove joystick already arrives as two addresses. Send
multiple values together only when they are consumed as a group, the way the
radar sends distance and magnitude.

Names stay bare identifiers so they survive into Pd receive names and
SuperCollider symbols unchanged. Run `kitlib monitor` to confirm what is
actually arriving.

## Translation

| Grove part | On the phone | Address | Notes |
|---|---|---|---|
| 6-Axis Accelerometer & Gyroscope | Core Motion device motion | `/sensor/roll`, `/sensor/pitch`, `/sensor/yaw`, `/sensor/accel_x` and so on | Better than the original. You get fused roll, pitch and yaw, plus gravity separated from user acceleration, at 100 Hz |
| Loudness Sensor | Microphone, RMS off an audio tap | `/sensor/loudness` | Better. The Grove part is an envelope with a trimmer; this is real audio you can also band-split |
| Thumb Joystick | Device tilt, or an on-screen pad | `/sensor/tilt_x`, `/sensor/tilt_y` | One address each, as the Grove joystick already arrives. Tilt is the more expressive of the two and needs no thumb on glass |
| MPR121 12-key touch | Multi-touch | `/sensor/touch` | Position and count are straightforward. Per-key capacitance is not; model it as regions on screen |
| Finger-clip Heart Rate | Camera with the torch on, red channel | `/sensor/heart` | Works, and is the standard phone technique. An Apple Watch through HealthKit is steadier if anyone has one |
| XE125 mmWave radar | Lidar depth, on Pro models only | `/sensor/depth` | Reaches metres rather than the radar's 40 cm, and returns a depth map rather than one peak, so it is strictly more useful for shape. Non-Pro phones have no depth sensor |
| Light Sensor LS06-S | No public API | `/sensor/light` | See below |
| Round Force Sensor FSR402 | No force on current phones | `/sensor/force` | See below |
| SHT31 Temperature & Humidity | Nothing | — | See below |
| AMG8833 thermal array | Nothing | — | See below |
| Base Shield, I2C hub, ADC, cables | Not needed | — | This is the part you are buying back |

## What the phone adds that the kit never had

| Source | Address | Why it matters here |
|---|---|---|
| Barometric altimeter | `/sensor/altitude` | Relative altitude to roughly 10 cm. At a mountain hotel this is a real instrument, not a novelty |
| GPS | `/sensor/location` | Position and speed, for anything that moves outdoors |
| Magnetometer | `/sensor/heading` | Compass bearing, which pairs with the altimeter for orientation on a slope |
| Face and body tracking | `/ch5/pose/...` | The Ch5 track's whole subject, already on the device |

Altitude is the one worth taking seriously. Nothing in the Grove kit senses
anything about where you are standing, and you are standing somewhere unusual.

## The four things a phone genuinely cannot do

Stated plainly so nobody spends an afternoon looking for an API that is not
there.

- **Ambient light.** iOS exposes no public ambient light sensor. The usual
  workaround is to read the front camera's exposure metering and treat it as a
  brightness proxy, which is monotonic with light level but not calibrated and
  not lux.
- **Force.** Current iPhones dropped force-sensitive touch. Long press is
  timing, not pressure. If pressure matters to your idea, the FSR402 on an
  Arduino is the honest answer and can sit alongside the phone on the same bus.
- **Temperature and humidity.** No sensor and no API. A weather lookup by
  location is the substitute, and it describes the valley rather than the room.
- **Thermal imaging.** No equivalent to the AMG8833. Clip-on thermal cameras
  exist as accessories, but nothing is built in.

The first two are the ones most likely to matter. Both can be covered by
keeping one Arduino with just those two sensors on it, which also sidesteps
every I2C conflict in the setup document, since two sensors cannot collide.

## Getting OSC off the phone

Three routes, cheapest first.

**An existing app.** Motion-streaming OSC apps already exist and will have you
on the bus in minutes with no code. Point one at your laptop's address on port
9000 and rename its addresses to match the table above. Good enough to prove
the idea before lunch, and limited to whatever sensors that app exposes.

**A small app of your own.** Core Motion plus a UDP socket. OSC 1.0 framing is
simple enough to write by hand if you do not want a dependency:

```
address string, null-terminated, padded with nulls to a multiple of 4
"," then one type tag per argument, same padding      f = float32, i = int32, s = string
each argument, big-endian
```

That is the whole format for what you need. A float message is under 32 bytes.
Send at 30 to 60 Hz per sensor and rate-limit anything faster at the source,
the same way the radar is rate-limited.

**Python on the phone.** The bus, the contract and the signal stages in
`kitlib` are pure Python with one pure-Python dependency, so a Python
environment on iOS can import them directly and you inherit the conditioning
stages rather than reimplementing them.

## Worked example

Tilt driving a Wwise parameter, phone to laptop, nothing else running:

```
on the phone     /sensor/tilt_x 0.42             already 0..1
                 /sensor/tilt_y 0.61
on the laptop    kitlib monitor                  confirm it is arriving
                 kitlib wwise --map /sensor/tilt_x=Tilt --map /sensor/tilt_y=Lean
```

Two addresses, two parameters, exactly the shape the Grove joystick would have
arrived in.

Tilt playing chords instead, no Wwise involved:

```
kitlib play --map /sensor/tilt_x=C,Am,F,G
```

## If you keep one Arduino

Force and ambient light are the two gaps worth closing with hardware. One
Arduino carrying only the FSR402 and the LS06-S publishes alongside the phone
with no conflict, because both are analog and the I2C address table never comes
into it.

```
kitlib arduino /dev/tty.usbmodem1101 --scale force=fsr402 --scale light=light
```

The phone sends normalised values and this sends raw counts through the presets
that normalise them. Downstream, both are floats from 0 to 1 on
`/sensor/<name>`, and nothing needs to know which is which.
