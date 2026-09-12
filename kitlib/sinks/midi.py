"""The bus back out to MIDI: play somebody else's hardware from anywhere.

The mirror of ``kitlib.sources.midi``. A Ch3 radar, a Ch5 gesture or a Ch2 Pd
patch sends ``/midi/chord Cmaj7`` and the ChordCat, or any synth, plays it.
Neither side has to know what the other is.

    /midi/note   <note> <velocity?> <channel?>       velocity 0 releases
    /midi/chord  <ChordName> <velocity?> <channel?>  Cmaj7, F#m, Bb7
    /midi/cc     <controller> <value> <channel?>
    /midi/panic  <channel?>                          release everything

Channels are 1..16 as printed on hardware. MIDI puts 0..15 on the wire and the
conversion is the single commonest off-by-one in this corner of the world, so
it happens here, once.

Needs ``pip install kitlib[midi]``.
"""
from __future__ import annotations

import sys
from typing import Dict, List, Optional, Set

from .. import chords
from ..bus import Bus
from ..contract import MIDI_CC, MIDI_CHORD, MIDI_NOTE, MIDI_PANIC

DEFAULT_VELOCITY = 100
DEFAULT_CHANNEL = 1


class CannotReachMidi(RuntimeError):
    """Raised with what to try instead."""


def open_output(port: Optional[str] = None):
    """Open a MIDI output, or explain what is available instead."""
    import mido  # optional extra; imported late

    available = list(mido.get_output_names())
    if port is None:
        from ..sources.midi import find_port
        port = find_port(available)
    if not port:
        raise CannotReachMidi(
            "No MIDI output chosen and none looked like a ChordCat. "
            + (f"Available: {', '.join(available)}. Pass one by name."
               if available else
               "This machine can see no MIDI outputs at all; check the cable."))
    if port not in available:
        raise CannotReachMidi(
            f"No MIDI output called {port!r}. "
            + (f"Available: {', '.join(available)}."
               if available else "This machine can see no MIDI outputs at all."))
    return mido.open_output(port)


class MidiSink:
    """Translates the ``/midi/*`` verbs into MIDI messages.

    Tracks what it has sounded, per channel, so ``panic`` can release exactly
    those and a new chord can replace the one before it. Without that, a stream
    of chords from a sensor leaves every note it ever played held down.
    """

    def __init__(self, port, verbose: bool = False):
        self.port = port
        self.verbose = verbose
        self._sounding: Dict[int, Set[int]] = {}

    @classmethod
    def open(cls, port: Optional[str] = None, verbose: bool = False) -> "MidiSink":
        return cls(open_output(port), verbose)

    # -- plumbing --------------------------------------------------------

    def send(self, kind: str, **fields) -> None:
        import mido

        if self.verbose:
            print(kind, fields)
        try:
            self.port.send(mido.Message(kind, **fields))
        except Exception as exc:  # a bad note number should not kill the sink
            print("MIDI error:", kind, fields, exc, file=sys.stderr)

    @staticmethod
    def _wire_channel(channel=None) -> int:
        """1..16 as printed on hardware becomes 0..15 as sent on the wire."""
        number = DEFAULT_CHANNEL if channel is None else int(channel)
        return min(max(number, 1), 16) - 1

    def _sound(self, note: int, velocity: int, channel: int) -> None:
        self.send("note_on", note=note, velocity=velocity, channel=channel)
        self._sounding.setdefault(channel, set()).add(note)

    def _release(self, note: int, channel: int) -> None:
        self.send("note_off", note=note, velocity=0, channel=channel)
        self._sounding.get(channel, set()).discard(note)

    # -- the verbs -------------------------------------------------------

    def note(self, _address, note, velocity=None, channel=None) -> None:
        wire = self._wire_channel(channel)
        level = DEFAULT_VELOCITY if velocity is None else int(velocity)
        number = int(note)
        if level > 0:
            self._sound(number, min(level, 127), wire)
        else:
            self._release(number, wire)

    def chord(self, _address, name, velocity=None, channel=None) -> None:
        """Play a named chord, releasing whatever was sounding on that channel.

        Replacing rather than layering is what makes a stream of chords from a
        sensor sound like playing and not like a pile-up.
        """
        wire = self._wire_channel(channel)
        try:
            notes = chords.spell(str(name))
        except ValueError as exc:
            print(f"MIDI error: {exc}", file=sys.stderr)
            return

        level = DEFAULT_VELOCITY if velocity is None else int(velocity)
        for sounding in sorted(self._sounding.get(wire, set())):
            self._release(sounding, wire)
        if level <= 0:
            return
        for number in notes:
            self._sound(number, min(level, 127), wire)

    def cc(self, _address, controller, value, channel=None) -> None:
        self.send("control_change", control=int(controller),
                  value=min(max(int(value), 0), 127),
                  channel=self._wire_channel(channel))

    def panic(self, _address, channel=None) -> None:
        """Release every note this sink has sounded, on one channel or all."""
        wires = ([self._wire_channel(channel)] if channel is not None
                 else list(self._sounding))
        for wire in wires:
            for note in sorted(self._sounding.get(wire, set())):
                self._release(note, wire)

    # -- wiring ----------------------------------------------------------

    def attach(self, bus: Bus) -> "MidiSink":
        """Register every ``/midi/*`` verb on the bus."""
        for address, handler in ((MIDI_NOTE, self.note), (MIDI_CHORD, self.chord),
                                 (MIDI_CC, self.cc), (MIDI_PANIC, self.panic)):
            bus.on(address, handler)
        return self

    def map_chord(self, bus: Bus, address: str, names: List[str],
                  velocity: int = DEFAULT_VELOCITY) -> "MidiSink":
        """Drive a chord progression from one continuous address.

        A radar reading of 0..1 walked across a list of chords is the shortest
        path from a sensor to something musical, and it is what a Ch6 team
        demonstrating an accessible instrument actually wants::

            sink.map_chord(bus, "/sensor/radar", ["C", "Am", "F", "G"])

        The value picks a chord by position, so anything already scaled to 0..1
        works without further arithmetic.
        """
        if not names:
            raise ValueError("map_chord needs at least one chord name")
        for name in names:
            chords.parse(name)  # fail now, not on the first gesture

        last: List[Optional[str]] = [None]

        def handle(_address, *values):
            if not values:
                return
            position = min(max(float(values[0]), 0.0), 1.0)
            index = min(int(position * len(names)), len(names) - 1)
            if names[index] != last[0]:
                last[0] = names[index]
                self.chord(None, names[index], velocity)

        bus.on(address, handle)
        return self

    def close(self) -> None:
        self.panic(None)
        self.port.close()

    def __enter__(self) -> "MidiSink":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
