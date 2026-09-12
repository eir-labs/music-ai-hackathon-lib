"""Stand-ins for the three things the tests cannot plug in.

No Arduino, no radar board and no Wwise installation exists in CI, and none
exists on most of the laptops at the event either. Each of those arrives
through an optional extra that its module imports late, inside the function
that needs it, which is exactly what makes it substitutable here.

One copy of each double lives here so the per-component tests and the
integration tests agree about what the hardware does. Install them through the
fixtures in ``conftest.py`` rather than reaching in directly.
"""
from __future__ import annotations

import sys
import time
import types
from typing import Iterable

import numpy as np

from kitlib.sources import radar


# -- Wwise ---------------------------------------------------------------

class FakeClient:
    """A WAAPI client that records calls instead of making them.

    ``fail`` makes every call raise, which is how a bad RTPC name behaves: the
    bridge is expected to report it and keep running.
    """

    def __init__(self, fail: bool = False, info=None):
        self.calls = []
        self.fail = fail
        self.disconnected = False
        self.info = info or {"displayName": "Wwise",
                             "version": {"displayName": "2023.1.4"}}

    def call(self, uri, args=None):
        if uri == "ak.wwise.core.getInfo":
            return self.info
        self.calls.append((uri, args))
        if self.fail:
            raise RuntimeError("boom")
        return {}

    def disconnect(self) -> None:
        self.disconnected = True

    # -- reading the log ------------------------------------------------

    def uris(self):
        return [uri for uri, _ in self.calls]

    def of(self, uri: str):
        """Just the arguments of the calls made to ``uri``, in order."""
        return [args for made, args in self.calls if made == uri]

    def wait_for(self, count: int, timeout: float = 2.0) -> bool:
        """Block until ``count`` calls in total have been made. False on timeout.

        Messages cross a real UDP socket and land on a server thread, so an
        assertion made too early sees an empty log rather than a failure.

        Prefer ``wait_for_of`` when you know which call you are waiting for.
        A total is easy to get wrong, because registering a game object is a
        call too and happens only the first time an object is mentioned.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(self.calls) < count:
            time.sleep(0.005)
        return len(self.calls) >= count

    def wait_for_of(self, uri: str, count: int = 1, timeout: float = 2.0) -> bool:
        """Block until ``uri`` has been called ``count`` times. False on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(self.of(uri)) < count:
            time.sleep(0.005)
        return len(self.of(uri)) >= count

    def settle(self, seconds: float = 0.25) -> None:
        """Give stray calls a chance to arrive, for 'nothing else came' checks."""
        time.sleep(seconds)


# -- Arduino -------------------------------------------------------------

class FakePort:
    """A serial port that replays canned lines, then looks like Ctrl-C."""

    def __init__(self, lines: Iterable[bytes], log: dict):
        self._lines = iter(lines)
        self.log = log
        self.closed = False

    def __enter__(self) -> "FakePort":
        return self

    def __exit__(self, *exc) -> None:
        self.closed = True

    def readline(self) -> bytes:
        try:
            return next(self._lines)
        except StopIteration:
            raise KeyboardInterrupt  # what a user pressing Ctrl-C looks like


def install_serial(monkeypatch, lines, log: dict) -> FakePort:
    """Put a stand-in ``serial`` module in front of ``import serial``."""
    encoded = [line if isinstance(line, bytes) else line.encode() for line in lines]
    port = FakePort(encoded, log)

    def Serial(device, baud, timeout=None):
        log.update(device=device, baud=baud, timeout=timeout)
        return port

    module = types.ModuleType("serial")
    module.Serial = Serial
    monkeypatch.setitem(sys.modules, "serial", module)
    return port


def install_list_ports(monkeypatch, *descriptions) -> None:
    """Put a stand-in ``serial.tools.list_ports`` in front of the port scan."""
    ports = [types.SimpleNamespace(device=f"COM{i}", description=text)
             for i, text in enumerate(descriptions, start=3)]
    list_ports = types.ModuleType("serial.tools.list_ports")
    list_ports.comports = lambda: ports
    tools = types.ModuleType("serial.tools")
    tools.list_ports = list_ports
    monkeypatch.setitem(sys.modules, "serial.tools", tools)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", list_ports)


# -- XE125 radar ---------------------------------------------------------

def frame_peaking_at(index: int, magnitude: float = 1.0,
                     points: int = radar.POINTS):
    """One sweep of complex IQ data with its strongest reflection at ``index``.

    Index times ``radar.STEP_CM`` is the distance the source should report, so
    a test states the centimetres it wants and reads them back out.
    """
    sweep = np.full((1, points), 0.01 + 0j)
    sweep[0, index] = magnitude + 0j
    return sweep


def frame_at_cm(centimetres: float, magnitude: float = 1.0):
    """The sweep a reflector at ``centimetres`` would produce."""
    return frame_peaking_at(int(round(centimetres / radar.STEP_CM)), magnitude)


def install_acconeer(monkeypatch, frames, log: dict) -> dict:
    """Put a stand-in ``acconeer.exptool`` in front of the SDK import."""
    stream = iter(frames)

    class Client:
        @staticmethod
        def open(serial_port=None):
            log["port"] = serial_port
            return Client()

        def setup_session(self, config):
            log["calls"].append("setup")

        def start_session(self):
            log["calls"].append("start")

        def get_next(self):
            try:
                return types.SimpleNamespace(frame=next(stream))
            except StopIteration:
                raise KeyboardInterrupt

        def stop_session(self):
            log["calls"].append("stop")

        def close(self):
            log["calls"].append("close")

    a121 = types.SimpleNamespace(
        Client=Client,
        SessionConfig=lambda spec: ("session", spec),
        SensorConfig=lambda: "sensor")
    exptool = types.ModuleType("acconeer.exptool")
    exptool.a121 = a121
    monkeypatch.setitem(sys.modules, "acconeer.exptool", exptool)
    return log


# -- MIDI ----------------------------------------------------------------

class Message:
    """A stand-in for ``mido.Message``, which is just named fields.

    Constructing one validates nothing, deliberately. The real library raises
    on an out-of-range note, and the sink is supposed to report that and keep
    running rather than die, so a test needs to be able to provoke it.
    """

    def __init__(self, type, **fields):
        self.type = type
        self.note = fields.get("note")
        self.velocity = fields.get("velocity")
        self.control = fields.get("control")
        self.value = fields.get("value")
        self.channel = fields.get("channel")
        self.fields = fields

    def __eq__(self, other):
        return (isinstance(other, Message) and self.type == other.type
                and self.fields == other.fields)

    def __repr__(self):
        inner = ", ".join(f"{k}={v!r}" for k, v in self.fields.items())
        return f"Message({self.type!r}, {inner})"


def note_on(note, velocity=100, channel=0) -> Message:
    return Message("note_on", note=note, velocity=velocity, channel=channel)


def note_off(note, channel=0) -> Message:
    return Message("note_off", note=note, velocity=0, channel=channel)


class FakeMidiInput:
    """A MIDI input that replays canned messages, then looks like Ctrl-C."""

    def __init__(self, incoming):
        self._incoming = list(incoming)
        self.closed = False

    def __enter__(self) -> "FakeMidiInput":
        return self

    def __exit__(self, *exc) -> None:
        self.closed = True

    def __iter__(self):
        yield from self._incoming
        raise KeyboardInterrupt  # what a user pressing Ctrl-C looks like


class FakeMidiOutput:
    """A MIDI output that records what was sent; can be told to fail."""

    def __init__(self, fail: bool = False):
        self.sent = []
        self.fail = fail
        self.closed = False

    def send(self, message) -> None:
        if self.fail:
            raise ValueError("data byte must be in range 0..127")
        self.sent.append(message)

    def close(self) -> None:
        self.closed = True

    def wait_for(self, count: int = 1, timeout: float = 2.0) -> bool:
        """Block until ``count`` messages have been sent. False on timeout.

        Messages reach this port across a real UDP socket and a server thread
        whenever a bus is in front of it, so asserting too early sees nothing.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(self.sent) < count:
            time.sleep(0.005)
        return len(self.sent) >= count

    def settle(self, seconds: float = 0.25) -> None:
        """Give stray messages a chance to arrive, for 'nothing else came' checks."""
        time.sleep(seconds)

    def of(self, kind: str):
        """Just the messages of one type, in order."""
        return [m for m in self.sent if m.type == kind]

    def notes_on(self):
        return [m.note for m in self.sent if m.type == "note_on" and m.velocity]

    def notes_off(self):
        return [m.note for m in self.sent
                if m.type == "note_off" or (m.type == "note_on" and not m.velocity)]


def install_mido(monkeypatch, incoming=(), inputs=("ChordCat MIDI 1",),
                 outputs=("ChordCat MIDI 1",), fail: bool = False):
    """Put a stand-in ``mido`` in front of the import. Returns the output port."""
    output = FakeMidiOutput(fail=fail)
    opened = {"input": None}

    def open_input(name=None):
        opened["input"] = name
        return FakeMidiInput(incoming)

    module = types.ModuleType("mido")
    module.Message = Message
    module.get_input_names = lambda: list(inputs)
    module.get_output_names = lambda: list(outputs)
    module.open_input = open_input
    module.open_output = lambda name=None: output
    monkeypatch.setitem(sys.modules, "mido", module)

    output.opened = opened
    return output
