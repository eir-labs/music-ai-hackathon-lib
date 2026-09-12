# Sensor Kit Setup

Grove sensors × Arduino UNO R4 Minima

This document is a reference for **the things that will trip you up**. Everything else is ordinary
Arduino development, so it covers only the toolchain, the libraries, the I2C addresses, the wiring
constraints and each sensor's quirks.

No sample code is included. Each library you install from Library Manager brings its own official
examples under **File > Examples** — that is the quickest place to start.

---

## 0. Check this first

**You cannot flash the UNO R4 from ARM-based Windows** (Snapdragon machines and similar) — no DFU driver exists for that architecture. If that's your machine, talk to the organizers. x64 Windows and macOS are both fine.

**You need administrator privileges.** (Reason in the next section.)

---

## 1. Toolchain

```
Arduino IDE 2.x
  → Boards Manager: "Arduino UNO R4 Boards"
  → Tools > Board:  "Arduino UNO R4 Minima"

arduino-cli:
  arduino-cli core install arduino:renesas_uno
  FQBN: arduino:renesas_uno:minima
```

### ⚠️ Approve the UAC prompt during board package installation

The UNO R4 switches its USB interface CDC → DFU → CDC during upload, so **a DFU driver is mandatory**. The board package's `post_install.bat` installs it automatically — but if you decline the "unknown publisher" warning, **it fails silently with no error message.**

Symptoms: "Unknown USB Device" in Device Manager, or `dfu-util: Cannot open DFU device` on upload.

Recovery: **Remove → Install** the board package in Boards Manager and approve every prompt this time. If that still fails, run `drivers\dpinst-amd64.exe` from the board package directory as Administrator.

### The sensors need no drivers at all

Grove sensors talk I2C or analog to the microcontroller, not to your PC. The OS never sees them. **There is nothing to install.**

---

## 2. Libraries

From Library Manager:

| Library | For |
|---|---|
| `Grove SHT31 Temp Humi Sensor` | temperature / humidity |
| `Arduino_LSM6DS3` | 6-axis IMU |
| `Adafruit AMG88xx Library` | thermal array |

Manual ZIP install:

| Repository | For |
|---|---|
| https://github.com/Seeed-Studio/Seeed_MRP121 | capacitive touch |

### ⚠️ Three traps here

**The temperature sensor is the SHT31.** Searching brings up `Grove - I2C High Accuracy Temp_Humi Sensor SHT35` first — that is **a different sensor**.

**Use Arduino's official IMU library, not Seeed's.** `Seeed Arduino LSM6DS3` **does not compile on the UNO R4**. It compiles its SPI code unconditionally even when you're on I2C, and `SPI.setBitOrder()` does not exist on the Renesas core's `ArduinoSPI` class.

```
error: 'class arduino::ArduinoSPI' has no member named 'setBitOrder'
```

Arduino's `Arduino_LSM6DS3` uses I2C only and works on the R4 (`LSM6DS3_ADDRESS` = `0x6A`, and it defines `IMU` as `IMU_LSM6DS3`).

**The MPR121 repository is named `MRP121`.** That's Seeed's typo — searching for `MPR121` will not find it. It is also absent from Library Manager, so manual ZIP install is the only option.

---

## 3. Hardware

### Set the Base Shield voltage switch to 5V

That switch changes **only the Vcc (red wire) on the Grove connectors**. **There is no level shifter on the board** — the signal lines run straight to the Arduino pins. The UNO R4 is a 5V-logic board (IOREF = 5V), so 5V is correct. Setting it to 3.3V leaves you with modules powered at 3.3V receiving 5V signals, which is a real risk to the hardware.

---

## Sensor combination rules

Sensors split into two families. **I2C devices share one bus, so you can use all of them at once. Analog sensors each need their own dedicated pin.** Everything else follows from that.

### ① All the I2C sensors can be used simultaneously

**Temperature / touch / IMU / thermal / heart rate** — five modules. Plug them into any socket marked `I2C`, as many as you like.

> **How it works**: I2C is a bus — two wires (SDA / SCL) shared by every device, each with its own address (`0x44`, `0x6A`, and so on) that the Arduino calls by name. The Base Shield's four I2C sockets are **physically the same two wires**, so it makes no difference which one you use.

There are only four sockets, so to use all five modules, plug the **I2C Hub** into one socket — it branches into five. The Hub is a plain parallel splitter with no IC, so there is nothing to configure and no power to supply.

### ② You can only use three analog sensors

Of **joystick / force / loudness / light**, only three can be connected at once.

> **How it works**: analog sensors output a voltage and have no address, so they cannot share a line — **each one needs its own pin**. The UNO R4 has A0–A5, but **A4 and A5 are taken by I2C (SDA / SCL)**, leaving A0–A3 — four pins. And **the joystick outputs separate voltages for X and Y, consuming two of them.** 4 − 2 = 2 pins left for three single-channel sensors, so one of them is always left over.

Recommended layout:

```
socket A0 → joystick        (uses A0 = X and A1 = Y)
socket A2 → force sensor
socket A3 → light sensor
```

**Socket A1 is unusable.** A Grove socket carries two signal lines and overlaps with its neighbour (socket A0 = A0+A1, socket A1 = A1+A2, and so on). That overlap is what lets the joystick fit into a single socket — the cost is that it kills the socket next to it.

If you don't need the joystick, you can put the force, loudness and light sensors in A0 / A1 / A2.

### ③ The heart rate sensor and the I2C ADC are mutually exclusive

Both answer at I2C address `0x50`, so the Arduino cannot tell them apart. Use one or the other.

> **What the I2C ADC is**: a bridge that reads an analog voltage and returns it over I2C. It lets you add the leftover loudness sensor without consuming an analog pin — at the cost of giving up the heart rate sensor.
>
> ```
> loudness sensor ──(analog)──> I2C ADC ──(I2C)──> Arduino
> ```

---

## Practical limit

**You cannot use all ten sensors at once. Eight is the normal maximum, nine at a stretch.**

| If you want | Configuration | Count |
|---|---|---|
| the heart rate sensor | 5 × I2C + 3 × analog (no loudness) | 8 |
| the loudness sensor | 4 × I2C + I2C ADC + 3 × analog (no heart rate) | 8 |
| maximum count | either of the above, plus the remainder | 9 |

Once you know what you're building, connect only the sensors you need. There is no reason to plug in everything.

---

## I2C address reference

| addr | Device | Notes |
|---|---|---|
| `0x44` | SHT31 temperature / humidity | `0x45` also selectable |
| `0x50` | **heart rate OR I2C ADC v1.2** | **★ conflict — cannot coexist** |
| `0x55` | I2C ADC v1.0 / v1.1 | depends on board revision |
| `0x5B` | MPR121 touch | if you use the Adafruit library, its default is `0x5A` — pass `begin(0x5B)` explicitly |
| `0x68` | AMG8833 thermal | Adafruit's own breakout defaults to `0x69`; the Grove board is `0x68` |
| `0x6A` | LSM6DS3 IMU | `0x6B` also selectable |

Seeed's heart rate sensor documentation uses the 8-bit notation `0xA0`. What you pass to `Wire` is `0xA0 >> 1` = `0x50`.

---

## 4. UNO R4 vs UNO R3

| | UNO R3 | UNO R4 Minima |
|---|---|---|
| MCU | ATmega328P @ 16MHz | Renesas RA4M1 (Cortex-M4) @ 48MHz |
| Logic level | 5V | 5V (same) |
| SRAM / Flash | 2K / 32K | 32K / 256K |
| `analogRead` default | 10-bit | 10-bit (kept for compatibility) |
| ADC maximum | 10-bit | **14-bit** via `analogReadResolution(14)` |
| `analogReference()` | `INTERNAL` (1.1V), etc. | **`AR_DEFAULT` / `AR_INTERNAL_1_5V` / `AR_INTERNAL_2_0V` / `AR_INTERNAL_2_5V` / `AR_EXTERNAL`** |
| I2C | A4 / A5 | A4 / A5 (= D18 / D19). **Pull-ups are not populated** on the PCB (the core enables the MCU's weak internal ones). 100 kHz default |
| Pin 13 | INPUT after reset | **OUTPUT after reset** |
| GPIO current | ~20 mA | **8 mA** |
| `Serial` / `Serial1` | same UART | **fully independent** (Serial = USB CDC, Serial1 = D0 / D1) |
| A0 | — | **shared with DAC0** |

### Compile failures you should expect

Relevant if you bring in older AVR-targeted libraries.

| Cause | Error |
|---|---|
| including `avr/io.h` and friends directly | `fatal error: avr/io.h: No such file` |
| direct port manipulation (`PORTB` / `PINB`) | `'PORTB' was not declared in this scope` |
| AVR timer registers (TimerOne, MsTimer2) | `'TCCR1A' was not declared` |
| a missing branch in `#if defined(__AVR__)` dispatch | `#error no timer functions implemented for this board` |
| `SoftwareSerial::listen()` | `has no member named 'listen'` — the R4 core's bundled SoftwareSerial lacks it |
| `SPI.setBitOrder()` / `setClockDivider()` | `'class arduino::ArduinoSPI' has no member named ...` |

`avr/pgmspace.h`, `PROGMEM` and `dtostrf()` are fine — the Renesas core ships compatibility shims for them.

**Bit-banged libraries (1-Wire, DHT, NeoPixel-style) compile cleanly but return garbage**, because their timing loops assume 16 MHz and the R4 runs at 48 MHz.

Other notes:

- `while (!Serial) {}` after `Serial.begin()` **does block correctly** on the Minima. (It does not on the R4 WiFi — don't generalize between the two.)
- USB is handled by the main MCU, so **a crashing sketch takes the COM port down with it.** Double-tap RESET to enter DFU mode and recover.
- Uploading re-enumerates USB, so you may need to close and reopen the Serial Monitor.
- The 5V rail has been measured as low as ~4.6V. If you convert ADC counts to absolute volts, measure your actual rail. Ratiometric readings cancel this out.

---

## 5. Sensor characteristics

| Sensor | Output | Notes |
|---|---|---|
| SHT31 temp / humidity | °C / % | — |
| LSM6DS3 IMU | acceleration in G / angular rate in dps | at rest, gravity puts one axis at 1.0 — that's your tilt reference |
| MPR121 touch | electrodes 0–11 as a bitmask | sensitivity is environment-dependent; tuning `set_sensitivity()` is effectively mandatory |
| **heart rate** | bpm | **★ takes about a minute to produce a valid reading.** An initial 0 is not a fault. Requires firm skin contact and no movement. Cold hands degrade accuracy |
| AMG8833 thermal | °C × 64 pixels | 0–80°C, ±2.5°C, 60° field of view, 10 fps. The library issues 128 I2C transactions per frame, so it is slow |
| FSR402 force | 0 – **~650** | **never reaches 1023.** Non-linear; Seeed themselves state it is unsuitable for precise measurement. Use it for threshold detection |
| loudness | 0–1023 | **an envelope, not dB.** An onboard trimmer changes the gain, so absolute values are meaningless. **Below 3.5V is out of spec** — 5V required |
| joystick | ~200–800 | centre is not 512 but X≈516 / Y≈507. **The button is multiplexed onto the X axis** — pressing it pins X to 1023, and you cannot read the X position while it's held. 5V required |
| light LS06-S | ~45–800 | **not lux.** dark ≈45 / indoors ≈600 / bright ≈754. Peak sensitivity 540 nm (green), 20–30 ms response |
| I2C ADC | 0–4095 | 3.00V reference. The `×2` in Seeed's voltage conversion assumes an input divider that Seeed never documents — calibrate against a known voltage before trusting absolute volts |

---

## 6. When you get no readings

1. Is the Base Shield switch on 5V?
2. **Is each Grove cable fully seated at both ends?** — this is the most common failure. A half-inserted cable can bridge to an adjacent pin and pull SDA to ground, which makes an I2C scan "find" all 112 addresses.
3. Is the I2C module in a socket marked `I2C`?
4. Is the Base Shield's green PWR LED lit?
5. For the heart rate sensor — did you wait a full minute?

If none of that helps, ask the organizers.

---

## Appendix: XE125 mmWave radar (some teams only)

**Do not connect it to the Arduino.** It is not a Grove module — it plugs into your PC directly over USB-C and runs on Acconeer's own Python tooling. See the separate `XE125_Setup_Windows.md` / `XE125_Setup_macOS.md`.

https://docs.acconeer.com/en/latest/getting_started/evk_setup/xm125.html
