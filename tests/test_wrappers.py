"""The original scripts still answer to their documented commands.

Teams are following READMEs that say `python osc2wwise.py --map ...`. Those
invocations now route through kitlib, and these tests are what stops a
refactor from quietly breaking a command somebody is mid-demo with.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(script: str, *args, timeout: float = 30.0):
    return subprocess.run([sys.executable, str(ROOT / script), *args],
                          capture_output=True, text=True, timeout=timeout)


class TestDocumentedFlags:
    @pytest.mark.parametrize("script,flags", [
        ("wwise/osc2wwise.py", ["--port", "--ip", "--waapi", "--map", "-v"]),
        ("sensors/xe125_to_osc.py", ["--host", "--port"]),
        ("sensors/arduino_serial_to_osc.py", ["--baud", "--host", "--port"]),
    ])
    def test_every_flag_the_readme_promises_is_still_accepted(self, script, flags):
        result = run(script, "--help")
        assert result.returncode == 0, result.stderr
        for flag in flags:
            assert flag in result.stdout, f"{script} no longer offers {flag}"

    def test_the_radar_bridge_still_takes_an_optional_port_argument(self):
        result = run("sensors/xe125_to_osc.py", "--help")
        assert "[serial]" in result.stdout


class TestBehaviour:
    def test_the_smoke_test_explains_a_missing_board(self):
        result = run("sensors/xe125_peak.py")
        assert result.returncode == 1
        assert "No XE125 found" in result.stderr
        assert "XE125_Setup_Windows.md" in result.stderr

    def test_a_malformed_map_is_still_rejected_the_same_way(self):
        """And without waiting on Wwise, which is what used to hang here."""
        result = run("wwise/osc2wwise.py", "--map", "no-equals-sign", timeout=15.0)
        assert result.returncode == 2
        assert "want /osc/addr=RtpcName" in result.stderr

    @pytest.mark.parametrize("script", [
        "wwise/osc2wwise.py", "sensors/xe125_to_osc.py",
        "sensors/arduino_serial_to_osc.py", "sensors/xe125_peak.py",
    ])
    def test_each_script_finds_kitlib_without_being_installed_first(self, script):
        """The path shim at the top of each wrapper, which a bare clone relies on."""
        source = (ROOT / script).read_text()
        assert "sys.path.insert" in source
        assert "import kitlib" in source or "from kitlib" in source
