"""The ``kitlib`` command.

Most of this drives the subcommand functions directly. The monitor is the
exception: it is the tool a team reaches for when nothing is working, so it is
tested the way they will run it, as a process interrupted with Ctrl-C.
"""
from __future__ import annotations

import argparse
import ast
import inspect
import signal as signals
import socket
import subprocess
import sys
import time

import pytest

from kitlib import cli, contract
from kitlib.bus import Bus


#: The shortest argv that parses, per subcommand.
MINIMAL_ARGV = [
    ["contract"],
    ["monitor"],
    ["send", "/x", "1"],
    ["chord", "Cmaj7"],
    ["sweep"],
    ["echo", "nowhere.wav"],
    ["wwise", "--map", "/a=B"],
    ["arduino", "COM5"],
    ["radar"],
    ["midi"],
    ["play", "--map", "/a=C,Am"],
    ["forward", "--to", "host:9001"],
]


def reads_of_args(handler) -> set:
    """Every ``args.<name>`` the handler's own source reads."""
    tree = ast.parse(inspect.getsource(handler).lstrip())
    return {node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name) and node.value.id == "args"}


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TestHelpers:
    @pytest.mark.parametrize("text,expected", [
        ("5", 5), ("-3", -3), ("0.5", 0.5), ("-1.25", -1.25),
        ("Proximity", "Proximity"), ("", ""), ("1e3", 1000.0),
    ])
    def test_command_line_arguments_keep_their_type(self, text, expected):
        assert cli._number(text) == expected
        assert type(cli._number(text)) is type(expected)

    @pytest.mark.parametrize("value,expected", [
        (0.5, "0.5"), (1.0, "1"), (12.0, "12"), (3, "3"), ("X", "X"),
    ])
    def test_values_print_without_trailing_zeros(self, value, expected):
        assert cli._format(value) == expected

    @pytest.mark.parametrize("text,expected", [
        ("10.0.0.5:9001", ("10.0.0.5", 9001)),
        ("10.0.0.5", ("10.0.0.5", 9001)),
        (":9002", ("127.0.0.1", 9002)),
    ])
    def test_a_target_can_omit_the_port(self, text, expected):
        assert cli._host_port(text, contract.PORT + 1) == expected

    def test_an_unknown_preset_lists_the_real_ones(self):
        with pytest.raises(argparse.ArgumentTypeError, match="fsr402"):
            cli._preset("nonsense")

    def test_a_known_preset_comes_back(self):
        assert cli._preset("radar")(20) == pytest.approx(0.5)


class TestParser:
    def test_a_command_is_required(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args([])

    @pytest.mark.parametrize("argv", MINIMAL_ARGV)
    def test_every_subcommand_parses_and_binds_a_handler(self, argv):
        args = cli.build_parser().parse_args(argv)
        assert callable(args.run)

    def test_the_bus_port_is_the_default_everywhere(self):
        parse = cli.build_parser().parse_args
        for argv in (["monitor"], ["send", "/x"], ["wwise"], ["arduino", "COM5"],
                     ["radar"], ["forward", "--to", "h"]):
            assert parse(argv).port == contract.PORT

    def test_forward_requires_a_target(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["forward"])

    def test_repeatable_flags_accumulate(self):
        args = cli.build_parser().parse_args(
            ["forward", "--to", "a:1", "--to", "b:2"])
        assert args.to == ["a:1", "b:2"]

    @pytest.mark.parametrize("argv", MINIMAL_ARGV)
    def test_every_option_a_handler_reads_was_added_to_the_parser(self, argv):
        """A handler reading ``args.x`` that no ``add_argument`` defines.

        Nothing catches this until somebody runs the subcommand, because the
        handler is only reached with a real bus or a real serial port in front
        of it. At the event that means the failure surfaces at the worst moment,
        as an AttributeError from a command the docs told the team to run.
        """
        parsed = cli.build_parser().parse_args(argv)
        missing = sorted(reads_of_args(parsed.run) - set(vars(parsed)))
        assert not missing, (
            f"{parsed.run.__name__} reads {missing} but "
            f"'kitlib {argv[0]}' never parses it")


class TestContractCommand:
    def test_it_prints_the_whole_namespace(self, capsys):
        assert cli.main(["contract"]) == 0
        printed = capsys.readouterr().out
        for address in contract.SPECS:
            assert address in printed
        assert contract.SENSOR_NS in printed


class TestSendCommand:
    def test_it_puts_a_message_on_the_bus(self, listening, collector):
        listening.on("/wwise/rtpc", collector)
        assert cli.main(["send", "/wwise/rtpc", "Proximity", "0.5",
                         "--port", str(listening.bound[1])]) == 0
        assert collector.wait_for(1)
        assert collector.messages[0][1] == ("Proximity", pytest.approx(0.5))

    def test_an_address_with_no_arguments_is_fine(self, listening, collector):
        listening.on("/wwise/stop", collector)
        cli.main(["send", "/wwise/stop", "--port", str(listening.bound[1])])
        assert collector.wait_for(1)
        assert collector.messages[0][1] == ()

    def test_it_reports_where_it_sent(self, listening, capsys):
        cli.main(["send", "/x", "1", "--port", str(listening.bound[1])])
        assert f"127.0.0.1:{listening.bound[1]}" in capsys.readouterr().out


class TestChordCommand:
    """The one command a Ch6 team can run with nothing plugged in."""

    def test_it_prints_the_notes_and_the_numbers(self, capsys):
        assert cli.main(["chord", "Cmaj7"]) == 0
        printed = capsys.readouterr().out
        assert "C4 E4 G4 B4" in printed
        assert "60 64 67 71" in printed

    def test_the_octave_moves_it(self, capsys):
        cli.main(["chord", "C", "--octave", "3"])
        assert "C3 E3 G3" in capsys.readouterr().out

    def test_flats_are_available(self, capsys):
        cli.main(["chord", "Bb7", "--flats"])
        assert "Bb4 D5 F5 Ab5" in capsys.readouterr().out

    def test_a_name_nobody_recognises_fails_rather_than_guessing(self, capsys):
        assert cli.main(["chord", "Cwobble"]) == 2
        assert "unknown chord quality" in capsys.readouterr().err

    def test_it_can_put_the_chord_on_the_bus(self, listening, collector):
        listening.on(contract.MIDI_CHORD, collector)
        cli.main(["chord", "Am7", "--send", "--port", str(listening.bound[1])])
        assert collector.wait_for(1)
        assert collector.messages[0][1][0] == "Am7"


class TestMidiCommand:
    def test_listing_ports_needs_no_device(self, fake_midi, capsys):
        fake_midi(inputs=["ChordCat MIDI 1"], outputs=["IAC Driver Bus 1"])
        assert cli.main(["midi", "--list"]) == 0
        printed = capsys.readouterr().out
        assert "ChordCat MIDI 1" in printed
        assert "IAC Driver Bus 1" in printed

    def test_an_empty_list_says_so_rather_than_printing_nothing(
            self, fake_midi, capsys):
        fake_midi(inputs=[], outputs=[])
        cli.main(["midi", "--list"])
        assert "(none)" in capsys.readouterr().out

    def test_no_device_reports_rather_than_hangs(self, fake_midi, capsys):
        fake_midi(inputs=[])
        assert cli.main(["midi"]) == 1
        assert "kitlib midi --list" in capsys.readouterr().err


class TestPlayCommand:
    def test_a_malformed_map_is_rejected_before_opening_the_port(self, capsys):
        assert cli.main(["play", "--map", "/sensor/radar"]) == 2
        assert "want /osc/addr=C,Am,F,G" in capsys.readouterr().err

    def test_a_typo_in_the_progression_is_rejected_up_front(self, capsys):
        assert cli.main(["play", "--map", "/sensor/radar=C,Awobble"]) == 2
        assert "unknown chord quality" in capsys.readouterr().err

    def test_no_midi_output_reports_rather_than_hangs(self, fake_midi, capsys):
        fake_midi(outputs=[])
        assert cli.main(["play"]) == 1
        assert "MIDI output" in capsys.readouterr().err


class TestBadArguments:
    def test_a_malformed_map_is_rejected_before_touching_the_network(self, capsys):
        """A typo should read as a typo, not as a connection failure."""
        assert cli.main(["wwise", "--map", "no-equals-sign"]) == 2
        assert "want /osc/addr=RtpcName" in capsys.readouterr().err

    def test_a_malformed_scale_is_rejected_before_opening_the_port(self, capsys):
        assert cli.main(["arduino", "COM5", "--scale", "no-equals-sign"]) == 2
        assert "want name=preset" in capsys.readouterr().err

    def test_an_unreachable_wwise_reports_rather_than_hangs(self, capsys):
        port = free_port()
        assert cli.main(["wwise", "--waapi", f"ws://127.0.0.1:{port}/waapi"]) == 1
        assert "Nothing is listening" in capsys.readouterr().err


class TestMonitorCommand:
    """Run it the way a team will: as a process, ended with Ctrl-C."""

    def _run(self, argv, send=(), settle=0.6):
        process = subprocess.Popen(
            [sys.executable, "-m", "kitlib.cli", *argv],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(settle)
        for address, args in send:
            Bus(port=int(argv[argv.index("--port") + 1])).send(address, *args)
        time.sleep(0.4)
        process.send_signal(signals.SIGINT)
        return process.communicate(timeout=15)[0], process.wait()

    def test_it_prints_what_arrived_and_counts_it(self):
        port = free_port()
        out, code = self._run(
            ["monitor", "--port", str(port), "--max-hz", "0"],
            send=[("/sensor/light", (i,)) for i in range(5)]
                 + [("/wwise/rtpc", ("Proximity", 0.5))])
        assert code == 0
        assert "/sensor/light 4" in out
        assert "/wwise/rtpc Proximity 0.5" in out
        assert "Hz" in out
        summary = out.splitlines()[-2:]
        assert any("/sensor/light" in line and "5" in line for line in summary)

    def test_the_display_cap_thins_the_output_without_losing_the_count(self):
        """650 Hz of radar must not scroll the useful lines away."""
        port = free_port()
        out, _ = self._run(
            ["monitor", "--port", str(port), "--max-hz", "1"],
            send=[("/sensor/radar", (float(i),)) for i in range(40)])
        printed = out.count("/sensor/radar ")
        assert printed < 40
        assert any("40" in line for line in out.splitlines() if "/sensor/radar" in line)

    def test_an_empty_bus_says_so_and_fails(self):
        port = free_port()
        out, code = self._run(["monitor", "--port", str(port)])
        assert code == 1
        assert "Nothing arrived" in out
        assert str(port) in out
