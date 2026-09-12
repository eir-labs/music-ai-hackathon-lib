"""Wwise as a bus sink, over the Wwise Authoring API.

Anything that speaks OSC drives Wwise events and game parameters, with no game
engine in the loop. Wwise must be running with a project open and
**Project > User Preferences > Enable Wwise Authoring API** ticked.

Game objects are integers you invent. The sink registers each one the first
time it sees it, and defaults to 1.

Needs ``pip install kitlib[wwise]``.
"""
from __future__ import annotations

import socket
import sys
import threading
from typing import Optional, Tuple
from urllib.parse import urlparse

from ..bus import Bus
from ..contract import EVENT, POS, RTPC, STATE, STOP, SWITCH
from ..signal import Stage

DEFAULT_GAME_OBJECT = 1
DEFAULT_WAAPI_URL = "ws://127.0.0.1:8080/waapi"

#: Seconds to spend deciding whether anything is listening at all.
PROBE_TIMEOUT = 2.0
#: Seconds to wait for a WAMP handshake before giving up on it. See ``connect``.
CONNECT_TIMEOUT = 10.0


class CannotReachWwise(RuntimeError):
    """Raised with the three things that are usually wrong."""


def _endpoint(url: Optional[str]) -> Tuple[str, int]:
    parsed = urlparse(url or DEFAULT_WAAPI_URL)
    return parsed.hostname or "127.0.0.1", parsed.port or 8080


def _probe(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> None:
    """Fail fast if nothing is listening on the WAAPI port."""
    try:
        socket.create_connection((host, port), timeout=timeout).close()
    except OSError as exc:
        raise CannotReachWwise(
            f"Nothing is listening on {host}:{port}. Is Wwise running, is a "
            f"project open, and is Enable Wwise Authoring API ticked in "
            f"Project > User Preferences?") from exc


class WwiseSink:
    """Translates the ``/wwise/*`` verbs into WAAPI calls."""

    def __init__(self, client, verbose: bool = False):
        self.client = client
        self.verbose = verbose
        self._registered = set()

    @classmethod
    def connect(cls, url: Optional[str] = None, verbose: bool = False,
                timeout: float = CONNECT_TIMEOUT) -> "WwiseSink":
        """Open a WAAPI connection, or explain why it cannot be opened.

        ``waapi-client`` blocks indefinitely when the handshake does not
        complete, and it does not complete when Wwise is closed or when some
        unrelated server happens to hold port 8080. Either way a team is left
        staring at a frozen terminal, so the wait is bounded here and the
        diagnosis names what was actually found.
        """
        from waapi import CannotConnectToWaapiException, WaapiClient

        host, port = _endpoint(url)
        _probe(host, port)

        opened, failed = {}, {}

        def open_connection():
            try:
                opened["client"] = WaapiClient(url)
            except BaseException as exc:  # the library raises broadly
                failed["error"] = exc

        worker = threading.Thread(target=open_connection, daemon=True,
                                  name="kitlib-waapi-connect")
        worker.start()
        worker.join(timeout)

        if "client" in opened:
            return cls(opened["client"], verbose)
        if "error" in failed:
            error = failed["error"]
            raise CannotReachWwise(
                f"Wwise refused the connection on {host}:{port}: {error}. Is a "
                f"project open, and is Enable Wwise Authoring API ticked in "
                f"Project > User Preferences?") from error
        raise CannotReachWwise(
            f"Something is listening on {host}:{port} but it did not answer as "
            f"Wwise within {timeout:g}s. Check that the port belongs to Wwise "
            f"and not another server, or pass --waapi with the right url.")

    def describe_connection(self) -> str:
        info = self.client.call("ak.wwise.core.getInfo")
        return f"{info['displayName']} {info['version']['displayName']}"

    # -- WAAPI plumbing --------------------------------------------------

    def call(self, uri: str, args: dict):
        if self.verbose:
            print(uri, args)
        try:
            return self.client.call(uri, args)
        except Exception as exc:  # a bad RTPC name should not kill the bridge
            print("WAAPI error:", uri, args, exc, file=sys.stderr)

    def game_object(self, value=None) -> int:
        """Coerce to an int and register it with the sound engine on first use."""
        number = DEFAULT_GAME_OBJECT if value is None else int(value)
        if number not in self._registered:
            self.call("ak.soundengine.registerGameObj",
                      {"gameObject": number, "name": f"osc_{number}"})
            self._registered.add(number)
        return number

    # -- the verbs -------------------------------------------------------

    def event(self, _address, name, game_object=None) -> None:
        self.call("ak.soundengine.postEvent",
                  {"event": str(name), "gameObject": self.game_object(game_object)})

    def rtpc(self, _address, name, value, game_object=None) -> None:
        self.call("ak.soundengine.setRTPCValue",
                  {"rtpc": str(name), "value": float(value),
                   "gameObject": self.game_object(game_object)})

    def switch(self, _address, group, state, game_object=None) -> None:
        self.call("ak.soundengine.setSwitch",
                  {"switchGroup": str(group), "switchState": str(state),
                   "gameObject": self.game_object(game_object)})

    def state(self, _address, group, state) -> None:
        self.call("ak.soundengine.setState",
                  {"stateGroup": str(group), "state": str(state)})

    def position(self, _address, game_object, x, y, z) -> None:
        self.call("ak.soundengine.setPosition", {
            "gameObject": self.game_object(game_object),
            "position": {"orientationFront": {"x": 0, "y": 0, "z": 1},
                         "orientationTop": {"x": 0, "y": 1, "z": 0},
                         "position": {"x": float(x), "y": float(y), "z": float(z)}}})

    def stop(self, _address, game_object=None) -> None:
        self.call("ak.soundengine.stopAll",
                  {"gameObject": self.game_object(game_object)})

    # -- wiring ----------------------------------------------------------

    def attach(self, bus: Bus) -> "WwiseSink":
        """Register every ``/wwise/*`` verb on the bus."""
        for address, handler in ((EVENT, self.event), (RTPC, self.rtpc),
                                 (SWITCH, self.switch), (STATE, self.state),
                                 (POS, self.position), (STOP, self.stop)):
            bus.on(address, handler)
        return self

    def map_rtpc(self, bus: Bus, address: str, rtpc: str,
                 stage: Optional[Stage] = None) -> "WwiseSink":
        """Drive one RTPC straight from a sensor address, skipping the verbs.

        Takes the first argument of whatever arrives, so ``/sensor/radar`` with
        its ``<cm> <magnitude>`` pair feeds the distance and ignores the rest.
        """
        def handle(_address, *values):
            if not values:
                return
            value = values[0]
            if stage is not None:
                value = stage(value)
                if value is None:
                    return
            self.rtpc(None, rtpc, value)

        bus.on(address, handle)
        return self

    def close(self) -> None:
        self.client.disconnect()

    def __enter__(self) -> "WwiseSink":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
