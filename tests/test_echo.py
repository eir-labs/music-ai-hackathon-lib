"""Measuring a space, against places that do not exist.

Every test here states a room in metres, plays a sweep through it, and asserts
the metres back. No microphone, no loudspeaker and no weather, which is the
only way to know whether a disappointing measurement at the lake is the method
or the conditions.

Sweeps are short here because a two-second one exercises the same arithmetic as
a ten-second one and the suite has to stay quick.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from doubles import echo_room
from kitlib import echo

RATE = 48000
COLD = 4.0                      #: a September evening at altitude


@pytest.fixture
def excitation():
    return echo.sweep(seconds=1.0, rate=RATE)


def heard(excitation, distances, **kwargs):
    """The reflections an analysis finds in a room with these reflectors."""
    captured = echo_room(excitation, distances, celsius=COLD, **kwargs)
    return echo.reflections(echo.deconvolve(captured, excitation), RATE)


class TestSpeedOfSound:
    @pytest.mark.parametrize("celsius,expected", [
        (0.0, 331.3), (20.0, 343.4), (4.0, 333.7), (-5.0, 328.3),
    ])
    def test_it_tracks_temperature(self, celsius, expected):
        assert echo.speed_of_sound(celsius) == pytest.approx(expected, abs=0.1)

    def test_the_number_everyone_quotes_is_a_warm_room(self):
        """343 m/s is 20 degrees. At a cold lake it is wrong by about 3%."""
        warm = echo.speed_of_sound(20.0)
        cold = echo.speed_of_sound(4.0)
        assert warm == pytest.approx(343.4, abs=0.1)
        assert (warm - cold) / warm == pytest.approx(0.028, abs=0.002)

    def test_getting_it_wrong_moves_a_distant_reflector_by_metres(self):
        """Which is why the temperature is a parameter and not a constant."""
        delay = 0.6
        warm = echo.Reflection(delay, 0.5).distance(20.0)
        cold = echo.Reflection(delay, 0.5).distance(4.0)
        assert warm - cold == pytest.approx(2.9, abs=0.2)


class TestSweep:
    def test_it_inverts_itself_into_an_impulse(self, excitation):
        """The load-bearing property. If this fails nothing downstream means anything.

        A sweep convolved with its own inverse filter has to collapse to a
        single spike. Anything smeared here shows up later as reflections from
        surfaces that are not there.
        """
        impulse = echo.deconvolve(excitation.signal, excitation)
        envelope = np.abs(impulse)
        peak = int(np.argmax(envelope))

        window = int(0.001 * RATE)
        near = np.sum(envelope[peak - window:peak + window] ** 2)
        assert near / np.sum(envelope ** 2) > 0.99

        away = envelope.copy()
        away[peak - window:peak + window] = 0.0
        assert 20 * math.log10(envelope[peak] / away.max()) > 40

    def test_it_sweeps_from_low_to_high(self, excitation):
        """First half low, second half high, which is what exponential means here."""
        half = len(excitation.signal) // 2
        early = np.fft.rfft(excitation.signal[:half])
        late = np.fft.rfft(excitation.signal[half:])
        bins = np.fft.rfftfreq(half, 1 / RATE)
        assert bins[np.argmax(np.abs(early))] < bins[np.argmax(np.abs(late))]

    def test_it_starts_and_ends_quietly(self, excitation):
        """A loudspeaker asked to start instantly makes a click, not a sweep."""
        assert abs(excitation.signal[0]) < 0.01
        assert abs(excitation.signal[-1]) < 0.01

    def test_the_inverse_is_the_sweep_backwards(self, excitation):
        """Not identical, because the exponential tilt is taken out on the way."""
        reversed_sweep = excitation.signal[::-1]
        correlation = np.corrcoef(reversed_sweep, excitation.inverse)[0, 1]
        assert 0.3 < correlation < 0.99

    @pytest.mark.parametrize("kwargs,message", [
        ({"seconds": 0}, "positive duration"),
        ({"seconds": -1}, "positive duration"),
        ({"low": 0}, "low < high"),
        ({"low": 9000, "high": 500}, "low < high"),
        ({"high": 30000, "rate": 48000}, "Nyquist"),
    ])
    def test_impossible_sweeps_are_refused_with_the_reason(self, kwargs, message):
        with pytest.raises(ValueError, match=message):
            echo.sweep(**{"seconds": 1.0, **kwargs})

    def test_it_reports_itself_legibly(self, excitation):
        assert "1s" in repr(excitation) and "48000" in repr(excitation)


class TestDeconvolve:
    def test_an_empty_recording_says_so(self, excitation):
        with pytest.raises(ValueError, match="empty"):
            echo.deconvolve([], excitation)

    def test_a_reflector_appears_at_its_own_delay(self, excitation):
        found = heard(excitation, [30.0])
        assert len(found) == 1
        assert found[0].distance(COLD) == pytest.approx(30.0, abs=0.05)


class TestReflections:
    def test_it_recovers_several_distances_at_once(self, excitation):
        found = heard(excitation, [12.0, 27.5, 61.0], amplitudes=[0.5, 0.3, 0.15])
        assert [round(r.distance(COLD), 1) for r in found] == [12.0, 27.5, 61.0]

    def test_they_come_back_nearest_first(self, excitation):
        found = heard(excitation, [61.0, 12.0, 27.5], amplitudes=[0.15, 0.5, 0.3])
        assert [r.delay for r in found] == sorted(r.delay for r in found)

    def test_a_nearer_surface_reflects_louder_than_a_far_one(self, excitation):
        found = heard(excitation, [12.0, 61.0], amplitudes=[0.5, 0.15])
        assert found[0].amplitude > found[1].amplitude

    def test_the_direct_arrival_is_the_reference_not_a_reflection(self, excitation):
        """Which is what lets several recorders be used without a shared clock."""
        found = heard(excitation, [30.0])
        assert all(r.delay > 0 for r in found)
        assert len(found) == 1

    def test_the_sidelobes_beside_the_direct_arrival_are_not_surfaces(
            self, excitation):
        """Deconvolution leaves ringing next to the peak. Reporting it as a
        reflector two centimetres away is wrong in a way that looks plausible.
        """
        found = heard(excitation, [30.0])
        assert all(r.distance(COLD) > 0.3 for r in found)

    def test_a_quiet_reflection_below_the_floor_is_left_out(self, excitation):
        """Lowering the floor finds it again, along with the ringing around the
        loud one, which is why the floor is not simply set as low as it will go.
        """
        captured = echo_room(excitation, [20.0, 55.0], amplitudes=[0.5, 0.005],
                             celsius=COLD)
        ir = echo.deconvolve(captured, excitation)

        def distances(floor):
            return [r.distance(COLD)
                    for r in echo.reflections(ir, RATE, floor_db=floor)]

        assert not any(abs(d - 55.0) < 0.3 for d in distances(-30.0))
        assert any(abs(d - 55.0) < 0.3 for d in distances(-60.0))
        assert len(distances(-30.0)) < len(distances(-60.0))

    def test_one_wide_peak_is_one_surface_not_several(self, excitation):
        found = heard(excitation, [30.0])
        assert len(found) == 1

    def test_the_limit_caps_how_many_come_back(self, excitation):
        many = [10.0 + 6.0 * n for n in range(10)]
        found = heard(excitation, many, amplitudes=[0.4] * len(many))
        assert len(echo.reflections(
            echo.deconvolve(echo_room(excitation, many, [0.4] * len(many),
                                      celsius=COLD), excitation),
            RATE, limit=3)) == 3
        assert len(found) > 3

    def test_silence_holds_no_surfaces(self):
        assert echo.reflections(np.zeros(1000), RATE) == []

    def test_something_too_short_to_analyse_is_not_an_error(self):
        assert echo.reflections([1.0], RATE) == []
        assert echo.reflections([], RATE) == []

    def test_noise_does_not_stop_the_real_reflectors_being_found(self, excitation):
        found = heard(excitation, [18.0, 44.0], amplitudes=[0.45, 0.28],
                      noise=0.01)
        distances = [r.distance(COLD) for r in found]
        assert any(abs(d - 18.0) < 0.2 for d in distances)
        assert any(abs(d - 44.0) < 0.2 for d in distances)


class TestDistances:
    def test_path_is_there_and_back_and_distance_is_half_of_it(self):
        reflection = echo.Reflection(delay=0.1, amplitude=0.5)
        assert reflection.path(COLD) == pytest.approx(33.37, abs=0.05)
        assert reflection.distance(COLD) == pytest.approx(16.68, abs=0.05)

    def test_it_reports_itself_in_milliseconds(self):
        assert "100.0 ms" in repr(echo.Reflection(delay=0.1, amplitude=0.5))


class TestSurvey:
    """The part that makes this musical rather than merely accurate."""

    def measure(self, excitation, survey, distances, repeats, jitter=0.0,
                noise=0.002, seed=0):
        rng = np.random.default_rng(seed)
        for n in range(repeats):
            moved = [d + rng.normal(0.0, jitter) for d in distances]
            captured = echo_room(excitation, moved, celsius=COLD, noise=noise,
                                 seed=seed + n)
            survey.add(echo.reflections(echo.deconvolve(captured, excitation), RATE))
        return survey

    def test_one_capture_corroborates_nothing(self, excitation):
        """Saying otherwise would be a lie the rest of the piece is built on."""
        survey = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                              [20.0, 50.0], repeats=1)
        assert survey.captures == 1
        assert survey.confidence == 0.0
        assert all(math.isinf(e.spread) for e in survey.estimates())

    def test_confidence_climbs_as_still_captures_agree(self, excitation):
        survey = echo.Survey(celsius=COLD, rate=RATE)
        climb = []
        for n in range(6):
            self.measure(excitation, survey, [18.0, 44.0], repeats=1, seed=n)
            climb.append(survey.confidence)

        assert climb[0] == 0.0
        assert climb == sorted(climb), f"confidence went backwards: {climb}"
        assert climb[-1] > 0.8

    def test_two_agreeing_captures_are_not_treated_as_ten(self, excitation):
        """Small samples get the Student factor, so certainty has to be earned."""
        few = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                           [18.0], repeats=2)
        many = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                            [18.0], repeats=8)
        assert few.confidence < many.confidence
        assert few.confidence < 0.7

    def test_a_medium_that_will_not_sit_still_keeps_confidence_low(
            self, excitation):
        """Wind moves the arrival times, the captures disagree, and the number
        says so instead of averaging the disagreement away.
        """
        still = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                             [18.0, 44.0], repeats=5, jitter=0.0)
        windy = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                             [18.0, 44.0], repeats=5, jitter=0.6, seed=40)
        assert windy.confidence < 0.3
        assert windy.confidence < still.confidence

    def test_a_surface_seen_once_in_many_captures_counts_against_it(
            self, excitation):
        """A peak that will not reappear is usually weather, not rock."""
        survey = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                              [18.0], repeats=4)
        steady = survey.confidence
        survey.add([echo.Reflection(delay=0.31, amplitude=0.2)])
        assert survey.confidence < steady

    def test_captures_of_the_same_surface_become_one_estimate(self, excitation):
        survey = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                              [18.0, 44.0], repeats=4)
        estimates = survey.estimates()
        assert len(estimates) == 2
        assert all(e.seen == 4 for e in estimates)
        assert [round(e.distance, 1) for e in estimates] == [18.0, 44.0]

    def test_the_tolerance_decides_what_counts_as_the_same_surface(self):
        near = echo.Survey(tolerance=0.010, rate=RATE)
        far = echo.Survey(tolerance=0.0001, rate=RATE)
        for survey in (near, far):
            survey.add([echo.Reflection(0.100, 0.5)])
            survey.add([echo.Reflection(0.101, 0.5)])
        assert len(near.estimates()) == 1
        assert len(far.estimates()) == 2

    def test_the_spread_shrinks_as_captures_accumulate(self, excitation):
        few = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                           [30.0], repeats=3, jitter=0.05, seed=5)
        many = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                            [30.0], repeats=9, jitter=0.05, seed=5)
        assert many.estimates()[0].spread < few.estimates()[0].spread

    def test_an_empty_survey_is_not_confident(self):
        assert echo.Survey().confidence == 0.0
        assert echo.Survey().estimates() == []

    def test_add_is_chainable_and_counts_captures(self):
        survey = echo.Survey().add([]).add([])
        assert survey.captures == 2

    def test_it_reports_itself_legibly(self, excitation):
        survey = self.measure(excitation, echo.Survey(celsius=COLD, rate=RATE),
                              [18.0], repeats=3)
        text = repr(survey)
        assert "3 captures" in text and "confidence" in text


class TestPublishing:
    def test_the_confidence_and_the_distances_reach_the_bus(
            self, listening, buses, collector):
        listening.on("/sensor/*", collector)
        survey = echo.Survey(celsius=COLD, rate=RATE)
        for _ in range(3):
            survey.add([echo.Reflection(0.100, 0.5), echo.Reflection(0.260, 0.3)])

        survey.publish(buses(port=listening.bound[1]))

        assert collector.wait_for(2)
        arrived = dict(collector.messages)
        assert arrived["/sensor/echo_confidence"][0] == pytest.approx(
            survey.confidence)
        assert len(arrived["/sensor/echo"]) == 2

    def test_the_name_can_be_changed_for_a_second_position(
            self, listening, buses, collector):
        """Two positions on the same bus need two names."""
        listening.on("/sensor/*", collector)
        echo.Survey().add([]).publish(buses(port=listening.bound[1]), "shore")

        assert collector.wait_for(2)
        assert set(collector.addresses) == {"/sensor/shore",
                                            "/sensor/shore_confidence"}


class TestFiles:
    def test_a_sweep_survives_a_round_trip_to_disk(self, tmp_path, excitation):
        path = str(tmp_path / "sweep.wav")
        echo.write_wav(path, excitation.signal, RATE)
        back, rate = echo.read_wav(path)

        assert rate == RATE
        assert len(back) == len(excitation.signal)
        normalised = excitation.signal / np.max(np.abs(excitation.signal))
        assert np.corrcoef(back, normalised)[0, 1] > 0.999

    def test_it_leaves_headroom_below_full_scale(self, tmp_path, excitation):
        """A loudspeaker asked for full scale reproduces the clipping too."""
        path = str(tmp_path / "sweep.wav")
        echo.write_wav(path, excitation.signal, RATE)
        back, _ = echo.read_wav(path)
        assert 0.8 < np.max(np.abs(back)) < 0.95

    def test_a_measurement_still_works_after_the_round_trip(
            self, tmp_path, excitation):
        """Sixteen bits is enough. This is the whole pipeline as it will run."""
        path = str(tmp_path / "capture.wav")
        echo.write_wav(path, echo_room(excitation, [25.0], celsius=COLD), RATE)
        recorded, rate = echo.read_wav(path)

        found = echo.reflections(echo.deconvolve(recorded, excitation), rate)
        assert found[0].distance(COLD) == pytest.approx(25.0, abs=0.05)

    def test_the_24_bit_files_recorders_write_by_default_are_read(self, tmp_path):
        """NumPy has no 24-bit type, so this is hand-unpacked and worth pinning."""
        import wave

        path = str(tmp_path / "24bit.wav")
        wanted = np.array([0.0, 0.5, -0.5, 0.25], dtype=float)
        packed = (wanted * (1 << 23)).astype("<i4")
        raw = b"".join(int(v).to_bytes(4, "little", signed=True)[:3]
                       for v in packed)
        with wave.open(path, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(3)
            handle.setframerate(RATE)
            handle.writeframes(raw)

        back, rate = echo.read_wav(path)
        assert rate == RATE
        assert back == pytest.approx(wanted, abs=1e-5)

    def test_one_channel_is_taken_from_a_stereo_file(self, tmp_path):
        import wave

        path = str(tmp_path / "stereo.wav")
        left = np.array([0.5, 0.5, 0.5], dtype=float)
        right = np.array([-0.25, -0.25, -0.25], dtype=float)
        interleaved = np.empty(6)
        interleaved[0::2], interleaved[1::2] = left, right
        with wave.open(path, "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(RATE)
            handle.writeframes((interleaved * 32767).astype("<i2").tobytes())

        assert echo.read_wav(path, channel=0)[0] == pytest.approx(left, abs=1e-4)
        assert echo.read_wav(path, channel=1)[0] == pytest.approx(right, abs=1e-4)
        with pytest.raises(ValueError, match="no channel 5"):
            echo.read_wav(path, channel=5)
