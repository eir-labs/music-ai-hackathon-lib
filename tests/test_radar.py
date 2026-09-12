"""The XE125 radar source, against a fake board.

The Acconeer SDK is an optional extra and no radar is plugged into CI, so both
it and ``pyserial`` are substituted here. The arithmetic under test is the bit
that matters: which bin reflected hardest, and how far away that is.
"""
from __future__ import annotations

import itertools
import sys
import types

import numpy as np
import pytest

from kitlib import signal
from kitlib.sources import radar


def frame_peaking_at(index: int, magnitude: float = 1.0, points: int = radar.POINTS):
    """One sweep of complex IQ data with its strongest reflection at ``index``."""
    sweep = np.full((1, points), 0.01 + 0j)
    sweep[0, index] = magnitude + 0j
    return sweep


@pytest.fixture
def fake_ports(monkeypatch):
    """Install a stand-in ``serial.tools.list_ports``."""
    def install(*descriptions):
        ports = [types.SimpleNamespace(device=f"COM{i}", description=text)
                 for i, text in enumerate(descriptions, start=3)]
        list_ports = types.ModuleType("serial.tools.list_ports")
        list_ports.comports = lambda: ports
        tools = types.ModuleType("serial.tools")
        tools.list_ports = list_ports
        monkeypatch.setitem(sys.modules, "serial.tools", tools)
        monkeypatch.setitem(sys.modules, "serial.tools.list_ports", list_ports)
    return install


@pytest.fixture
def fake_board(monkeypatch):
    """Install a stand-in ``acconeer.exptool`` and hand back the call log."""
    log = {"calls": []}

    def install(frames):
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

    install.log = log
    return install


class TestGeometry:
    def test_the_board_covers_forty_centimetres(self):
        assert radar.POINTS == 160
        assert radar.STEP_CM == 0.25
        assert radar.RANGE_CM == 40.0

    def test_it_publishes_on_the_documented_address(self):
        assert radar.ADDRESS == "/sensor/radar"


class TestFindPort:
    def test_it_picks_the_enhanced_port_not_the_standard_one(self, fake_ports):
        fake_ports("Silicon Labs Dual CP2105 ... Standard Com Port",
                   "Silicon Labs Dual CP2105 ... Enhanced Com Port")
        assert radar.find_port() == "COM3"  # matches on CP2105, both are the board

    def test_it_matches_an_enhanced_port_with_no_chip_name(self, fake_ports):
        fake_ports("Some other device", "Enhanced Com Port")
        assert radar.find_port() == "COM4"

    def test_it_returns_none_when_nothing_looks_like_the_board(self, fake_ports):
        fake_ports("Arduino UNO R4 Minima", "Bluetooth-Incoming-Port")
        assert radar.find_port() is None

    def test_a_port_with_no_description_does_not_crash_it(self, fake_ports):
        fake_ports(None, "Enhanced Com Port")
        assert radar.find_port() == "COM4"


class TestReadings:
    def test_the_peak_bin_becomes_a_distance_in_centimetres(self, fake_board):
        fake_board([frame_peaking_at(48, 0.9), frame_peaking_at(160 - 1, 0.4)])
        assert list(itertools.islice(radar.readings("COM3"), 2)) == [
            (12.0, pytest.approx(0.9)), (39.75, pytest.approx(0.4))]

    def test_a_reflection_at_the_sensor_reads_zero(self, fake_board):
        fake_board([frame_peaking_at(0, 1.0)])
        assert next(radar.readings("COM3"))[0] == 0.0

    def test_it_opens_the_port_it_was_given(self, fake_board):
        log = fake_board([frame_peaking_at(10)])
        next(radar.readings("/dev/tty.usbserial-x"))
        assert log["port"] == "/dev/tty.usbserial-x"

    def test_it_falls_back_to_the_guessed_port(self, fake_board, fake_ports):
        fake_ports("Enhanced Com Port")
        log = fake_board([frame_peaking_at(10)])
        next(radar.readings())
        assert log["port"] == "COM3"

    def test_the_session_is_closed_even_on_interrupt(self, fake_board):
        log = fake_board([frame_peaking_at(10)])
        with pytest.raises(KeyboardInterrupt):
            list(radar.readings("COM3"))
        assert log["calls"] == ["setup", "start", "stop", "close"]

    def test_no_board_gives_an_error_that_names_the_fix(self, fake_ports, fake_board):
        fake_ports("Arduino UNO R4 Minima")
        fake_board([])
        with pytest.raises(RuntimeError, match="XE125_Setup_Windows"):
            next(radar.readings())


class TestRun:
    def test_it_sends_distance_and_magnitude(
            self, fake_board, listening, buses, collector):
        listening.on("/sensor/radar", collector)
        fake_board([frame_peaking_at(48, 0.9)])
        radar.run(bus=buses(port=listening.bound[1]), port="COM3")
        assert collector.wait_for(1)
        distance, magnitude = collector.messages[0][1]
        assert distance == pytest.approx(12.0, rel=1e-6)
        assert magnitude == pytest.approx(0.9, rel=1e-6)

    def test_a_stage_conditions_the_distance_but_not_the_magnitude(
            self, fake_board, listening, buses, collector):
        """Magnitude is how you tell a real reflection from noise, so it stays raw."""
        listening.on("/sensor/radar", collector)
        fake_board([frame_peaking_at(80, 0.42)])
        radar.run(bus=buses(port=listening.bound[1]), port="COM3",
                  stage=signal.RADAR_CM)
        assert collector.wait_for(1)
        distance, magnitude = collector.messages[0][1]
        assert distance == pytest.approx(0.5, rel=1e-6)
        assert magnitude == pytest.approx(0.42, rel=1e-6)

    def test_a_dropped_sample_sends_nothing(
            self, fake_board, listening, buses, collector, clock):
        listening.on("/sensor/radar", collector)
        fake_board([frame_peaking_at(40)] * 5)
        radar.run(bus=buses(port=listening.bound[1]), port="COM3",
                  stage=signal.RateLimit(10, clock))
        assert collector.wait_for(1)
        collector.settle()
        assert len(collector) == 1

    def test_the_address_can_be_overridden(
            self, fake_board, listening, buses, collector):
        listening.on("/ch3/*", collector)
        fake_board([frame_peaking_at(20)])
        radar.run(bus=buses(port=listening.bound[1]), port="COM3",
                  address="/ch3/dashboard")
        assert collector.wait_for(1)
        assert collector.messages[0][0] == "/ch3/dashboard"

    def test_verbose_echoes_what_it_sent(self, fake_board, buses, capsys):
        fake_board([frame_peaking_at(48, 0.9)])
        radar.run(bus=buses(port=1), port="COM3", verbose=True)
        assert "/sensor/radar 12 0.9" in capsys.readouterr().out
