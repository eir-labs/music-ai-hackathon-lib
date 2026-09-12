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

    def test_the_namespaces_keep_their_published_names(self):
        assert contract.SENSOR_NS == "/sensor"
        assert contract.CHORD_NS == "/chord"
        assert contract.WWISE_NS == "/wwise"
        assert contract.MIDI_NS == "/midi"

    def test_every_namespace_is_either_published_or_consumed(self):
        """The distinction a team needs first: does sending here ask for something?"""
        assert contract.PUBLISHED_NS == (contract.SENSOR_NS, contract.CHORD_NS)
        assert contract.CONSUMED_NS == (contract.WWISE_NS, contract.MIDI_NS)
        assert not set(contract.PUBLISHED_NS) & set(contract.CONSUMED_NS)

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

    def test_every_spec_sits_in_one_of_the_published_namespaces(self):
        known = contract.PUBLISHED_NS + contract.CONSUMED_NS
        for address in contract.SPECS:
            assert address.startswith(known), f"{address} belongs to no namespace"

    def test_all_six_wwise_verbs_are_specified(self):
        assert set(contract.WWISE_SPECS) == {
            contract.EVENT, contract.RTPC, contract.SWITCH,
            contract.STATE, contract.POS, contract.STOP}

    def test_all_four_midi_verbs_are_specified(self):
        assert set(contract.MIDI_SPECS) == {
            contract.MIDI_NOTE, contract.MIDI_CHORD,
            contract.MIDI_CC, contract.MIDI_PANIC}

    def test_the_chord_source_publishes_notes_the_held_set_and_a_name(self):
        assert set(contract.CHORD_SPECS) == {
            contract.CHORD_NOTE, contract.CHORD_NOTES, contract.CHORD_NAME}

    def test_the_groups_together_are_the_whole_contract(self):
        """SPECS is what `kitlib contract` prints, so nothing may be left out."""
        assert set(contract.SPECS) == (
            set(contract.WWISE_SPECS) | set(contract.MIDI_SPECS)
            | set(contract.CHORD_SPECS))

    def test_no_address_is_claimed_by_two_groups(self):
        total = (len(contract.WWISE_SPECS) + len(contract.MIDI_SPECS)
                 + len(contract.CHORD_SPECS))
        assert len(contract.SPECS) == total

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
    def test_it_covers_every_namespace(self):
        text = contract.describe()
        for address in contract.SPECS:
            assert address in text
        assert contract.SENSOR_NS in text

    def test_it_says_which_way_each_address_points(self):
        text = contract.describe()
        assert "published by sources" in text
        assert "consumed by sinks" in text

    def test_the_columns_line_up(self):
        rows = [line for line in contract.describe().splitlines()
                if line.startswith("  ")]
        docs = ([spec.doc for spec in contract.CHORD_SPECS.values()]
                + ["a sensor reading"]
                + [spec.doc for spec in contract.WWISE_SPECS.values()]
                + [spec.doc for spec in contract.MIDI_SPECS.values()])
        assert len(rows) == len(docs)
        assert len({row.index(doc) for row, doc in zip(rows, docs)}) == 1

    def test_there_is_one_line_per_address_plus_the_sensor_namespace(self):
        rows = [line for line in contract.describe().splitlines()
                if line.startswith("  ")]
        assert len(rows) == len(contract.SPECS) + 1
