#!/usr/bin/env python3
"""
osc2wwise — drive Wwise from any OSC source, no game engine.

    pip install waapi-client python-osc
    python osc2wwise.py                       # listens on UDP 9000

Requires Wwise running with a project open and
Project > User Preferences > Enable Wwise Authoring API ticked.

OSC addresses (generic):
    /wwise/event   <EventName> [gameObj]            post an event
    /wwise/rtpc    <RtpcName> <float> [gameObj]     set a game parameter
    /wwise/switch  <Group> <State> [gameObj]
    /wwise/state   <Group> <State>
    /wwise/pos     <gameObj> <x> <y> <z>            move a source
    /wwise/stop    [gameObj]                        stop everything on it

Or map your own sensor addresses straight to RTPCs:
    python osc2wwise.py --map /sensor/prox=Proximity --map /pd/knob1=Cutoff

Every gameObj is an integer you invent; the bridge registers them on first use.
Default gameObj is 1.
"""
import argparse, sys
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from waapi import WaapiClient, CannotConnectToWaapiException

DEFAULT_GO = 1


class Bridge:
    def __init__(self, client, verbose):
        self.c, self.v, self.known = client, verbose, set()

    def call(self, uri, args):
        if self.v:
            print(uri, args)
        try:
            return self.c.call(uri, args)
        except Exception as e:
            print("WAAPI error:", uri, args, e, file=sys.stderr)

    def go(self, x):
        g = int(x) if x is not None else DEFAULT_GO
        if g not in self.known:
            self.call("ak.soundengine.registerGameObj", {"gameObject": g, "name": f"osc_{g}"})
            self.known.add(g)
        return g

    def event(self, _a, name, go=None):
        self.call("ak.soundengine.postEvent", {"event": str(name), "gameObject": self.go(go)})

    def rtpc(self, _a, name, value, go=None):
        self.call("ak.soundengine.setRTPCValue",
                  {"rtpc": str(name), "value": float(value), "gameObject": self.go(go)})

    def switch(self, _a, group, state, go=None):
        self.call("ak.soundengine.setSwitch",
                  {"switchGroup": str(group), "switchState": str(state), "gameObject": self.go(go)})

    def state(self, _a, group, state):
        self.call("ak.soundengine.setState", {"stateGroup": str(group), "state": str(state)})

    def pos(self, _a, go, x, y, z):
        self.call("ak.soundengine.setPosition", {
            "gameObject": self.go(go),
            "position": {"orientationFront": {"x": 0, "y": 0, "z": 1},
                         "orientationTop": {"x": 0, "y": 1, "z": 0},
                         "position": {"x": float(x), "y": float(y), "z": float(z)}}})

    def stop(self, _a, go=None):
        self.call("ak.soundengine.stopAll", {"gameObject": self.go(go)})

    def mapped(self, rtpc):
        # sensor address → fixed RTPC on the default game object; takes the first float arg
        def h(_a, *vals):
            if vals:
                self.rtpc(None, rtpc, vals[0])
        return h


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=9000, help="OSC UDP port to listen on (default 9000)")
    p.add_argument("--ip", default="0.0.0.0", help="bind address (default all interfaces)")
    p.add_argument("--waapi", default=None, help="WAAPI url (default ws://127.0.0.1:8080/waapi)")
    p.add_argument("--map", action="append", default=[], metavar="/osc/addr=RtpcName",
                   help="map an OSC address directly to an RTPC (repeatable)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()

    try:
        client = WaapiClient(a.waapi)
    except CannotConnectToWaapiException:
        sys.exit("Cannot reach Wwise. Is it running, is a project open, is WAAPI enabled in User Preferences?")

    info = client.call("ak.wwise.core.getInfo")
    print(f"Connected to {info['displayName']} {info['version']['displayName']}")

    b = Bridge(client, a.verbose)
    d = Dispatcher()
    d.map("/wwise/event", b.event)
    d.map("/wwise/rtpc", b.rtpc)
    d.map("/wwise/switch", b.switch)
    d.map("/wwise/state", b.state)
    d.map("/wwise/pos", b.pos)
    d.map("/wwise/stop", b.stop)
    for m in a.map:
        addr, _, rtpc = m.partition("=")
        if not rtpc:
            sys.exit(f"bad --map {m!r}, want /osc/addr=RtpcName")
        d.map(addr, b.mapped(rtpc))
        print(f"  {addr} -> RTPC {rtpc}")

    print(f"Listening for OSC on {a.ip}:{a.port}  (Ctrl-C to quit)")
    try:
        BlockingOSCUDPServer((a.ip, a.port), d).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
