"""Shared fixtures.

Two ideas do most of the work here. A hand-cranked clock lets the time-based
stages be tested exactly, without sleeping. A collector plus a real UDP round
trip lets the bus be tested for what it actually does, rather than for what its
dispatcher was asked to do.
"""
from __future__ import annotations

import threading
import time
from typing import List, Tuple

import pytest

from kitlib.bus import Bus


class Clock:
    """A monotonic clock you advance by hand."""

    def __init__(self, now: float = 0.0):
        self.now = float(now)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


class Collector:
    """An OSC handler that records what arrived, safely across threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self.messages: List[Tuple[str, tuple]] = []

    def __call__(self, address: str, *args) -> None:
        with self._lock:
            self.messages.append((address, tuple(args)))

    def __len__(self) -> int:
        with self._lock:
            return len(self.messages)

    @property
    def addresses(self) -> List[str]:
        with self._lock:
            return [address for address, _ in self.messages]

    def wait_for(self, count: int, timeout: float = 2.0) -> bool:
        """Block until ``count`` messages have landed. False on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self) >= count:
                return True
            time.sleep(0.005)
        return len(self) >= count

    def settle(self, seconds: float = 0.25) -> None:
        """Give stray messages a chance to arrive, for 'nothing else came' checks."""
        time.sleep(seconds)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def collector() -> Collector:
    return Collector()


@pytest.fixture
def buses():
    """Factory for Buses that are closed on teardown.

    ``buses(listen_port=0)`` binds an OS-chosen port; read it back from
    ``bus.bound`` once the bus is serving.
    """
    made: List[Bus] = []

    def build(**kwargs) -> Bus:
        bus = Bus(**kwargs)
        made.append(bus)
        return bus

    yield build
    for bus in made:
        bus.close()


@pytest.fixture
def listening(buses):
    """A Bus already serving on an OS-chosen port."""
    bus = buses(listen_port=0)
    bus.start()
    return bus


@pytest.fixture
def sender(buses, listening):
    """A Bus pointed at whatever ``listening`` bound."""
    return buses(port=listening.bound[1])
