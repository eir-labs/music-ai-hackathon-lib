"""The OSC contract every track shares.

One UDP port, one address namespace. A Ch3 team's radar can drive a Ch4 team's
Wwise session without either team reading the other's code, because both sides
agree on what is written here and nowhere else.

Four namespaces, in two kinds. A source publishes; a sink consumes.

    /sensor/<name>      raw-ish readings published by a source
    /chord/<what>       notes and chords published by a MIDI source
    /wwise/<verb>       commands consumed by the Wwise bridge
    /midi/<verb>        commands consumed by the MIDI sink

The MIDI pair is shared rather than private to Ch6 because three tracks reach
for it: the ChordCat is a MIDI groovebox, Ch2's brief is MIDI instruments, and
a Ch5 team turning movement into notes has nowhere else to put them. A gesture
can play a chord on somebody else's hardware without either team agreeing on
anything beyond what is written here.

Anything else is yours. Prefix a private namespace with your track, e.g.
``/ch5/pose/left_hand``, so it cannot collide with another team's.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

#: Everything on the shared bus speaks this, on every machine at the event.
PORT = 9000
HOST = "127.0.0.1"

SENSOR_NS = "/sensor"
CHORD_NS = "/chord"
WWISE_NS = "/wwise"
MIDI_NS = "/midi"

#: Namespaces a source writes to. Nothing consumes these by contract; a team
#: subscribes to what it wants.
PUBLISHED_NS = (SENSOR_NS, CHORD_NS)
#: Namespaces a sink reads. Sending to one is asking for something to happen.
CONSUMED_NS = (WWISE_NS, MIDI_NS)

EVENT = "/wwise/event"
RTPC = "/wwise/rtpc"
SWITCH = "/wwise/switch"
STATE = "/wwise/state"
POS = "/wwise/pos"
STOP = "/wwise/stop"

CHORD_NOTE = "/chord/note"
CHORD_NOTES = "/chord/notes"
CHORD_NAME = "/chord/name"

MIDI_NOTE = "/midi/note"
MIDI_CHORD = "/midi/chord"
MIDI_CC = "/midi/cc"
MIDI_PANIC = "/midi/panic"


@dataclass(frozen=True)
class Spec:
    """One address and the arguments it carries."""

    address: str
    args: Tuple[str, ...]
    doc: str

    def __str__(self) -> str:
        return f"{self.address} {' '.join(f'<{a}>' for a in self.args)}"


#: The Wwise verbs. ``gameObj`` is an integer you invent; the bridge registers
#: it on first use and defaults to 1.
WWISE_SPECS: Dict[str, Spec] = {
    EVENT: Spec(EVENT, ("EventName", "gameObj?"), "post an event"),
    RTPC: Spec(RTPC, ("RtpcName", "float", "gameObj?"), "set a game parameter"),
    SWITCH: Spec(SWITCH, ("Group", "State", "gameObj?"), "set a switch"),
    STATE: Spec(STATE, ("Group", "State"), "set a global state"),
    POS: Spec(POS, ("gameObj", "x", "y", "z"), "move a source"),
    STOP: Spec(STOP, ("gameObj?",), "stop everything on that object"),
}

#: The MIDI verbs, consumed by the MIDI sink. ``channel`` is 1..16 as printed
#: on hardware, not the 0..15 the wire uses; the sink converts.
MIDI_SPECS: Dict[str, Spec] = {
    MIDI_NOTE: Spec(MIDI_NOTE, ("note", "velocity?", "channel?"),
                    "play one note; velocity 0 releases it"),
    MIDI_CHORD: Spec(MIDI_CHORD, ("ChordName", "velocity?", "channel?"),
                     "play a named chord, e.g. Cmaj7"),
    MIDI_CC: Spec(MIDI_CC, ("controller", "value", "channel?"),
                  "send a control change"),
    MIDI_PANIC: Spec(MIDI_PANIC, ("channel?",), "release every note"),
}

#: What a MIDI source publishes. Nothing is obliged to listen, so these are
#: readings rather than commands, the same way ``/sensor/*`` is.
CHORD_SPECS: Dict[str, Spec] = {
    CHORD_NOTE: Spec(CHORD_NOTE, ("note", "velocity"),
                     "one key moved; velocity 0 is a release"),
    CHORD_NOTES: Spec(CHORD_NOTES, ("note...",), "every note held right now"),
    CHORD_NAME: Spec(CHORD_NAME, ("ChordName", "root", "quality"),
                     "what those notes spell, when they spell something"),
}

#: Every published address, so one lookup covers the whole contract.
SPECS: Dict[str, Spec] = {**WWISE_SPECS, **MIDI_SPECS, **CHORD_SPECS}


def sensor(name: str) -> str:
    """Address for a named sensor reading: ``sensor("radar")`` -> ``/sensor/radar``.

    Names are bare identifiers so they survive the trip through Pd receive
    names and SuperCollider symbols unchanged.
    """
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"sensor name must be alphanumeric or underscore, got {name!r}")
    return f"{SENSOR_NS}/{name}"


#: Grouped for printing, with the line each group's free-form namespace needs.
_GROUPS = (
    ("published by sources", CHORD_SPECS,
     (f"{SENSOR_NS}/<name> <float...>", "a sensor reading")),
    ("consumed by sinks", {**WWISE_SPECS, **MIDI_SPECS}, None),
)


def describe() -> str:
    """The contract as a printable table, for ``kitlib contract``.

    Grouped by direction, because the first thing a team needs to know about an
    address is whether sending to it asks for something or just announces it.
    """
    rows = [(str(spec), spec.doc) for spec in SPECS.values()]
    rows.append((f"{SENSOR_NS}/<name> <float...>", "a sensor reading"))
    width = max(len(shape) for shape, _ in rows)

    lines = []
    for heading, specs, extra in _GROUPS:
        lines.append(f"{heading}:")
        for spec in specs.values():
            lines.append(f"  {str(spec):<{width}}  {spec.doc}")
        if extra is not None:
            lines.append(f"  {extra[0]:<{width}}  {extra[1]}")
        lines.append("")
    return "\n".join(lines).rstrip()
