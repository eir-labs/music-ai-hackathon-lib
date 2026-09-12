# XE125 Radar — Setup Guide (Windows)

Acconeer XE125 evaluation board (A121 sensor / XM125 module)

> **This board is not a Grove module.** Do not connect it to the Arduino. It plugs into your PC directly over USB-C and is driven by Acconeer's own software.

**You need to flash the firmware yourself** before the board will talk to anything. That is Step 4.

---

## What you need

| | |
|---|---|
| OS | Windows 10 or 11 (x64) |
| Python | 3.9 or newer |
| Cable | USB-C, **data-capable** (charge-only cables will not work) |
| Privileges | Administrator (for the driver install) |
| Account | A free **Acconeer developer account** — https://developer.acconeer.com/ — needed to download the firmware. **Create it before the event**; waiting on a confirmation email on the day will cost you time |

---

## Step 1 — Install the CP210x USB driver

The XE125 uses a Silicon Labs **CP2105** dual USB-to-UART bridge. Windows does not always apply the driver automatically, so specify it manually.

1. Download the **CP210x Universal Windows Driver** ZIP from the Acconeer developer site (Exploration Tool page) or from Silicon Labs, and extract it anywhere.
2. Open **Device Manager**.
3. Find `Enhanced Com Port` (it may appear under *Other devices* with a warning icon). Right-click it → **Update driver**.
4. Choose **Browse my computer for drivers**.
5. Point it at the extracted folder (e.g. `CP210x_Universal_Windows_Driver`) and confirm.
6. Repeat for `Standard Com Port`.

---

## Step 2 — Verify the ports

In Device Manager, under **Ports (COM & LPT)**, you should now see two entries:

```
Silicon Labs Dual CP2105 USB to UART Bridge: Enhanced Com Port (COM3)
Silicon Labs Dual CP2105 USB to UART Bridge: Standard Com Port  (COM4)
```

**Note the COM number of the Enhanced port.** That is the one you will flash and connect to. The COM numbers on your machine will differ from the example above.

---

## Step 3 — Install the Exploration Tool

```
py -3 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install "acconeer-exptool[app]"
```

---

## Step 4 — Flash the firmware

The XE125 ships without the **Exploration Server** firmware, so it cannot communicate until you flash it. This is a one-time operation per board.

1. Connect the XE125 over USB-C.
2. Launch the Exploration Tool:
   ```
   python -m acconeer.exptool.app
   ```
3. Press the **Flash** button.
4. Follow the guided process. The tool downloads the latest binary from developer.acconeer.com — **this is where your account login is needed**. You can also point it at a `.bin` you downloaded earlier.

**Already flashed?** If the board connects in Step 5 without complaint, the firmware is present and you can skip this step.

---

## Step 5 — Connect

```
python -m acconeer.exptool.app
```

1. Select **A121** (not A111 — the XE125 carries an A121 sensor).
2. Set the connection type to **Serial**.
3. Choose the **Enhanced Com Port** COM number from Step 2.
4. Click **Connect**.

You should now be able to start a session and see live radar data.

---

## Step 6 (optional) — Read data from Python without the GUI

If you only need numbers, skip the GUI entirely. Install without the `[app]` extra to avoid the Qt dependencies:

```
python -m pip install acconeer-exptool
```

```python
from acconeer.exptool import a121

client = a121.Client.open(serial_port="COM3")   # your Enhanced port

config = a121.SessionConfig({1: a121.SensorConfig()})
metadata = client.setup_session(config)
client.start_session()

for _ in range(10):
    result = client.get_next()
    frame = result.frame              # complex ndarray, shape (1, 160)
    print(abs(frame).max())

client.stop_session()
client.close()
```

**Close the Exploration Tool before running this.** Only one process can hold the serial port.

A ready-made test script, `xe125_test.py`, is included with the kit. It enumerates the serial ports, picks the most likely candidate, connects, and prints a few frames.

---

## Understanding the data

The default configuration returns **Sparse IQ** data.

| Field | Value | Meaning |
|---|---|---|
| `frame.shape` | `(1, 160)` | 1 sweep × 160 distance points |
| `base_step_length_m` | `0.0025` | **2.5 mm** between points |
| Range | 160 × 2.5 mm | **≈ 40 cm** |
| `max_sweep_rate` | `650` | up to 650 Hz |

Each point is a complex number (IQ). **The magnitude is the reflected signal strength.** A large magnitude at a given index means something is reflecting at that distance.

```python
import numpy as np
amp  = np.abs(frame)
peak = int(np.argmax(amp))
print(f"strongest reflection at ≈{peak * 0.0025 * 100:.1f} cm")
```

Move your hand in front of the sensor and watch the peak index change — that is your distance reading.

`SensorConfig` lets you change the start distance, number of points, profile, sweep rate and more. See the API reference:
https://docs.acconeer.com/en/latest/exploration_tool/api/a121.html

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| No COM ports appear at all | Charge-only USB-C cable. Swap it for a data-capable one. |
| Device shows as `Unknown` or `Enhanced Com Port` with a warning icon | Driver not applied. Redo Step 1, pointing at the extracted driver folder. |
| Connects but no data | Confirm you selected **A121**, not A111. |
| Nothing responds even though the port is correct | Firmware not flashed. Go back to Step 4. |
| Flash fails to download the binary | Acconeer developer account not logged in, or the network is blocking it. Download the `.bin` on another connection and select it manually. |
| `Could not open port` / access denied | Another process holds the port. Close the Exploration Tool, Arduino IDE Serial Monitor, or any other terminal program. |
| Connected to the wrong port | Use the **Enhanced** COM port, not Standard. |

---

## References

- [Exploration Tool — Acconeer Developer](https://developer.acconeer.com/home/exploration-tool/)
- [XM125 / XE125 setup — Acconeer docs](https://docs.acconeer.com/en/latest/getting_started/evk_setup/xm125.html)
- [A121 Python API reference](https://docs.acconeer.com/en/latest/exploration_tool/api/a121.html)
- [acconeer-python-exploration on GitHub](https://github.com/acconeer/acconeer-python-exploration)
