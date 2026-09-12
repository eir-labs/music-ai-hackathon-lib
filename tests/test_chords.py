"""Chords as data.

No hardware, no bus, no MIDI library: this is arithmetic on note numbers, and
it is tested as arithmetic. It carries more weight than its size suggests,
because the MIDI source, the MIDI sink and the `kitlib chord` command all read
their answers out of it. A wrong table here is wrong everywhere at once.

The cases are written as a musician would check them, by naming the notes.
"""
from __future__ import annotations

import pytest

from kitlib import chords


def notes(*names) -> list:
    """``notes("C4", "E4", "G4")`` -> ``[60, 64, 67]``."""
    return [chords.note_number(name) for name in names]


class TestNoteNumbers:
    @pytest.mark.parametrize("name,number", [
        ("C4", 60), ("A4", 69), ("C0", 12), ("C-1", 0), ("G9", 127),
        ("C#4", 61), ("Db4", 61), ("Bb3", 58), ("E#3", 53), ("Cb4", 59),
    ])
    def test_a_name_becomes_the_number_the_hardware_uses(self, name, number):
        assert chords.note_number(name) == number

    def test_middle_c_is_sixty_and_is_called_c4(self):
        """The convention MIDI hardware prints. Notation software may say C3."""
        assert chords.MIDDLE_C == 60
        assert chords.note_name(60) == "C4"
        assert chords.note_number("C4") == 60

    @pytest.mark.parametrize("number,name", [
        (60, "C4"), (61, "C#4"), (69, "A4"), (0, "C-1"), (127, "G9"),
    ])
    def test_a_number_becomes_a_name(self, number, name):
        assert chords.note_name(number) == name

    def test_flats_are_available_for_keys_that_read_better_that_way(self):
        assert chords.note_name(61) == "C#4"
        assert chords.note_name(61, flats=True) == "Db4"

    def test_a_double_sharp_shifts_twice(self):
        assert chords.note_number("F##2") == chords.note_number("G2")

    @pytest.mark.parametrize("bad", ["H4", "C", "4", "", "C4#", "Cb"])
    def test_things_that_are_not_note_names_are_rejected(self, bad):
        with pytest.raises(ValueError):
            chords.note_number(bad)


class TestIdentify:
    @pytest.mark.parametrize("played,name", [
        (("C4", "E4", "G4"), "C"),
        (("C4", "Eb4", "G4"), "Cm"),
        (("C4", "E4", "G4", "B4"), "Cmaj7"),
        (("C4", "E4", "G4", "Bb4"), "C7"),
        (("C4", "Eb4", "G4", "Bb4"), "Cm7"),
        (("C4", "Eb4", "Gb4"), "Cdim"),
        (("C4", "E4", "G#4"), "Caug"),
        (("C4", "D4", "G4"), "Csus2"),
        (("C4", "F4", "G4"), "Csus4"),
        (("C4", "G4"), "C5"),
        (("F#4", "A4", "C#5"), "F#m"),
        (("Bb3", "D4", "F4", "Ab4"), "A#7"),
    ])
    def test_a_chord_reads_as_itself(self, played, name):
        assert chords.identify(notes(*played)).name == name

    def test_an_inversion_keeps_the_chord_and_names_the_bass(self):
        """E G C is still a C major chord, played over its third."""
        chord = chords.identify(notes("E4", "G4", "C5"))
        assert chord.name == "C/E"
        assert chord.root == 0
        assert chord.bass == 4
        assert chord.inverted

    def test_root_position_is_not_called_an_inversion(self):
        chord = chords.identify(notes("C4", "E4", "G4"))
        assert not chord.inverted
        assert chord.name == "C"

    def test_doubling_a_note_an_octave_up_changes_nothing(self):
        """A two-handed voicing spells the same chord as a close one."""
        assert chords.identify(notes("C3", "G3", "C4", "E4", "G4")).name == "C"

    def test_the_bass_decides_between_two_readings_of_the_same_notes(self):
        """C6 and Am7 hold identical pitch classes. What you put lowest is the answer."""
        same = ("C", "E", "G", "A")
        assert chords.identify(notes("C4", "E4", "G4", "A4")).name == "C6"
        assert chords.identify(notes("A3", "C4", "E4", "G4")).name == "Am7"
        assert {n % 12 for n in notes("C4", "E4", "G4", "A4")} == \
               {n % 12 for n in notes("A3", "C4", "E4", "G4")}
        assert len(same) == 4

    def test_the_notes_played_are_kept_as_played(self):
        """So a caller can send them straight back out without respelling."""
        played = notes("E4", "G4", "C5")
        assert chords.identify(played).notes == (64, 67, 72)

    @pytest.mark.parametrize("played", [
        ("C4", "C#4", "D4"),        # a cluster
        ("C4", "D4"),               # a bare second
        ("C4", "E4", "G4", "C#5"),  # a triad with something stuck to it
    ])
    def test_what_is_not_a_chord_is_not_guessed_at(self, played):
        """A wrong name is worse than none; a team would build a mapping on it."""
        assert chords.identify(notes(*played)) is None

    def test_nothing_held_is_not_a_chord(self):
        assert chords.identify([]) is None

    def test_one_note_alone_is_not_a_chord(self):
        assert chords.identify([60]) is None


class TestSpell:
    @pytest.mark.parametrize("name,expected", [
        ("C", ("C4", "E4", "G4")),
        ("Am", ("A4", "C5", "E5")),
        ("Cmaj7", ("C4", "E4", "G4", "B4")),
        ("F#m7", ("F#4", "A4", "C#5", "E5")),
        ("Dsus4", ("D4", "G4", "A4")),
        ("G7", ("G4", "B4", "D5", "F5")),
    ])
    def test_a_name_becomes_the_notes_to_play(self, name, expected):
        assert chords.spell(name) == notes(*expected)

    def test_the_octave_moves_the_whole_chord(self):
        assert chords.spell("C", 3) == [n - 12 for n in chords.spell("C", 4)]

    def test_the_root_is_the_lowest_note(self):
        for name in ("C", "Am7", "F#dim", "Bb9"):
            root, _ = chords.parse(name)
            assert chords.spell(name)[0] % 12 == root

    @pytest.mark.parametrize("name", sorted(chords.QUALITIES))
    def test_everything_the_table_offers_can_be_spelled_and_read_back(self, name):
        """Round trip: spell it, identify it, get the same chord.

        This is the test that keeps the two halves honest. Add a quality to the
        table and forget that some rotation of it already means something else,
        and it fails here rather than on stage.
        """
        written = chords.spell("C" + name)
        read = chords.identify(written)
        assert read is not None, f"C{name} spelled {written} and read as nothing"
        assert read.quality == name
        assert read.root == 0

    @pytest.mark.parametrize("typed,means", [
        ("CM", "C"), ("Cmaj", "C"), ("Cmin", "Cm"), ("C-", "Cm"),
        ("C+", "Caug"), ("Co", "Cdim"), ("Co7", "Cdim7"), ("Cdom7", "C7"),
        ("Csus", "Csus4"), ("CmM7", "CmMaj7"),
    ])
    def test_the_spellings_people_actually_type_are_understood(self, typed, means):
        assert chords.spell(typed) == chords.spell(means)

    def test_an_unknown_quality_says_what_is_known(self):
        with pytest.raises(ValueError, match="unknown chord quality"):
            chords.spell("Cwobble")

    @pytest.mark.parametrize("bad", ["", "H", "7", "  ", "#m"])
    def test_things_that_are_not_chord_names_are_rejected(self, bad):
        with pytest.raises(ValueError):
            chords.spell(bad)


class TestTranspose:
    def test_it_moves_every_note(self):
        assert chords.transpose(notes("C4", "E4", "G4"), 2) == notes("D4", "F#4", "A4")

    def test_it_stays_inside_the_midi_range(self):
        """127 is the highest note that exists. Going past it is not a note."""
        assert chords.transpose([120, 125], 10) == [127, 127]
        assert chords.transpose([5, 2], -10) == [0, 0]

    def test_transposing_a_chord_keeps_it_the_same_chord(self):
        for semitones in range(12):
            moved = chords.transpose(chords.spell("Am7"), semitones)
            assert chords.identify(moved).quality == "m7"
