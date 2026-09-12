# Music & AI Hackathon 2026 — toolkit

Berghotel Rudolfshütte · Sep 11–13, 2026. One repo with the setup docs, glue scripts and pointers for every challenge track.
The living version is the wiki — https://wiki.eir.sh/hackathon — where team pages accrete from Discord and coding agents. This repo is the offline-friendly, cloneable subset.

```
git submodule update --init --recursive    # fills bumochi/, needed once per clone
pip install -r requirements.txt
```

Travelling light, or on a Raspberry Pi? `pip install -e ".[radar]"` takes only
what your track needs. The extras are `arduino`, `radar`, `wwise`, `all`.

| Track | Folder | Start with |
|---|---|---|
| Ch1 Sound & Nature (Austria Tourism) | `recorders/` | the recorders at the kit table |
| Ch2 AI Instruments (Roland & Neutone) | `lydia/` | `README.md` → Roland's DIY doc |
| Ch3 Sound & Driving (Alps Alpine) | `sensors/` | `Sensor_Kit_Setup.md` **before plugging anything in** |
| Ch4 Game Sound (Audiokinetic) | `wwise/` | `kitlib wwise` |
| Ch5 Moving Bodies (academic) | `bumochi/` | `README.md` → the vendored BuMoChi submodule |
| Ch6 Accessibility (AlphaTheta) | `chordcat/` | `kitlib chord Cmaj7`, then `README.md` |

`Challenges.pdf` — the official briefs.

## Glue

Everything here talks OSC on UDP 9000 so tracks can borrow from each other:

```
Arduino  ──serial──▶ kitlib arduino ──┐                 ┌──▶ kitlib wwise ──▶ Wwise
XE125    ──USB─────▶ kitlib radar ────┤                 ├──▶ kitlib play ──▶ ChordCat / any synth
ChordCat ──MIDI────▶ kitlib midi ─────┼──▶ OSC :9000 ──▶┤
BuMoChi / SC / Pd ────────────────────┘                 └──▶ kitlib forward ──▶ Pd / SC / Godot / a laptop
```

## kitlib

The shared library, in `kitlib/`. Installing above puts a `kitlib` command on your path.

```
kitlib contract                                   the address namespace all six tracks agree on
kitlib monitor                                    watch everything arriving on 9000
kitlib send /wwise/rtpc Proximity 0.5             fire one message by hand
kitlib chord Cmaj7                                what a chord is made of, no hardware
kitlib sweep --out sweep.wav                      the excitation to play at a space
kitlib echo cap1.wav cap2.wav --celsius 4         distances, and how sure they are
kitlib wwise --map /sensor/radar=Proximity        OSC → Wwise, no game engine
kitlib arduino COM5 --scale force=fsr402          Arduino serial → bus
kitlib radar --normalise --smooth 0.15 --rate 60  XE125 → bus
kitlib midi                                       ChordCat / any MIDI in → bus
kitlib play --map /sensor/radar=C,Am,F,G          bus → MIDI out, play the hardware
kitlib forward --to 127.0.0.1:9001                mirror the bus to Pd, SC, Godot, a laptop
```

Crossing a sensor address into a Wwise verb needs the parameter name added and
any extra readings dropped, because the two namespaces count their arguments
differently:

```
kitlib forward --to 192.168.1.42 --pattern /sensor/radar \
               --rename /wwise/rtpc --lead Proximity --take 1
```

**When something is not working, run `kitlib monitor` first.** It prints every message arriving on the bus and, on Ctrl-C, how many of each and at what rate. Display is capped per address so a 650 Hz radar cannot scroll the useful lines away.

In your own code:

```python
from kitlib import Bus, signal

bus = Bus()
proximity = signal.RADAR_CM >> signal.Smooth(0.15) >> signal.RateLimit(60)
bus.send("/wwise/rtpc", "Proximity", proximity(reading))
```

| Module | What |
|---|---|
| `kitlib/contract.py` | the OSC address namespace. The one thing all six tracks agree on |
| `kitlib/bus.py` | send, subscribe by address or glob, serve in the foreground or a thread |
| `kitlib/signal.py` | scale, smooth, deadband, rate-limit, median, composed with `>>` |
| `kitlib/chords.py` | name a set of notes, spell a name. No hardware, no MIDI, no bus |
| `kitlib/echo.py` | sweep, deconvolve, distances to what reflected, confidence from repeats |
| `kitlib/sources/` | Arduino serial, XE125 radar, MIDI in |
| `kitlib/sinks/` | Wwise over WAAPI, MIDI out, forwarding to Pd / SuperCollider / Godot |

The presets in `signal.py` carry the real ranges out of `sensors/Sensor_Kit_Setup.md`, so `signal.FSR402` already knows the force sensor tops out near 650 rather than 1023, and `signal.LIGHT_LS06S` that its dark reading is 45 rather than 0.

Tests: `pytest`. 507 of them, no hardware required, about sixteen seconds.
`tests/test_integration.py` holds the cross-track paths and is where a new
source or verb proves it landed on the contract rather than beside it.

The four original scripts still answer to exactly the commands their READMEs describe. They are thin wrappers over the library now.

## Coding agents

`AGENTS.md` is the entry point: the one rule about the address namespace, which
track folders hold code and which are deliberately empty, the house conventions,
and the traps worth knowing before you debug. `CLAUDE.md` points at it.

## Contributing

PRs from teams welcome — put reusable bits under the track folder, credit your team in the file header, and post the link in your `<team>_music` Discord channel so the wiki picks it up.

## Ask

Mention **@eir** in any team channel on Discord, or paste `https://wiki.eir.sh/api/mcp` into your coding agent.
