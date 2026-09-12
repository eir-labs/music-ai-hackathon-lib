# Ch6 Accessibility — AlphaTheta ChordCat

5 sets at the kit table. Wiki: `challenge.accessibility`.

The ChordCat is an 8-track groovebox built around chords: Chord Play and Chord
Cruiser modes, a large bank of chord voicings, an 8-track sequencer, and MIDI
IN, MIDI OUT/THRU and USB-C on the back. The MIDI ports are the way in and out
for everything below.

**Not confirmed against the hardware yet:** the exact name the device presents
as a MIDI port, which channel it sends on, and whether it is class-compliant
over USB-C or wants a driver. Nothing in `kitlib` hardcodes any of those. Run
`kitlib midi --list` on the machine with the device attached, and if the guess
is wrong, pass the port by name. Tell the Ch6 mentor what it turns out to be
and put it on the wiki.

## The chord library, with no hardware at all

`kitlib.chords` is arithmetic on note numbers. It needs no ChordCat, no MIDI
library and no bus, so it works on the plane and in a browser-free corner of
the hotel.

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

## Onto the bus

```
kitlib midi --list                        which ports this machine can see
kitlib midi                               ChordCat -> OSC, guessing the port
kitlib midi "ChordCat MIDI 1" -v          or name it
```

Publishes three things, so different tracks can take what suits them:

```
/chord/note  <note> <velocity>              every key movement; velocity 0 is a release
/chord/notes <note...>                      what is held right now
/chord/name  <ChordName> <root> <quality>   what those notes spell
```

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
/midi/cc     <controller> <value> <channel?>
/midi/panic  <channel?>                          release everything
```

Channels are 1 to 16 as printed on the hardware. MIDI puts 0 to 15 on the wire,
and the conversion happens once, inside the sink.

`--map` walks a progression from any address already scaled to 0 and 1, which
is the shortest route from a sensor to something musical. A new chord releases
the one before it, so a stream of readings sounds like playing rather than a
pile-up, and it only retriggers when the chord actually changes.

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
