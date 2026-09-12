#!/usr/bin/env python3
"""Print the strongest radar reflection distance from an Acconeer XE125.

    python xe125_peak.py [PORT]

Smoke test. Move your hand in front of the sensor and watch the number change.
Close the Exploration Tool first, only one process can hold the port.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from kitlib.sources import radar  # noqa: E402


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        for centimetres, magnitude in radar.readings(port):
            print(f"\r~ {centimetres:5.1f} cm   (mag {magnitude:.3g})", end="", flush=True)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
