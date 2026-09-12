"""The Wwise sink, against a fake WAAPI client.

No Wwise installation is involved. What is under test is the translation from
the six OSC verbs into the WAAPI calls Wwise expects, and the game-object
bookkeeping that has to happen before any of them will work.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
import types

import pytest

from kitlib import signal
from kitlib.sinks.wwise import CannotReachWwise, WwiseSink


class FakeClient:
    """Records calls; can be told to fail."""

    def __init__(self, fail=False, info=None):
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

    def disconnect(self):
        self.disconnected = True

    def uris(self):
        return [uri for uri, _ in self.calls]

    def wait_for(self, count, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(self.calls) < count:
            time.sleep(0.005)
        return len(self.calls) >= count


@pytest.fixture
def sink():
    return WwiseSink(FakeClient())


class TestGameObjects:
    def test_it_registers_an_object_before_first_use(self, sink):
        sink.event(None, "Play_Music")
        assert sink.client.calls[0] == (
            "ak.soundengine.registerGameObj", {"gameObject": 1, "name": "osc_1"})

    def test_it_registers_each_object_only_once(self, sink):
        for _ in range(3):
            sink.event(None, "Play_Music", 5)
        assert sink.client.uris().count("ak.soundengine.registerGameObj") == 1

    def test_the_default_object_is_one(self, sink):
        assert sink.game_object() == 1

    def test_a_float_from_osc_is_coerced_to_an_integer(self, sink):
        assert sink.game_object(7.0) == 7
        assert sink.game_object("9") == 9

    def test_different_objects_are_registered_separately(self, sink):
        sink.event(None, "A", 1)
        sink.event(None, "B", 2)
        assert sink.client.uris().count("ak.soundengine.registerGameObj") == 2


class TestVerbs:
    def test_event(self, sink):
        sink.event(None, "Play_Music", 3)
        assert sink.client.calls[-1] == (
            "ak.soundengine.postEvent", {"event": "Play_Music", "gameObject": 3})

    def test_rtpc_sends_a_float(self, sink):
        sink.rtpc(None, "Proximity", "0.25")
        assert sink.client.calls[-1] == (
            "ak.soundengine.setRTPCValue",
            {"rtpc": "Proximity", "value": 0.25, "gameObject": 1})

    def test_switch(self, sink):
        sink.switch(None, "Surface", "Snow", 2)
        assert sink.client.calls[-1] == (
            "ak.soundengine.setSwitch",
            {"switchGroup": "Surface", "switchState": "Snow", "gameObject": 2})

    def test_state_is_global_and_takes_no_game_object(self, sink):
        sink.state(None, "Weather", "Storm")
        assert sink.client.calls == [
            ("ak.soundengine.setState", {"stateGroup": "Weather", "state": "Storm"})]

    def test_position_carries_the_orientation_wwise_requires(self, sink):
        sink.position(None, 4, 1, 2, 3)
        uri, args = sink.client.calls[-1]
        assert uri == "ak.soundengine.setPosition"
        assert args["gameObject"] == 4
        assert args["position"]["position"] == {"x": 1.0, "y": 2.0, "z": 3.0}
        assert args["position"]["orientationFront"] == {"x": 0, "y": 0, "z": 1}
        assert args["position"]["orientationTop"] == {"x": 0, "y": 1, "z": 0}

    def test_stop(self, sink):
        sink.stop(None)
        assert sink.client.calls[-1] == (
            "ak.soundengine.stopAll", {"gameObject": 1})


class TestFailureHandling:
    def test_a_bad_call_does_not_kill_the_bridge(self, capsys):
        sink = WwiseSink(FakeClient(fail=True))
        sink.rtpc(None, "NoSuchRtpc", 1.0)
        sink.rtpc(None, "AlsoBad", 2.0)
        assert "WAAPI error" in capsys.readouterr().err

    def test_describe_connection_names_the_version(self, sink):
        assert sink.describe_connection() == "Wwise 2023.1.4"


class TestWiring:
    def test_attach_registers_every_verb(self, sink, listening, buses):
        sink.attach(listening)
        out = buses(port=listening.bound[1])
        out.send("/wwise/rtpc", "Proximity", 0.5)
        out.send("/wwise/event", "Play_Music")
        out.send("/wwise/state", "Weather", "Storm")
        out.send("/wwise/switch", "Surface", "Snow")
        out.send("/wwise/pos", 1, 0.0, 0.0, 0.0)
        out.send("/wwise/stop")
        assert sink.client.wait_for(7)  # six verbs plus one registration
        assert "ak.soundengine.setRTPCValue" in sink.client.uris()
        assert "ak.soundengine.setState" in sink.client.uris()
        assert "ak.soundengine.stopAll" in sink.client.uris()

    def test_attach_and_map_rtpc_are_chainable(self, sink, listening):
        assert sink.attach(listening).map_rtpc(listening, "/sensor/x", "X") is sink

    def test_close_disconnects(self, sink):
        sink.close()
        assert sink.client.disconnected

    def test_it_works_as_a_context_manager(self):
        client = FakeClient()
        with WwiseSink(client):
            pass
        assert client.disconnected


class TestMapRtpc:
    def test_it_drives_an_rtpc_straight_from_a_sensor(self, sink, listening, buses):
        sink.map_rtpc(listening, "/sensor/radar", "Proximity")
        buses(port=listening.bound[1]).send("/sensor/radar", 0.25, 0.9)
        assert sink.client.wait_for(2)
        uri, args = sink.client.calls[-1]
        assert uri == "ak.soundengine.setRTPCValue"
        assert args["rtpc"] == "Proximity"
        assert args["value"] == pytest.approx(0.25, rel=1e-6)

    def test_a_stage_conditions_the_value_on_the_way(self, sink, listening, buses):
        sink.map_rtpc(listening, "/sensor/radar", "Proximity", stage=signal.RADAR_CM)
        buses(port=listening.bound[1]).send("/sensor/radar", 20.0, 0.9)
        assert sink.client.wait_for(2)
        assert sink.client.calls[-1][1]["value"] == pytest.approx(0.5, rel=1e-6)

    def test_a_dropped_sample_makes_no_waapi_call(self, sink, listening, buses):
        sink.map_rtpc(listening, "/sensor/radar", "Proximity",
                      stage=signal.Deadband(100))
        out = buses(port=listening.bound[1])
        out.send("/sensor/radar", 10.0)
        out.send("/sensor/radar", 11.0)
        assert sink.client.wait_for(2)
        time.sleep(0.25)
        assert sink.client.uris().count("ak.soundengine.setRTPCValue") == 1

    def test_a_message_with_no_arguments_is_ignored(self, sink, listening, buses):
        sink.map_rtpc(listening, "/sensor/radar", "Proximity")
        buses(port=listening.bound[1]).send("/sensor/radar")
        time.sleep(0.25)
        assert sink.client.calls == []


def free_url() -> str:
    """A url whose port nothing is listening on."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return f"ws://127.0.0.1:{port}/waapi"


@pytest.fixture
def occupied_url():
    """A url whose port something is listening on, but not Wwise."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    yield f"ws://127.0.0.1:{server.getsockname()[1]}/waapi"
    server.close()


@pytest.fixture
def fake_waapi(monkeypatch):
    """Install a stand-in ``waapi`` that connects, refuses, or hangs."""
    class Refused(Exception):
        pass

    def install(behaviour):
        def WaapiClient(url=None):
            if behaviour == "refuse":
                raise Refused("connection refused")
            if behaviour == "hang":
                threading.Event().wait(5)
            return FakeClient()

        module = types.ModuleType("waapi")
        module.CannotConnectToWaapiException = Refused
        module.WaapiClient = WaapiClient
        monkeypatch.setitem(sys.modules, "waapi", module)

    return install


class TestConnect:
    """The library blocks forever on a failed handshake, so this is bounded."""

    def test_an_open_port_and_a_willing_server_gives_a_sink(
            self, occupied_url, fake_waapi):
        fake_waapi("connect")
        sink = WwiseSink.connect(occupied_url, timeout=2.0)
        assert isinstance(sink, WwiseSink)

    def test_a_closed_port_is_diagnosed_immediately(self, fake_waapi):
        fake_waapi("connect")
        started = time.monotonic()
        with pytest.raises(CannotReachWwise, match="Nothing is listening"):
            WwiseSink.connect(free_url(), timeout=10.0)
        assert time.monotonic() - started < 3.0

    def test_a_closed_port_message_names_the_three_usual_causes(self, fake_waapi):
        fake_waapi("connect")
        with pytest.raises(CannotReachWwise, match="Authoring API"):
            WwiseSink.connect(free_url())

    def test_a_refusal_is_reported_rather_than_raised_raw(
            self, occupied_url, fake_waapi):
        fake_waapi("refuse")
        with pytest.raises(CannotReachWwise, match="refused the connection"):
            WwiseSink.connect(occupied_url, timeout=2.0)

    def test_an_unrelated_server_on_the_port_times_out_instead_of_hanging(
            self, occupied_url, fake_waapi):
        """Port 8080 is popular. A dev server there must not freeze the bridge."""
        fake_waapi("hang")
        started = time.monotonic()
        with pytest.raises(CannotReachWwise, match="did not answer as Wwise"):
            WwiseSink.connect(occupied_url, timeout=0.3)
        assert time.monotonic() - started < 2.0

    def test_the_default_endpoint_is_the_documented_one(self):
        from kitlib.sinks.wwise import DEFAULT_WAAPI_URL, _endpoint
        assert DEFAULT_WAAPI_URL == "ws://127.0.0.1:8080/waapi"
        assert _endpoint(None) == ("127.0.0.1", 8080)

    @pytest.mark.parametrize("url,expected", [
        ("ws://10.0.0.5:9090/waapi", ("10.0.0.5", 9090)),
        ("ws://localhost:8080/waapi", ("localhost", 8080)),
        ("ws://127.0.0.1/waapi", ("127.0.0.1", 8080)),
    ])
    def test_a_custom_url_is_parsed_for_the_probe(self, url, expected):
        from kitlib.sinks.wwise import _endpoint
        assert _endpoint(url) == expected
