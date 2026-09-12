# Music & AI Hackathon 2026 — toolkit

Berghotel Rudolfshütte · Sep 11–13, 2026. One repo with the setup docs, glue scripts and pointers for every challenge track.
The living version is the wiki — https://wiki.eir.sh/hackathon — where team pages accrete from Discord and coding agents. This repo is the offline-friendly, cloneable subset.

```
pip install -r requirements.txt
```

| Track | Folder | Start with |
|---|---|---|
| Ch1 Sound & Nature (Austria Tourism) | `recorders/` | the recorders at the kit table |
| Ch2 AI Instruments (Roland & Neutone) | `lydia/` | `README.md` → Roland's DIY doc |
| Ch3 Sound & Driving (Alps Alpine) | `sensors/` | `Sensor_Kit_Setup.md` **before plugging anything in** |
| Ch4 Game Sound (Audiokinetic) | `wwise/` | `osc2wwise.py` |
| Ch5 Moving Bodies (academic) | `bumochi/` | upstream BuMoChi |
| Ch6 Accessibility (AlphaTheta) | `chordcat/` | the Ch6 mentor |

`Challenges.pdf` — the official briefs.

## Glue

Everything here talks OSC on UDP 9000 so tracks can borrow from each other:

```
Arduino  ──serial──▶ sensors/arduino_serial_to_osc.py ──┐
XE125    ──USB─────▶ sensors/xe125_to_osc.py ───────────┤
BuMoChi / SC / Pd ──────────────────────────────────────┼──▶ OSC :9000 ──▶ wwise/osc2wwise.py ──▶ Wwise
                                                        └──▶ Pd [udpreceive] / SC OSCdef / Godot / anything
```

## Contributing

PRs from teams welcome — put reusable bits under the track folder, credit your team in the file header, and post the link in your `<team>_music` Discord channel so the wiki picks it up.

## Ask

Mention **@eir** in any team channel on Discord, or paste `https://wiki.eir.sh/api/mcp` into your coding agent.
