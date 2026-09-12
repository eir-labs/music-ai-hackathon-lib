# Ch6 Accessibility — AlphaTheta ChordCat

5 sets at the kit table. Wiki: `challenge.accessibility`.

An 8-track groovebox built around chords: Chord Play and Chord Cruiser modes, a
step sequencer, and on the back a USB-C socket, a MIDI IN DIN and a MIDI
OUT/THRU DIN. Runs off USB bus power at 5 V 500 mA, or six AA alkalines for
about five hours.

Everything below is from the ChordCat MIDI Implementation Guide and the
operating manual (DRJ1099A).

## The chord library, with no hardware at all

`kitlib.chords` is arithmetic on note numbers. No ChordCat, no MIDI library, no
bus, so it works on the plane and in a corner of the hotel with no wifi.

```
kitlib chord Cmaj7          C4 E4 G4 B4    60 64 67 71
kitlib chord F#m7 --octave 3
kitlib chord Bb7 --flats
```

```python
from kitlib import chords

chords.identify([60, 64, 67, 71]).name     # 'Cmaj7'
chords.identify([64, 67, 72]).name         # 'C/E', an inversion
chords.spell("Am7")                        # [69, 72, 76, 79]
chords.transpose(chords.spell("C"), 5)     # up a fourth
```

A set of notes that spells nothing comes back as `None` rather than a guess. A
wrong chord name is worse than no chord name, because a mapping gets built on
it and then drifts.

## One USB cable is the whole setup

The cable carries MIDI in both directions. Two facts make this easier than it
looks:

- The device's **MIDI IN settings apply to the USB socket and the DIN socket
  alike**, so there is no separate USB configuration to find.
- The **USB socket always transmits what the ChordCat itself plays**, whatever
  MIDI OUT/THRU Mode is set to. Reading chords off the device needs no menu
  diving at all.

To let a computer play the device, set `Menu` > `MIDI IN Settings` >
`Sync Source` to `USB MIDI`. To sync the other way, leave it `Internal`.

## Channels choose tracks

Out of the box the eight tracks listen on **USB channels 1 to 8, one each**, so
channel 3 plays track 3. Changed under `Menu` > `Track MIDI Settings` >
`MIDI IN`, where each track can also be set to a DIN channel or disabled.

Channels are 1 to 16 as printed on the hardware. MIDI puts 0 to 15 on the wire,
and `kitlib` converts once, inside the sink. There is also an `ALL` setting on
the device, which ignores the channel entirely.

## Onto the bus

```
kitlib midi --list                        which ports this machine can see
kitlib midi                               ChordCat -> OSC, guessing the port
kitlib midi "ChordCat" -v --channel 3     or name the port and a track
```

```
/chord/note  <note> <velocity>              every key movement; velocity 0 is a release
/chord/notes <note...>                      what is held right now
/chord/name  <ChordName> <root> <quality>   what those notes spell
```

The device transmits note on, note off, control change, program change, and
MIDI timing clock with start, continue and stop. `kitlib midi` reads the notes;
the rest is on the bus for anyone who wants to add it.

A Ch4 team can drive a Wwise switch group straight off `/chord/name` without
learning what a MIDI note number is.

## Back out to the hardware

```
kitlib play                                         bus -> ChordCat
kitlib play --map /sensor/radar=C,Am,F,G            a hand in the air plays the changes
```

```
/midi/note   <note> <velocity?> <channel?>       velocity 0 releases
/midi/chord  <ChordName> <velocity?> <channel?>  Cmaj7, F#m, Bb7
/midi/cc     <controller> <value> <channel?>     a name or a number
/midi/panic  <channel?>                          silence everything
```

`--map` walks a progression from any address already scaled to 0 and 1, which
is the shortest route from a sensor to something musical. A new chord releases
the one before it, so a stream of readings sounds like playing rather than a
pile-up, and it only retriggers when the chord actually changes.

The ChordCat acts on a fixed list of control changes and silently ignores the
rest, which looks exactly like a broken cable. Use the names:

| Name | CC | Name | CC |
|---|---|---|---|
| `volume` | 7 | `attack` | 73 |
| `pan` | 10 | `release` | 72 |
| `cutoff` | 74 | `reverb` | 91 |
| `resonance` | 71 | `chorus` | 93 |
| `portamento` | 65 | `portamento_time` | 5 |

```
kitlib send /midi/cc cutoff 40
```

`/midi/panic` releases the notes the sink knows it sounded and then sends the
device's own All Sound Off, which catches anything else.

## Three things that will waste your afternoon

**It turns itself off after 20 minutes.** Auto power off is enabled by default
and triggers on 20 minutes with no MIDI traffic and no button presses. An
installation left running between demos will be dead when you come back. Turn
it off under `Menu` > `System Settings` > `Auto Power Off`.

**A dark ChordCat is not an off ChordCat.** The display and panel lighting dim
after 5 idle minutes and go out after 5 more. Touching anything brings them
back.

**Power it down with the button, not the cable.** Pulling USB or cutting power
to the host skips the save-and-resume step, and the next power-up will not pick
up where you left off. The button is on the rear panel.

## Where this is going

The brief asks how AI and new interfaces lower the barrier to making music. The
pieces above are the plumbing for that, not an answer to it. Two shapes teams
have reached for already:

- **A sensor as the instrument.** Radar, light or force from the Ch3 kit walks a
  progression while the ChordCat supplies the voicings. Someone with limited
  movement plays harmony with a gesture the size of a wrist.
- **A gesture as the performer.** Ch5 pose tracking picks the chord while
  something else picks the rhythm.

Team Sound Flux Music asked on the wiki whether an interface can reach the
ChordCat's chords. Both directions above are that, and `kitlib.chords` is the
part that works whether or not a device is in the room.

## Still unverified

The exact string the device presents as a MIDI port name. `kitlib midi --list`
prints it; the port guess matches on "chordcat" and "alphatheta" and fails
cleanly rather than connecting to the wrong device. The manual documents no
driver for either platform and the device is USB bus powered, which is
consistent with it being class compliant, but that is inference rather than a
documented fact. First team to plug one in, put the answer on the wiki.
