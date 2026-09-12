#!/usr/bin/env python3
"""XE125 radar -> OSC. Sends /sensor/radar <distance_cm> <magnitude> at the sweep rate.

    python xe125_to_osc.py [PORT] [--host 127.0.0.1] [--port 9000]

Pairs with wwise/osc2wwise.py --map /sensor/radar=Proximity

This is a wrapper kept so the documented command still works. The same thing,
plus smoothing and rate limiting, is `kitlib radar`. See kitlib/sources/radar.py.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from kitlib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["radar", *sys.argv[1:]]))
