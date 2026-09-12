"""Chords as data: what a handful of notes spells, and what a name is made of.

The Ch6 kit is an AlphaTheta ChordCat, a groovebox whose whole point is chords.
It speaks MIDI, and MIDI has no idea what a chord is — it sends four separate
key-down messages and leaves the meaning to you. This module is that meaning,
in both directions:

    >>> identify([60, 64, 67, 71]).name
    'Cmaj7'
    >>> spell("Am7")
    [69, 72, 76, 79]

No hardware, no MIDI library, no bus. It is arithmetic on note numbers, so it
runs anywhere and a team can use it without owning a ChordCat at all.

Middle C is 60 and is called C4, which is the convention MIDI hardware prints
on its own display. Some notation software calls the same note C3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

MIDDLE_C = 60
SEMITONES = 12

#: Sharp spellings, which is what most hardware shows.
SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
#: Flat spellings, for keys and chords that read better that way.
FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")

#: Pitch class of each letter, before any accidental.
_LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

#: Chord qualities as semitones above the root.
#:
#: Order matters only for reading; matching is by exact interval set. Anything
#: not here is not guessed at — ``identify`` returns ``None`` and the caller
#: still has the notes. A wrong chord name is worse than no chord name, because
#: a team will build a mapping on it and wonder why it drifts.
QUALITIES: Dict[str, Tuple[int, ...]] = {
    "5": (0, 7),                        # power chord, no third, neither major nor minor
    "": (0, 4, 7),                      # major, written as the bare root: C
    "m": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "7": (0, 4, 7, 10),                 # dominant
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "m7b5": (0, 3, 6, 10),              # half diminished
    "dim7": (0, 3, 6, 9),
    "mMaj7": (0, 3, 7, 11),
    "7sus4": (0, 5, 7, 10),
    "add9": (0, 2, 4, 7),
    "9": (0, 2, 4, 7, 10),
    "maj9": (0, 2, 4, 7, 11),
    "m9": (0, 2, 3, 7, 10),
    "69": (0, 2, 4, 7, 9),
}

#: Interval set back to quality, for recognition.
_BY_INTERVALS = {frozenset(intervals): suffix for suffix, intervals in QUALITIES.items()}

#: Suffixes a person might type that are not the spelling used above.
ALIASES = {
    "M": "", "maj": "", "major": "",
    "min": "m", "minor": "m", "-": "m",
    "o": "dim", "°": "dim", "dim5": "dim",
    "+": "aug", "aug5": "aug",
    "ø": "m7b5", "m7-5": "m7b5", "half-dim": "m7b5",
    "o7": "dim7", "°7": "dim7",
    "dom7": "7", "sus": "sus4",
    "minMaj7": "mMaj7", "mM7": "mMaj7",
    "6/9": "69",
}

_NAME = re.compile(r"^\s*([A-Ga-g])([#b♯♭]*)\s*(.*?)\s*$")


@dataclass(frozen=True)
class Chord:
    """What a set of notes spells.

    ``notes`` is what was actually played, in the octaves it was played in, so
    a caller can send it straight back out. ``root`` and ``quality`` are the
    reading, and ``bass`` is the lowest note's pitch class, which is what makes
    an inversion audible even though the name does not change.
    """

    root: int                   #: pitch class, 0 = C
    quality: str                #: a key of QUALITIES
    notes: Tuple[int, ...]      #: the sounding MIDI notes, low to high
    bass: int                   #: pitch class of the lowest note

    @property
    def name(self) -> str:
        """``Cmaj7``, or ``Cmaj7/E`` when something other than the root is lowest."""
        base = SHARP_NAMES[self.root] + self.quality
        if self.bass != self.root:
            return f"{base}/{SHARP_NAMES[self.bass]}"
        return base

    @property
    def inverted(self) -> bool:
        return self.bass != self.root

    def __str__(self) -> str:
        return self.name


# -- notes ---------------------------------------------------------------

def note_name(note: int, flats: bool = False) -> str:
    """``60`` -> ``C4``. Middle C is 60, as the hardware labels it."""
    names = FLAT_NAMES if flats else SHARP_NAMES
    return f"{names[note % SEMITONES]}{note // SEMITONES - 1}"


def note_number(name: str) -> int:
    """``"C4"`` -> ``60``. Accepts sharps, flats and doubles: ``Bb3``, ``F##2``."""
    match = re.match(r"^\s*([A-Ga-g])([#b♯♭]*)(-?\d+)\s*$", name)
    if not match:
        raise ValueError(f"not a note name: {name!r}")
    letter, accidentals, octave = match.groups()
    return (_LETTERS[letter.upper()] + _accidental_shift(accidentals)
            + (int(octave) + 1) * SEMITONES)


def _accidental_shift(accidentals: str) -> int:
    return sum(1 if a in "#♯" else -1 for a in accidentals)


def pitch_classes(notes: Iterable[int]) -> List[int]:
    """The distinct pitch classes in a set of notes, ascending."""
    return sorted({note % SEMITONES for note in notes})


# -- reading a chord -----------------------------------------------------

def identify(notes: Sequence[int]) -> Optional[Chord]:
    """Name the chord a set of MIDI notes spells, or ``None`` if it is not one.

    Every pitch class present is tried as the root, starting with the lowest
    sounding note, so a chord in root position reads as itself and an inversion
    reads as the same chord over a different bass. That ordering is also what
    decides the genuinely ambiguous pairs: C6 and Am7 hold identical pitch
    classes, and which one you meant is exactly the note you put at the bottom.
    """
    if not notes:
        return None
    sounding = tuple(sorted(notes))
    present = pitch_classes(sounding)
    bass = sounding[0] % SEMITONES

    for root in [bass] + [pc for pc in present if pc != bass]:
        intervals = frozenset((pc - root) % SEMITONES for pc in present)
        quality = _BY_INTERVALS.get(intervals)
        if quality is not None:
            return Chord(root=root, quality=quality, notes=sounding, bass=bass)
    return None


# -- writing a chord -----------------------------------------------------

def parse(name: str) -> Tuple[int, str]:
    """``"F#m7"`` -> ``(6, "m7")``. Raises ``ValueError`` on anything else."""
    match = _NAME.match(name)
    if not match:
        raise ValueError(f"not a chord name: {name!r}")
    letter, accidentals, suffix = match.groups()
    root = (_LETTERS[letter.upper()] + _accidental_shift(accidentals)) % SEMITONES
    quality = ALIASES.get(suffix, suffix)
    if quality not in QUALITIES:
        raise ValueError(
            f"unknown chord quality {suffix!r} in {name!r}; "
            f"known: {', '.join(repr(q) for q in QUALITIES)}")
    return root, quality


def spell(name: str, octave: int = 4) -> List[int]:
    """``"Am7"`` -> ``[69, 72, 76, 79]``. The notes to play, low to high.

    ``octave`` places the root, so ``spell("C", 3)`` sits an octave below
    ``spell("C", 4)``. The root is the lowest note; inversions are the caller's
    business, because which one sounds right depends on what came before it.
    """
    root, quality = parse(name)
    base = root + (octave + 1) * SEMITONES
    return [base + step for step in QUALITIES[quality]]


def transpose(notes: Iterable[int], semitones: int) -> List[int]:
    """Move a set of notes, keeping everything inside the MIDI range 0..127."""
    return [min(max(note + semitones, 0), 127) for note in notes]
