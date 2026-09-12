"""The MIDI source and sink, against a fake port.

``mido`` is an optional extra imported inside the functions that need it, so no
MIDI library and no ChordCat are involved here. What is under test is the part
that is easy to get wrong by hand: which messages mean a key went up, what a
set of held notes spells, and the channel numbering that hardware and the wire
disagree about.
"""
from __future__ import annotations

import pytest

from doubles import note_off, note_on
from kitlib import chords, contract
from kitlib.sinks.midi import CannotReachMidi, MidiSink
from kitlib.sources import midi


def chord_notes(name: str) -> list:
    return chords.spell(name)


# -- source --------------------------------------------------------------

class TestFindingThePort:
    def test_it_picks_the_port_that_looks_like_the_chordcat(self, fake_midi):
        fake_midi(inputs=["IAC Driver Bus 1", "ChordCat MIDI 1", "Launchpad"])
        assert midi.find_port() == "ChordCat MIDI 1"

    def test_the_match_ignores_case_and_spacing(self):
        assert midi.find_port(["chord cat 1"]) == "chord cat 1"
        assert midi.find_port(["AlphaTheta Device"]) == "AlphaTheta Device"

    def test_nothing_recognisable_is_a_miss_not_a_wrong_guess(self):
        """Connecting to whatever happened to be first would be worse than failing."""
        assert midi.find_port(["IAC Driver Bus 1", "Launchpad"]) is None

    def test_opening_with_nothing_plugged_in_says_what_to_run(self, fake_midi):
        fake_midi(inputs=[])
        with pytest.raises(RuntimeError, match="kitlib midi --list"):
            midi.open_input()


class TestHeldNotes:
    def test_a_key_down_adds_a_note(self):
        assert midi.held_after(note_on(60), set()) == {60}

    def test_a_key_up_removes_it(self):
        assert midi.held_after(note_off(60), {60, 64}) == {64}

    def test_a_key_down_at_velocity_zero_is_a_key_up(self):
        """Hardware and sequencers both send releases this way.

        Reading it as a key-down leaves every note held forever, which sounds
        like the instrument has jammed and is the first thing to suspect when
        it does.
        """
        assert midi.held_after(note_on(60, velocity=0), {60, 64}) == {64}

    def test_releasing_something_never_held_is_harmless(self):
        assert midi.held_after(note_off(99), {60}) == {60}

    def test_anything_that_is_not_a_key_is_ignored(self):
        from doubles import Message
        held = {60}
        assert midi.held_after(Message("control_change", control=1, value=64), held) \
            == held


class TestPublishing:
    def test_a_chord_played_one_key_at_a_time_ends_up_named(
            self, fake_midi, listening, collector, buses):
        listening.on("/chord/*", collector)
        fake_midi(incoming=[note_on(60), note_on(64), note_on(67)])

        midi.run(bus=buses(port=listening.bound[1]))

        # Three keys, each publishing a note and the held set, plus one name:
        # a lone C spells nothing and so does a bare C and E.
        assert collector.wait_for(7)
        names = [args for address, args in collector.messages
                 if address == contract.CHORD_NAME]
        assert names == [("C", 0, "")]

    def test_every_key_movement_publishes_all_three_addresses(
            self, fake_midi, listening, collector, buses):
        """A subscriber that starts late must not have to reconstruct state."""
        listening.on("/chord/*", collector)
        fake_midi(incoming=[note_on(60), note_on(64), note_on(67)])

        midi.run(bus=buses(port=listening.bound[1]))

        assert collector.wait_for(7)
        addresses = collector.addresses
        assert addresses.count(contract.CHORD_NOTE) == 3
        assert addresses.count(contract.CHORD_NOTES) == 3

    def test_the_held_set_grows_and_shrinks(
            self, fake_midi, listening, collector, buses):
        listening.on(contract.CHORD_NOTES, collector)
        fake_midi(incoming=[note_on(60), note_on(64), note_off(60)])

        midi.run(bus=buses(port=listening.bound[1]))

        assert collector.wait_for(3)
        assert [args for _, args in collector.messages] == [(60,), (60, 64), (64,)]

    def test_notes_that_spell_nothing_publish_no_name(
            self, fake_midi, listening, collector, buses):
        """The notes still go out. Only the reading is withheld."""
        listening.on("/chord/*", collector)
        fake_midi(incoming=[note_on(60), note_on(61)])

        midi.run(bus=buses(port=listening.bound[1]))

        assert collector.wait_for(4)
        collector.settle()
        assert contract.CHORD_NAME not in collector.addresses
        assert collector.addresses.count(contract.CHORD_NOTES) == 2

    def test_a_release_publishes_velocity_zero(
            self, fake_midi, listening, collector, buses):
        listening.on(contract.CHORD_NOTE, collector)
        fake_midi(incoming=[note_on(60, velocity=90), note_off(60)])

        midi.run(bus=buses(port=listening.bound[1]))

        assert collector.wait_for(2)
        assert [args for _, args in collector.messages] == [(60, 90), (60, 0)]

    def test_one_channel_can_be_listened_to_alone(
            self, fake_midi, listening, collector, buses):
        """Channels are 1..16 as printed on hardware, 0..15 on the wire."""
        listening.on(contract.CHORD_NOTE, collector)
        fake_midi(incoming=[note_on(60, channel=0), note_on(64, channel=3)])

        midi.run(bus=buses(port=listening.bound[1]), channel=4)

        assert collector.wait_for(1)
        collector.settle()
        assert [args for _, args in collector.messages] == [(64, 100)]


# -- sink ----------------------------------------------------------------

@pytest.fixture
def port(fake_midi):
    """A fake MIDI output with a sink already attached to it."""
    return fake_midi()


@pytest.fixture
def sink(port) -> MidiSink:
    return MidiSink(port)


class TestOpeningAnOutput:
    def test_a_named_port_that_exists_opens(self, fake_midi):
        fake_midi(outputs=["ChordCat MIDI 1"])
        assert isinstance(MidiSink.open("ChordCat MIDI 1"), MidiSink)

    def test_a_name_that_does_not_exist_lists_the_ones_that_do(self, fake_midi):
        fake_midi(outputs=["IAC Driver Bus 1"])
        with pytest.raises(CannotReachMidi, match="IAC Driver Bus 1"):
            MidiSink.open("Typo")

    def test_no_outputs_at_all_says_to_check_the_cable(self, fake_midi):
        fake_midi(outputs=[])
        with pytest.raises(CannotReachMidi, match="cable"):
            MidiSink.open()


class TestVerbs:
    def test_a_note_sounds(self, sink, port):
        sink.note(None, 60)
        assert port.notes_on() == [60]

    def test_a_note_at_velocity_zero_releases_instead(self, sink, port):
        sink.note(None, 60)
        sink.note(None, 60, 0)
        assert port.notes_off() == [60]

    def test_a_chord_sounds_every_note_of_it(self, sink, port):
        sink.chord(None, "Cmaj7")
        assert port.notes_on() == chord_notes("Cmaj7")

    def test_a_second_chord_replaces_the_first_rather_than_piling_on(
            self, sink, port):
        """A stream of chords from a sensor has to sound like playing."""
        sink.chord(None, "C")
        sink.chord(None, "Am")
        assert port.notes_off() == chord_notes("C")
        assert port.notes_on() == chord_notes("C") + chord_notes("Am")

    def test_a_chord_at_velocity_zero_just_releases(self, sink, port):
        sink.chord(None, "C")
        sink.chord(None, "C", 0)
        assert port.notes_off() == chord_notes("C")
        assert port.notes_on() == chord_notes("C")

    def test_a_control_change_is_clamped_to_the_legal_range(self, sink, port):
        sink.cc(None, 74, 300)
        sink.cc(None, 74, -5)
        assert [m.value for m in port.of("control_change")] == [127, 0]

    def test_panic_releases_everything_it_sounded(self, sink, port):
        sink.note(None, 60)
        sink.chord(None, "Am", channel=2)
        sink.panic(None)
        assert sorted(port.notes_off()) == sorted([60] + chord_notes("Am"))


class TestChannels:
    def test_channel_one_on_the_hardware_is_channel_zero_on_the_wire(
            self, sink, port):
        """The commonest off-by-one in MIDI. It is converted once, here."""
        sink.note(None, 60, 100, 1)
        assert port.sent[0].channel == 0

    def test_channel_sixteen_is_the_last_one(self, sink, port):
        sink.note(None, 60, 100, 16)
        assert port.sent[0].channel == 15

    def test_no_channel_given_means_the_first_one(self, sink, port):
        sink.note(None, 60)
        assert port.sent[0].channel == 0

    def test_a_channel_outside_the_range_is_clamped_not_wrapped(self, sink, port):
        """Wrapping would silently play on a channel the team did not name."""
        sink.note(None, 60, 100, 99)
        sink.note(None, 61, 100, 0)
        assert [m.channel for m in port.sent] == [15, 0]

    def test_each_channel_keeps_its_own_sounding_notes(self, sink, port):
        sink.chord(None, "C", channel=1)
        sink.chord(None, "Am", channel=2)
        assert port.notes_off() == []          # different channels do not collide
        sink.panic(None, channel=1)
        assert port.notes_off() == chord_notes("C")


class TestFailureHandling:
    def test_a_chord_name_nobody_recognises_does_not_kill_the_sink(
            self, sink, port, capsys):
        sink.chord(None, "Cwobble")
        sink.chord(None, "C")
        assert "unknown chord quality" in capsys.readouterr().err
        assert port.notes_on() == chord_notes("C")

    def test_a_note_the_library_refuses_is_reported_and_survived(
            self, fake_midi, capsys):
        """One team's out-of-range note must not stop the shared machine."""
        port = fake_midi(fail=True)
        MidiSink(port).note(None, 999)
        assert "MIDI error" in capsys.readouterr().err


class TestWiring:
    @pytest.mark.parametrize("address,args,expected", [
        (contract.MIDI_NOTE, (60,), "note_on"),
        (contract.MIDI_CHORD, ("C",), "note_on"),
        (contract.MIDI_CC, (74, 64), "control_change"),
    ])
    def test_attach_registers_every_midi_verb(
            self, sink, port, listening, buses, address, args, expected):
        sink.attach(listening)

        buses(port=listening.bound[1]).send(address, *args)

        assert port.wait_for(1), f"{address} produced no MIDI at all"
        assert port.sent[0].type == expected

    def test_panic_arrives_over_the_bus_too(self, sink, port, listening, buses):
        sink.attach(listening)
        sink.chord(None, "C")

        buses(port=listening.bound[1]).send(contract.MIDI_PANIC)

        assert port.wait_for(len(chord_notes("C")) * 2)
        assert port.notes_off() == chord_notes("C")

    def test_closing_releases_whatever_was_still_sounding(self, sink, port):
        sink.chord(None, "Cmaj7")
        sink.close()
        assert port.notes_off() == chord_notes("Cmaj7")
        assert port.closed


class TestMapChord:
    @pytest.mark.parametrize("value,expected", [
        (0.0, "C"), (0.2, "C"), (0.3, "Am"), (0.6, "F"), (0.9, "G"), (1.0, "G"),
    ])
    def test_a_zero_to_one_value_picks_its_place_in_the_progression(
            self, sink, port, listening, buses, value, expected):
        """The whole range is covered and 1.0 lands on the last chord, not past it."""
        sink.map_chord(listening, "/sensor/radar", ["C", "Am", "F", "G"])

        buses(port=listening.bound[1]).send("/sensor/radar", value)

        assert port.wait_for(len(chord_notes(expected)))
        assert port.notes_on() == chord_notes(expected)

    def test_a_value_outside_zero_to_one_is_clamped_to_the_ends(
            self, sink, port, listening, buses):
        sink.map_chord(listening, "/sensor/radar", ["C", "Am"])

        buses(port=listening.bound[1]).send("/sensor/radar", 5.0)

        assert port.wait_for(len(chord_notes("Am")))
        assert port.notes_on() == chord_notes("Am")

    def test_it_only_fires_when_the_chord_actually_changes(
            self, sink, port, listening, buses):
        """A 60 Hz sensor inside one chord's range must not retrigger 60 times."""
        sink.map_chord(listening, "/sensor/radar", ["C", "Am"])
        bus = buses(port=listening.bound[1])

        for value in (0.0, 0.1, 0.2, 0.3):
            bus.send("/sensor/radar", value)

        assert port.wait_for(len(chord_notes("C")))
        port.settle()
        assert port.notes_on() == chord_notes("C")

    def test_a_progression_with_a_typo_in_it_is_refused_up_front(
            self, sink, listening):
        """Before a gesture, not during one."""
        with pytest.raises(ValueError, match="unknown chord quality"):
            sink.map_chord(listening, "/sensor/radar", ["C", "Awobble"])

    def test_an_empty_progression_is_refused(self, sink, listening):
        with pytest.raises(ValueError, match="at least one"):
            sink.map_chord(listening, "/sensor/radar", [])
