"""A MIDI instrument onto the bus, with the chords worked out on the way.

Written for the Ch6 kit, an AlphaTheta ChordCat, which is a groovebox with MIDI
in, MIDI out/thru and USB-C. Nothing here is specific to it: any MIDI source
works, which is the point, because Ch2's brief is MIDI instruments and a Ch5
team turning movement into notes needs the same addresses.

Publishes three things, because three different teams want different ones:

    /chord/note  <note> <velocity>              every key movement, for a sequencer
    /chord/notes <note...>                      what is held now, for a synth
    /chord/name  <ChordName> <root> <quality>   the reading, for anything musical

A Wwise team can drive a switch group straight off ``/chord/name`` without
knowing a thing about MIDI. See ``kitlib.chords`` for the naming itself.

Needs ``pip install kitlib[midi]``.
"""
from __future__ import annotations

from typing import Iterator, List, Optional, Set

from .. import chords
from ..bus import Bus
from ..contract import CHORD_NAME, CHORD_NOTE, CHORD_NOTES

#: Substrings to look for when guessing which port is the ChordCat.
#:
#: The exact name the device presents has not been confirmed against hardware,
#: so this is a guess that degrades safely: if nothing matches, the caller is
#: told to list the ports and pass one explicitly rather than being connected
#: to whatever happened to be first.
PORT_HINTS = ("chordcat", "chord cat", "alphatheta")


def inputs() -> List[str]:
    """Every MIDI input port name the system can see."""
    import mido  # optional extra; imported late so a Pd team need not have it

    return list(mido.get_input_names())


def outputs() -> List[str]:
    """Every MIDI output port name the system can see."""
    import mido

    return list(mido.get_output_names())


def find_port(names: Optional[List[str]] = None,
              hints: Optional[tuple] = None) -> Optional[str]:
    """Guess which port is the ChordCat, or ``None`` if nothing looks right."""
    hints = hints or PORT_HINTS
    for name in (inputs() if names is None else names):
        lowered = name.lower()
        if any(hint in lowered for hint in hints):
            return name
    return None


def open_input(port: Optional[str] = None):
    """Open a MIDI input, guessing the port when one is not named."""
    import mido

    port = port or find_port()
    if not port:
        raise RuntimeError(
            "No ChordCat found. Run `kitlib midi --list` to see the ports this "
            "machine can see, then pass one by name. If the list is empty, the "
            "device is not connected or the OS has not claimed it yet; on a "
            "ChordCat check that it is on USB rather than battery-only and that "
            "nothing else already holds the port.")
    return mido.open_input(port)


def messages(port: Optional[str] = None, channel: Optional[int] = None) -> Iterator:
    """Yield MIDI messages forever. Closes the port on exit.

    ``channel`` filters to one 1..16 channel as printed on hardware. Left off,
    everything arriving is passed through, which is what you want until you
    know what the device actually sends on.
    """
    with open_input(port) as handle:
        for message in handle:
            if channel is not None and getattr(message, "channel", None) is not None:
                if message.channel + 1 != channel:
                    continue
            yield message


def held_after(message, held: Set[int]) -> Set[int]:
    """Apply one message to the set of sounding notes.

    A note-on at velocity 0 is a release. Hardware and sequencers both send it
    that way, so treating it as a key-down leaves notes stuck on forever.
    """
    kind = message.type
    if kind == "note_on" and message.velocity > 0:
        return held | {message.note}
    if kind == "note_off" or (kind == "note_on" and message.velocity == 0):
        return held - {message.note}
    return held


def run(port: Optional[str] = None, bus: Optional[Bus] = None,
        channel: Optional[int] = None, verbose: bool = False) -> None:
    """Pump a MIDI instrument onto the bus until interrupted.

    Every key movement publishes all three addresses, so a subscriber never has
    to reconstruct state it missed by starting late.
    """
    bus = bus or Bus()
    held: Set[int] = set()
    try:
        for message in messages(port, channel):
            if message.type not in ("note_on", "note_off"):
                continue
            velocity = message.velocity if message.type == "note_on" else 0
            held = held_after(message, held)
            sounding = sorted(held)

            bus.send(CHORD_NOTE, message.note, velocity)
            bus.send(CHORD_NOTES, *sounding)
            chord = chords.identify(sounding)
            if chord is not None:
                bus.send(CHORD_NAME, chord.name, chord.root, chord.quality)

            if verbose:
                spelling = chord.name if chord else "-"
                print(f"{[chords.note_name(n) for n in sounding]} {spelling}")
    except KeyboardInterrupt:
        pass
