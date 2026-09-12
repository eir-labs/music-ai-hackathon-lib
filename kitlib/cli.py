"""The ``kitlib`` command. Seven subcommands, one bus.

    kitlib contract                 print the shared address namespace
    kitlib monitor                  watch everything arriving on 9000
    kitlib send /wwise/rtpc X 0.5   fire one message by hand
    kitlib wwise --map ...          run the Wwise bridge
    kitlib arduino COM5             pump an Arduino onto the bus
    kitlib radar                    pump the XE125 onto the bus
    kitlib forward --to host:9001   mirror the bus elsewhere
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from typing import List

from . import contract, signal
from .bus import Bus


def _number(text: str):
    """OSC arguments off the command line: numbers as numbers, rest as text."""
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def _format(value) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def _host_port(text: str, default_port: int) -> tuple:
    host, _, port = text.partition(":")
    return host or contract.HOST, int(port) if port else default_port


# -- subcommands ---------------------------------------------------------

def cmd_contract(args) -> int:
    print(contract.describe())
    return 0


def cmd_monitor(args) -> int:
    """Watch the bus. Display is throttled per address, counting is not.

    The radar sweeps at up to 650 Hz. Printing every frame tells you nothing
    and scrolls the useful lines away, so each address prints at most
    ``--max-hz`` times a second while the exit summary counts them all.
    """
    bus = Bus(bind=args.bind, listen_port=args.port)
    counts: Counter = Counter()
    throttles = {}

    def show(address, *values):
        counts[address] += 1
        if args.max_hz > 0:
            gate = throttles.setdefault(address, signal.RateLimit(args.max_hz))
            if gate(0.0) is None:
                return
        print(f"{address} {' '.join(_format(v) for v in values)}")

    bus.on_default(show)
    print(f"Watching {args.bind}:{args.port}  (Ctrl-C to quit)")
    if args.max_hz > 0:
        print(f"Display capped at {args.max_hz:g} Hz per address; every message is counted.")

    started = time.monotonic()
    try:
        bus.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bus.close()

    elapsed = max(time.monotonic() - started, 1e-9)
    if not counts:
        print(f"\nNothing arrived in {elapsed:.1f}s. Is the source pointed at "
              f"port {args.port}, and on this machine?")
        return 1
    width = max(len(a) for a in counts)
    print(f"\n{elapsed:.1f}s")
    for address, count in counts.most_common():
        print(f"  {address:<{width}}  {count:>8}  {count / elapsed:7.1f} Hz")
    return 0


def cmd_send(args) -> int:
    bus = Bus(host=args.host, port=args.port)
    values = [_number(a) for a in args.args]
    bus.send(args.address, *values)
    print(f"sent {args.address} {' '.join(_format(v) for v in values)} "
          f"to {args.host}:{args.port}")
    return 0


def cmd_wwise(args) -> int:
    from .sinks.wwise import CannotReachWwise, WwiseSink

    # Check the arguments before reaching for the network, so a typo is a typo
    # rather than a puzzling connection failure.
    mappings = []
    for mapping in args.map:
        address, _, rtpc = mapping.partition("=")
        if not rtpc:
            print(f"bad --map {mapping!r}, want /osc/addr=RtpcName", file=sys.stderr)
            return 2
        mappings.append((address, rtpc))

    try:
        sink = WwiseSink.connect(args.waapi, args.verbose)
    except CannotReachWwise as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Connected to {sink.describe_connection()}")
    bus = Bus(bind=args.ip, listen_port=args.port)
    sink.attach(bus)
    for address, rtpc in mappings:
        sink.map_rtpc(bus, address, rtpc)
        print(f"  {address} -> RTPC {rtpc}")

    print(f"Listening for OSC on {args.ip}:{args.port}  (Ctrl-C to quit)")
    try:
        bus.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bus.close()
        sink.close()
    return 0


def _preset(name: str):
    try:
        return signal.PRESETS[name]
    except KeyError:
        raise argparse.ArgumentTypeError(
            f"unknown preset {name!r}; choose from {', '.join(sorted(signal.PRESETS))}")


def cmd_arduino(args) -> int:
    from .sources.arduino import run

    stages = {}
    for mapping in args.scale:
        name, _, preset = mapping.partition("=")
        if not preset:
            print(f"bad --scale {mapping!r}, want name=preset", file=sys.stderr)
            return 2
        stages[name] = _preset(preset)
        print(f"  {contract.sensor(name)} scaled by {preset}")

    print(f"Reading {args.serial} at {args.baud} -> {args.host}:{args.port}")
    run(args.serial, args.baud, Bus(args.host, args.port), stages, args.verbose)
    return 0


def cmd_radar(args) -> int:
    from .sources import radar

    stages: List = []
    if args.normalise:
        stages.append(signal.RADAR_CM)
    if args.median:
        stages.append(signal.Median(args.median))
    if args.smooth:
        stages.append(signal.Smooth(args.smooth))
    if args.rate:
        stages.append(signal.RateLimit(args.rate))
    stage = signal.Chain(*stages) if stages else None

    print(f"Radar -> {args.host}:{args.port}" + (f"  [{stage!r}]" if stage else ""))
    try:
        radar.run(args.serial, Bus(args.host, args.port), stage,
                  verbose=args.verbose)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_forward(args) -> int:
    from .sinks.forward import Forward

    targets = [Bus(*_host_port(t, contract.PORT + 1)) for t in args.to]
    forward = Forward(*targets)
    forward.route(args.pattern, to=args.rename,
                  stage=_preset(args.scale) if args.scale else None,
                  lead=tuple(_number(a) for a in args.lead), take=args.take)
    bus = Bus(bind=args.bind, listen_port=args.port)
    forward.attach(bus)

    print(f"Forwarding {args.pattern} from {args.bind}:{args.port} to "
          + ", ".join(f"{t.host}:{t.port}" for t in targets))
    try:
        bus.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bus.close()
    return 0


# -- wiring --------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kitlib", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest="command", required=True)

    subs.add_parser("contract", help="print the shared OSC address namespace"
                    ).set_defaults(run=cmd_contract)

    monitor = subs.add_parser("monitor", help="watch everything on the bus")
    monitor.add_argument("--port", type=int, default=contract.PORT)
    monitor.add_argument("--bind", default="0.0.0.0")
    monitor.add_argument("--max-hz", type=float, default=20.0,
                         help="display cap per address, 0 to print everything")
    monitor.set_defaults(run=cmd_monitor)

    send = subs.add_parser("send", help="fire one message by hand")
    send.add_argument("address")
    send.add_argument("args", nargs="*")
    send.add_argument("--host", default=contract.HOST)
    send.add_argument("--port", type=int, default=contract.PORT)
    send.set_defaults(run=cmd_send)

    wwise = subs.add_parser("wwise", help="run the OSC to Wwise bridge")
    wwise.add_argument("--port", type=int, default=contract.PORT)
    wwise.add_argument("--ip", default="0.0.0.0")
    wwise.add_argument("--waapi", default=None,
                       help="WAAPI url (default ws://127.0.0.1:8080/waapi)")
    wwise.add_argument("--map", action="append", default=[],
                       metavar="/osc/addr=RtpcName",
                       help="drive an RTPC straight from an address (repeatable)")
    wwise.add_argument("-v", "--verbose", action="store_true")
    wwise.set_defaults(run=cmd_wwise)

    arduino = subs.add_parser("arduino", help="Arduino serial onto the bus")
    arduino.add_argument("serial", help="e.g. COM5 or /dev/tty.usbmodem1101")
    arduino.add_argument("--baud", type=int, default=115200)
    arduino.add_argument("--host", default=contract.HOST)
    arduino.add_argument("--port", type=int, default=contract.PORT)
    arduino.add_argument("--scale", action="append", default=[],
                         metavar="name=preset",
                         help=f"presets: {', '.join(sorted(signal.PRESETS))}")
    arduino.add_argument("-v", "--verbose", action="store_true")
    arduino.set_defaults(run=cmd_arduino)

    radar = subs.add_parser("radar", help="XE125 radar onto the bus")
    radar.add_argument("serial", nargs="?", help="Enhanced COM port; guessed if omitted")
    radar.add_argument("--host", default=contract.HOST)
    radar.add_argument("--port", type=int, default=contract.PORT)
    radar.add_argument("--normalise", action="store_true",
                       help="map 0..40 cm onto 0..1")
    radar.add_argument("--median", type=int, metavar="N", help="spike rejection window")
    radar.add_argument("--smooth", type=float, metavar="TAU", help="seconds")
    radar.add_argument("--rate", type=float, metavar="HZ", help="cap the send rate")
    radar.add_argument("-v", "--verbose", action="store_true")
    radar.set_defaults(run=cmd_radar)

    forward = subs.add_parser("forward", help="mirror the bus to Pd, SC, Godot, a laptop")
    forward.add_argument("--to", action="append", required=True, metavar="HOST:PORT",
                         help="repeatable, to fan out across machines")
    forward.add_argument("--pattern", default="/*", help="address glob to forward")
    forward.add_argument("--rename", default=None, help="outgoing address")
    forward.add_argument("--lead", action="append", default=[], metavar="ARG",
                         help="prepend a fixed argument, repeatable. Renaming to "
                              "a Wwise verb needs one: --rename /wwise/rtpc "
                              "--lead Proximity")
    forward.add_argument("--take", type=int, default=None, metavar="N",
                         help="keep only the first N incoming arguments. "
                              "/sensor/radar carries <cm> <mag>, so crossing "
                              "into /wwise/rtpc wants --take 1")
    forward.add_argument("--scale", default=None,
                         help=f"presets: {', '.join(sorted(signal.PRESETS))}")
    forward.add_argument("--port", type=int, default=contract.PORT)
    forward.add_argument("--bind", default="0.0.0.0")
    forward.set_defaults(run=cmd_forward)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
