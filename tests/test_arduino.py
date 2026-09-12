"""The Arduino serial source, against a fake port.

``pyserial`` is an optional extra, so the module imports it inside the function
that needs it. That is also what makes it substitutable here; the ``fake_serial``
fixture is in ``conftest.py``.
"""
from __future__ import annotations

import itertools

import pytest

from kitlib import signal
from kitlib.sources import arduino


class TestParse:
    @pytest.mark.parametrize("line,expected", [
        ("light 512\n", ("light", 512.0)),
        ("temp:21.5\n", ("temp", 21.5)),
        ("x = -3.25\r\n", ("x", -3.25)),
        ("  force   7  ", ("force", 7.0)),
        ("heart_rate 68", ("heart_rate", 68.0)),
        ("a3 100", ("a3", 100.0)),
    ])
    def test_it_reads_the_documented_shapes(self, line, expected):
        assert arduino.parse(line) == expected

    @pytest.mark.parametrize("line", [
        "", "\n", "Booting...", "a b c", "512", "3volts 5", "-name 5", "light abc",
    ])
    def test_it_ignores_anything_that_is_not_a_reading(self, line):
        """A sketch can print banners and debug text without corrupting the stream."""
        assert arduino.parse(line) is None


class TestReadings:
    def test_it_yields_name_value_pairs(self, fake_serial):
        fake_serial(["light 512\n", "temp 21.5\n", "junk\n", "force 7\n"])
        assert list(itertools.islice(arduino.readings("COM5"), 3)) == [
            ("light", 512.0), ("temp", 21.5), ("force", 7.0)]

    def test_it_opens_the_port_as_asked(self, fake_serial):
        fake_serial(["light 1\n"])
        next(arduino.readings("/dev/ttyACM0", baud=9600, timeout=2.0))
        assert fake_serial.log == {"device": "/dev/ttyACM0", "baud": 9600, "timeout": 2.0}

    def test_it_defaults_to_the_uno_r4_baud_rate(self, fake_serial):
        fake_serial(["light 1\n"])
        next(arduino.readings("COM5"))
        assert fake_serial.log["baud"] == 115200

    def test_the_port_is_closed_on_the_way_out(self, fake_serial):
        port = fake_serial(["light 1\n"])
        with pytest.raises(KeyboardInterrupt):
            list(arduino.readings("COM5"))
        assert port.closed


class TestRun:
    def test_each_reading_becomes_a_namespaced_sensor_message(
            self, fake_serial, listening, buses, collector):
        listening.on("/sensor/*", collector)
        fake_serial(["light 512\n", "temp 21.5\n"])
        arduino.run("COM5", bus=buses(port=listening.bound[1]))
        assert collector.wait_for(2)
        assert collector.addresses == ["/sensor/light", "/sensor/temp"]

    def test_a_named_stage_conditions_only_that_sensor(
            self, fake_serial, listening, buses, collector):
        listening.on("/sensor/*", collector)
        fake_serial(["force 650\n", "temp 21.5\n"])
        arduino.run("COM5", bus=buses(port=listening.bound[1]),
                    stages={"force": signal.FSR402})
        assert collector.wait_for(2)
        by_address = dict(collector.messages)
        assert by_address["/sensor/force"][0] == pytest.approx(1.0)
        assert by_address["/sensor/temp"][0] == pytest.approx(21.5, rel=1e-6)

    def test_a_stage_returning_none_sends_nothing(
            self, fake_serial, listening, buses, collector):
        listening.on("/sensor/*", collector)
        fake_serial(["light 500\n", "light 501\n", "light 900\n"])
        arduino.run("COM5", bus=buses(port=listening.bound[1]),
                    stages={"light": signal.Deadband(100)})
        assert collector.wait_for(2)
        collector.settle()
        assert len(collector) == 2

    def test_ctrl_c_ends_the_run_quietly(self, fake_serial, buses):
        fake_serial(["light 1\n"])
        arduino.run("COM5", bus=buses(port=1))  # returns rather than raising

    def test_verbose_echoes_what_it_sent(self, fake_serial, buses, capsys):
        fake_serial(["light 512\n"])
        arduino.run("COM5", bus=buses(port=1), verbose=True)
        assert "/sensor/light 512" in capsys.readouterr().out
