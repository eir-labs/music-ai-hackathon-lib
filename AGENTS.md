# Working in this repo

Toolkit for the Music & AI Hackathon 2026. Six challenge tracks, one shared
convention: **everything talks OSC on UDP 9000**, so a sensor team can drive a
game-audio team's mix without either side reading the other's code.

The code that matters is `kitlib/`. Everything else is documentation, hardware
notes, or a pointer to somebody else's repo.

## The one rule

`kitlib/contract.py` is the single source of truth for the address namespace.
Six teams have patches pointed at it. Changing an address there breaks work on
other laptops that you cannot see and cannot test.

- Adding a verb is fine. Wire it into the sink that serves its namespace,
  `WwiseSink.attach` or `MidiSink.attach`, in the same change, or
  `tests/test_integration.py` will fail with the verb's name in the output.
- Renaming or removing one is a decision for the organisers, not a refactor.
- There are four shared namespaces in two kinds. `/sensor/*` and `/chord/*` are
  published by sources; `/wwise/*` and `/midi/*` are consumed by sinks. Sending
  to a consumed one asks for something to happen.
- Anything outside those four belongs to whoever invented it. Prefix a private
  namespace with the track, `/ch5/pose/left_hand`, so it cannot collide.

Run `kitlib contract` to see the namespace as teams see it.

## Setup

```
pip install -e .            # the library and the CLI, nothing else
pip install -e ".[arduino]" # or [radar], [wwise], [midi], [all]
pytest                      # 435 tests, no hardware, about fifteen seconds
```

Install the extra your track needs rather than `requirements.txt`, which pulls
the radar SDK, the Wwise client and NumPy for everyone. A Pd team on a
Raspberry Pi has no reason to wait for any of it.

The BuMoChi track is a submodule. A fresh clone needs:

```
git submodule update --init --recursive
```

## Where things are

| Path | State | Notes |
|---|---|---|
| `kitlib/` | code, tested | the bus, chords, signal stages, sources, sinks, CLI |
| `tests/` | code, tested | per-component files plus `test_integration.py` |
| `sensors/` | code + real docs | Ch3. `Sensor_Kit_Setup.md` is the hard-won part |
| `wwise/` | code + real docs | Ch4. The bridge lives in `kitlib/sinks/wwise.py` |
| `bumochi/` | submodule + notes | Ch5. Upstream code, our notes in `README.md` |
| `lydia/` | notes only | Ch2. Roland's toolkit is not in this repo |
| `recorders/` | notes only | Ch1. Hardware at the kit table |
| `chordcat/` | code + notes | Ch6. The code is `kitlib/chords.py` and the MIDI pair |

Three track folders hold no code on purpose. If asked to build something for
Ch1 or Ch2, there is no local foundation to extend, and the honest first move
is to say so and ask what the team already has.

## Conventions

**Hardware imports are lazy.** `import serial`, `acconeer.exptool`, `waapi` and
`mido` happen inside the function that needs them, never at module scope. That is what
lets the whole suite run on a laptop with nothing plugged in, and what lets a
team install one extra instead of all three. Keep it that way.

**Test doubles live in `tests/doubles.py`.** One fake serial port, one fake
radar board, one fake WAAPI client, one fake MIDI port, installed by fixtures
in `conftest.py`. Write a new test against those rather than another copy.

**Tests use a real socket.** The bus is not mocked. Messages cross UDP and land
on a server thread, so assert through `collector.wait_for(n)` or the WAAPI
client's `wait_for_of(uri, n)`, never immediately. A test that asserts too early
passes for the wrong reason on a fast machine and fails on a slow one. Wait for
the specific call rather than a total: registering a game object is a call too,
and it happens only the first time an object is mentioned.

**Register handlers on the bus that is serving.** A `Bus` only dispatches on
the socket it bound. Registering a handler on a sending bus is a silent no-op.

**Docstrings say why, not what.** The existing ones name the specific thing
that goes wrong at this event: that the force sensor tops out near 650, that
the radar sweeps at 650 Hz, that Wwise drops calls against an unregistered game
object. Match that. A docstring restating the function signature is noise.

## Traps worth knowing before you debug

**`kitlib monitor` first.** It prints everything arriving on 9000 and, on
Ctrl-C, how many of each and at what rate. Most "it isn't working" is a source
pointed at the wrong host.

**Only one process can hold port 9000.** A source and a sink on one laptop both
construct a `Bus`, and only the sink should bind. `Bus` binds lazily on
`serve_forever` or `start`, which is why.

**Crossing `/sensor/*` into `/wwise/*` needs reshaping.** The two namespaces
count arguments differently. `/sensor/radar` carries `<cm> <magnitude>`;
`/wwise/rtpc` wants `<RtpcName> <float>`. Forwarding with a bare rename sets a
parameter named after the distance. Use `lead=` to put the name on the front
and `take=` to drop the magnitude, or let the receiving bridge do it with
`--map`. Pinned in `TestAcrossMachines`.

**The radar is not a Grove module.** It goes to the PC over USB-C, never near
the Arduino. See `sensors/XE125_Setup_Windows.md`.

**A MIDI note-on at velocity 0 is a release.** Hardware and sequencers both send
releases that way. Reading it as a key-down leaves every note held forever, and
the instrument sounds jammed. Handled in `held_after`; do not undo it.

**MIDI channels are 1 to 16 on hardware and 0 to 15 on the wire.** Converted
once, inside the MIDI sink. Do not convert again anywhere else.

**The ChordCat's port name is a guess.** It has not been confirmed against the
device. `kitlib midi --list` is the ground truth; nothing hardcodes a name.

## Contributing back

Teams send PRs. Put reusable work under the track folder, credit the team in
the file header, and keep the four original scripts in `sensors/` and `wwise/`
answering to the commands their own docstrings describe. They are thin wrappers
over `kitlib` now, and `tests/test_wrappers.py` holds them to it.
