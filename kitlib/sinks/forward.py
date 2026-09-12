"""Mirror the bus somewhere else: Pure Data, SuperCollider, Godot, a laptop.

Everything at the event lands on UDP 9000, but a Pd patch wants its own port
and the team across the room wants the same stream on their machine. Forward
listens on the bus and re-sends, optionally renaming addresses and conditioning
values on the way.

    from kitlib import Bus
    from kitlib.sinks.forward import Forward

    pd = Bus(port=9001)
    godot = Bus(host="192.168.1.42", port=9002)
    bus = Bus()
    Forward(pd, godot).route("/sensor/*").attach(bus)
    bus.serve_forever()
"""
from __future__ import annotations

from typing import List, NamedTuple, Optional, Tuple

from ..bus import Bus
from ..signal import Stage


class Route(NamedTuple):
    pattern: str
    to: Optional[str]
    stage: Optional[Stage]
    lead: Tuple = ()
    take: Optional[int] = None


class Forward:
    """Re-send bus traffic to one or more OSC endpoints."""

    def __init__(self, *targets: Bus):
        if not targets:
            raise ValueError("Forward needs at least one target Bus")
        self.targets = targets
        self.routes: List[Route] = []

    def route(self, pattern: str = "/*", to: Optional[str] = None,
              stage: Optional[Stage] = None, lead: Tuple = (),
              take: Optional[int] = None) -> "Forward":
        """Forward addresses matching ``pattern``, chainable.

        ``to`` renames the outgoing address, ``lead`` prepends fixed arguments
        and ``take`` keeps only the first N incoming ones. Reshaping one
        namespace into another usually needs all three, because the two sides
        count their arguments differently. A Ch3 radar publishes
        ``/sensor/radar <cm> <magnitude>``; ``/wwise/rtpc`` wants
        ``<RtpcName> <float> <gameObj?>``, so the name goes on the front and
        the magnitude has to come off the back or it lands in the game-object
        slot::

            Forward(wwise).route("/sensor/radar", to="/wwise/rtpc",
                                 lead=("Proximity",), take=1)
            # /sensor/radar 12.5 880.0  ->  /wwise/rtpc Proximity 12.5

        Rename with neither and the distance becomes the RTPC name, which is
        why ``kitlib contract`` is worth reading before reshaping. Forwarding
        a namespace to another machine unchanged needs none of them.

        ``stage`` conditions the first argument of the incoming message, before
        ``take`` trims and ``lead`` goes on the front; returning ``None`` drops
        the message rather than sending a stale value on.
        """
        self.routes.append(Route(pattern, to, stage, tuple(lead), take))
        return self

    def _send(self, route: Route, address: str, values) -> None:
        values = list(values)
        if route.stage is not None and values:
            conditioned = route.stage(values[0])
            if conditioned is None:
                return
            values[0] = conditioned
        if route.take is not None:
            values = values[:route.take]
        out = route.to or address
        values = list(route.lead) + values
        for target in self.targets:
            target.send(out, *values)

    def attach(self, bus: Bus) -> "Forward":
        """Wire the routes onto ``bus``. With no routes, mirrors everything."""
        if not self.routes:
            self.route()

        for route in self.routes:
            def handle(address, *values, _route=route):
                self._send(_route, address, values)

            bus.on(route.pattern, handle)
        return self

    def __repr__(self) -> str:
        where = ", ".join(f"{t.host}:{t.port}" for t in self.targets)
        return f"Forward({where}, {len(self.routes)} routes)"
