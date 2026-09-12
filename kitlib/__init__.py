"""kitlib — shared OSC runtime for the Music & AI Hackathon 2026.

Everything at the event talks OSC on UDP 9000 so tracks can borrow from each
other. This package is that bus, the signal conditioning around it, and the
adapters at either end.

    from kitlib import Bus, signal

    bus = Bus()
    prox = signal.RADAR_CM >> signal.Smooth(0.15) >> signal.RateLimit(60)
    bus.send("/wwise/rtpc", "Proximity", prox(12.3))

The address namespace lives in ``kitlib.contract`` and nowhere else. Run
``kitlib contract`` to print it, ``kitlib monitor`` to watch the bus.
"""
from . import contract, signal
from .bus import Bus
from .contract import HOST, PORT, sensor

__version__ = "0.1.0"
__all__ = ["Bus", "contract", "signal", "sensor", "HOST", "PORT", "__version__"]
