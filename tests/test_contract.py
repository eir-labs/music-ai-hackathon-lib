"""The shared address namespace.

This is the one thing six teams agree on, so the tests here are less about
logic than about pinning the agreement down. If one of these fails, somebody's
patch is already running against a different contract.
"""
from __future__ import annotations

import pytest

from kitlib import contract


class TestTheAgreement:
    def test_the_bus_is_udp_9000_on_the_local_machine(self):
        assert contract.PORT == 9000
        assert contract.HOST == "127.0.0.1"

    def test_there_are_exactly_two_shared_namespaces(self):
        assert contract.SENSOR_NS == "/sensor"
        assert contract.WWISE_NS == "/wwise"

    @pytest.mark.parametrize("name,address", [
        ("EVENT", "/wwise/event"), ("RTPC", "/wwise/rtpc"),
        ("SWITCH", "/wwise/switch"), ("STATE", "/wwise/state"),
        ("POS", "/wwise/pos"), ("STOP", "/wwise/stop"),
    ])
    def test_each_verb_keeps_its_published_address(self, name, address):
        assert getattr(contract, name) == address


class TestSensorAddresses:
    @pytest.mark.parametrize("name,address", [
        ("radar", "/sensor/radar"),
        ("heart_rate", "/sensor/heart_rate"),
        ("a3", "/sensor/a3"),
    ])
    def test_a_name_becomes_a_namespaced_address(self, name, address):
        assert contract.sensor(name) == address

    @pytest.mark.parametrize("bad", [
        "", "two words", "slash/es", "dot.ted", "dash-ed", "semi;colon", " ",
    ])
    def test_names_that_would_break_pd_or_supercollider_are_rejected(self, bad):
        """These travel on to Pd receive names and SC symbols unchanged."""
        with pytest.raises(ValueError):
            contract.sensor(bad)

    def test_the_error_says_what_is_allowed(self):
        with pytest.raises(ValueError, match="alphanumeric or underscore"):
            contract.sensor("no-dashes")


class TestSpecs:
    def test_every_spec_is_filed_under_its_own_address(self):
        for address, spec in contract.SPECS.items():
            assert spec.address == address

    def test_every_spec_is_a_wwise_verb(self):
        for address in contract.SPECS:
            assert address.startswith(contract.WWISE_NS)

    def test_all_six_verbs_are_specified(self):
        assert set(contract.SPECS) == {
            contract.EVENT, contract.RTPC, contract.SWITCH,
            contract.STATE, contract.POS, contract.STOP}

    def test_a_spec_prints_as_its_calling_shape(self):
        assert str(contract.SPECS[contract.RTPC]) == (
            "/wwise/rtpc <RtpcName> <float> <gameObj?>")

    def test_optional_arguments_are_marked_with_a_question_mark(self):
        assert contract.SPECS[contract.STOP].args == ("gameObj?",)
        assert "?" not in "".join(contract.SPECS[contract.POS].args)

    def test_specs_are_frozen_so_nobody_edits_the_contract_at_runtime(self):
        with pytest.raises(Exception):
            contract.SPECS[contract.RTPC].address = "/somewhere/else"

    def test_every_spec_carries_a_description(self):
        for spec in contract.SPECS.values():
            assert spec.doc and spec.doc[0].islower()


class TestDescribe:
    def test_it_covers_both_namespaces(self):
        text = contract.describe()
        for address in contract.SPECS:
            assert address in text
        assert contract.SENSOR_NS in text

    def test_the_columns_line_up(self):
        lines = contract.describe().splitlines()
        docs = [spec.doc for spec in contract.SPECS.values()] + ["a sensor reading"]
        assert len({line.index(doc) for line, doc in zip(lines, docs)}) == 1

    def test_there_is_one_line_per_address_plus_the_sensor_namespace(self):
        assert len(contract.describe().splitlines()) == len(contract.SPECS) + 1
