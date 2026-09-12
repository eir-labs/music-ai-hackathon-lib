"""The OSC contract every track shares.

One UDP port, one address namespace. A Ch3 team's radar can drive a Ch4 team's
Wwise session without either team reading the other's code, because both sides
agree on what is written here and nowhere else.

Two namespaces:

    /sensor/<name>      raw-ish readings published by a source
    /wwise/<verb>       commands consumed by the Wwise bridge

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
WWISE_NS = "/wwise"

EVENT = "/wwise/event"
RTPC = "/wwise/rtpc"
SWITCH = "/wwise/switch"
STATE = "/wwise/state"
POS = "/wwise/pos"
STOP = "/wwise/stop"


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
SPECS: Dict[str, Spec] = {
    EVENT: Spec(EVENT, ("EventName", "gameObj?"), "post an event"),
    RTPC: Spec(RTPC, ("RtpcName", "float", "gameObj?"), "set a game parameter"),
    SWITCH: Spec(SWITCH, ("Group", "State", "gameObj?"), "set a switch"),
    STATE: Spec(STATE, ("Group", "State"), "set a global state"),
    POS: Spec(POS, ("gameObj", "x", "y", "z"), "move a source"),
    STOP: Spec(STOP, ("gameObj?",), "stop everything on that object"),
}


def sensor(name: str) -> str:
    """Address for a named sensor reading: ``sensor("radar")`` -> ``/sensor/radar``.

    Names are bare identifiers so they survive the trip through Pd receive
    names and SuperCollider symbols unchanged.
    """
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"sensor name must be alphanumeric or underscore, got {name!r}")
    return f"{SENSOR_NS}/{name}"


def describe() -> str:
    """The contract as a printable table, for ``kitlib contract``."""
    width = max(len(str(s)) for s in SPECS.values())
    lines = [f"{str(s):<{width}}  {s.doc}" for s in SPECS.values()]
    lines.append(f"{SENSOR_NS + '/<name> <float...>':<{width}}  a sensor reading")
    return "\n".join(lines)
