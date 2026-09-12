#!/usr/bin/env python3
"""osc2wwise -- drive Wwise from any OSC source, no game engine.

    python osc2wwise.py                       # listens on UDP 9000
    python osc2wwise.py --map /sensor/radar=Proximity -v

Requires Wwise running with a project open and
Project > User Preferences > Enable Wwise Authoring API ticked.

OSC addresses:
    /wwise/event   <EventName> [gameObj]            post an event
    /wwise/rtpc    <RtpcName> <float> [gameObj]     set a game parameter
    /wwise/switch  <Group> <State> [gameObj]
    /wwise/state   <Group> <State>
    /wwise/pos     <gameObj> <x> <y> <z>            move a source
    /wwise/stop    [gameObj]                        stop everything on it

Every gameObj is an integer you invent; the bridge registers them on first use.
Default gameObj is 1.

This is a wrapper kept so the documented command still works. The same thing is
`kitlib wwise`. See kitlib/sinks/wwise.py.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from kitlib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["wwise", *sys.argv[1:]]))
