"""The conditioning stages, including the claims their docstrings make."""
from __future__ import annotations

import math

import pytest

from kitlib import signal
from kitlib.signal import (Chain, Deadband, Median, RateLimit, Scale, Smooth,
                           Stage)


class TestScale:
    def test_maps_input_range_onto_zero_to_one(self):
        scale = Scale(0, 1023)
        assert scale(0) == 0.0
        assert scale(1023) == 1.0
        assert scale(511.5) == pytest.approx(0.5)

    def test_clamps_outside_the_documented_range_by_default(self):
        scale = Scale(45, 800)
        assert scale(10) == 0.0
        assert scale(9999) == 1.0

    def test_clamping_can_be_turned_off(self):
        scale = Scale(0, 100, clamp=False)
        assert scale(150) == pytest.approx(1.5)
        assert scale(-50) == pytest.approx(-0.5)

    def test_honours_a_custom_output_range(self):
        assert Scale(0, 1, out_lo=20, out_hi=20000)(0.5) == pytest.approx(10010)

    def test_an_inverted_input_range_inverts_the_output(self):
        # Closer means louder: 0 cm should map to 1, not 0.
        near_is_loud = Scale(40, 0)
        assert near_is_loud(0) == 1.0
        assert near_is_loud(40) == 0.0

    def test_an_empty_range_is_rejected(self):
        with pytest.raises(ValueError):
            Scale(5, 5)


class TestSmooth:
    def test_the_first_sample_passes_straight_through(self, clock):
        assert Smooth(0.1, clock)(7.0) == 7.0

    def test_one_time_constant_covers_about_two_thirds_of_a_step(self, clock):
        smooth = Smooth(0.5, clock)
        smooth(0.0)
        clock.advance(0.5)
        assert smooth(1.0) == pytest.approx(1 - math.exp(-1), rel=1e-9)

    def test_it_converges_on_the_target(self, clock):
        smooth = Smooth(0.1, clock)
        smooth(0.0)
        for _ in range(50):
            clock.advance(0.05)
            value = smooth(1.0)
        assert value == pytest.approx(1.0, abs=1e-6)

    def test_zero_elapsed_time_holds_the_previous_value(self, clock):
        smooth = Smooth(0.1, clock)
        smooth(0.0)
        assert smooth(1.0) == 0.0

    def test_the_time_constant_is_in_seconds_not_samples(self, clock):
        """The docstring promises a 650 Hz radar and a 10 Hz camera behave alike."""
        fast, slow = Smooth(0.2, clock), Smooth(0.2, clock)
        fast(0.0)
        slow(0.0)
        for _ in range(100):
            clock.advance(0.01)
            fast_value = fast(1.0)
        clock.now = 0.0
        slow(0.0)
        for _ in range(10):
            clock.advance(0.1)
            slow_value = slow(1.0)
        assert fast_value == pytest.approx(slow_value, abs=1e-3)

    def test_reset_forgets_the_running_value(self, clock):
        smooth = Smooth(0.1, clock)
        smooth(100.0)
        smooth.reset()
        assert smooth(3.0) == 3.0

    @pytest.mark.parametrize("tau", [0, -1])
    def test_a_non_positive_time_constant_is_rejected(self, tau):
        with pytest.raises(ValueError):
            Smooth(tau)


class TestDeadband:
    def test_the_first_sample_always_passes(self):
        assert Deadband(5)(0.0) == 0.0

    def test_small_moves_are_dropped_and_large_ones_pass(self):
        band = Deadband(5)
        assert [band(x) for x in (0, 2, 10, 11, 20)] == [0.0, None, 10.0, None, 20.0]

    def test_slow_drift_accumulates_against_the_last_value_that_passed(self):
        band = Deadband(1.0)
        band(0.0)
        assert band(0.4) is None
        assert band(0.8) is None
        assert band(1.1) == 1.1

    def test_reset_forgets_the_reference(self):
        band = Deadband(5)
        band(100.0)
        band.reset()
        assert band(0.0) == 0.0

    def test_a_negative_threshold_is_rejected(self):
        with pytest.raises(ValueError):
            Deadband(-1)


class TestRateLimit:
    def test_the_first_sample_passes(self, clock):
        assert RateLimit(10, clock)(1.0) == 1.0

    def test_samples_inside_the_interval_are_dropped(self, clock):
        limit = RateLimit(10, clock)
        limit(1.0)
        clock.advance(0.05)
        assert limit(2.0) is None
        clock.advance(0.05)
        assert limit(3.0) == 3.0

    def test_it_thins_a_650_hz_radar_to_the_requested_rate(self, clock):
        limit = RateLimit(60, clock)
        passed = 0
        for _ in range(650):
            clock.advance(1 / 650)
            if limit(1.0) is not None:
                passed += 1
        assert passed == pytest.approx(60, abs=2)

    @pytest.mark.parametrize("hz", [0, -5])
    def test_a_non_positive_rate_is_rejected(self, hz):
        with pytest.raises(ValueError):
            RateLimit(hz)


class TestMedian:
    def test_it_rejects_an_isolated_spike(self):
        median = Median(3)
        assert [median(x) for x in (1, 100, 2, 3)] == [1.0, 50.5, 2.0, 3.0]

    def test_the_window_does_not_grow_past_n(self):
        median = Median(3)
        for value in (1, 1, 1, 50, 50, 50):
            result = median(value)
        assert result == 50.0

    def test_a_window_of_one_is_a_passthrough(self):
        median = Median(1)
        assert [median(x) for x in (5, 9, 2)] == [5.0, 9.0, 2.0]

    def test_reset_empties_the_window(self):
        median = Median(5)
        for _ in range(5):
            median(100)
        median.reset()
        assert median(1) == 1.0

    def test_an_empty_window_is_rejected(self):
        with pytest.raises(ValueError):
            Median(0)


class TestChain:
    def test_stages_apply_in_order(self):
        chain = Chain(Scale(0, 100), Scale(0, 1, out_lo=0, out_hi=10))
        assert chain(50) == pytest.approx(5.0)

    def test_the_shift_operator_builds_a_chain(self):
        chain = Scale(0, 10) >> Median(1)
        assert isinstance(chain, Chain)
        assert len(chain.stages) == 2

    def test_nested_chains_are_flattened(self):
        chain = (Scale(0, 1) >> Median(1)) >> (Deadband(0) >> Median(1))
        assert len(chain.stages) == 4
        assert not any(isinstance(s, Chain) for s in chain.stages)

    def test_a_dropped_sample_short_circuits_the_rest(self, clock):
        """A rate-limited sample must not reach the smoother behind it."""
        smooth = Smooth(0.1, clock)
        chain = Chain(RateLimit(10, clock), smooth)
        assert chain(0.0) == 0.0
        clock.advance(0.01)
        assert chain(1000.0) is None
        clock.advance(0.2)
        assert chain(0.0) == pytest.approx(0.0, abs=1e-9)

    def test_reset_reaches_every_stage(self, clock):
        smooth = Smooth(0.1, clock)
        chain = Chain(Scale(0, 10), smooth)
        chain(10)
        chain.reset()
        assert smooth._y is None

    def test_repr_reads_like_the_source(self):
        assert repr(Scale(0, 1) >> RateLimit(60)) == "Scale(0, 1 -> 0, 1) >> RateLimit(60)"


class TestPresets:
    def test_the_force_sensor_tops_out_where_the_kit_doc_says_it_does(self):
        # Sensor_Kit_Setup.md: FSR402 never reaches 1023.
        assert signal.FSR402(650) == 1.0
        assert signal.FSR402(1023) == 1.0

    def test_the_light_sensor_floor_is_its_dark_reading_not_zero(self):
        assert signal.LIGHT_LS06S(45) == 0.0
        assert signal.LIGHT_LS06S(0) == 0.0
        assert 0.7 < signal.LIGHT_LS06S(600) < 0.8

    def test_the_radar_covers_its_forty_centimetres(self):
        assert signal.RADAR_CM(0) == 0.0
        assert signal.RADAR_CM(20) == pytest.approx(0.5)
        assert signal.RADAR_CM(40) == 1.0

    def test_every_preset_is_reachable_by_name_and_is_a_stage(self):
        assert set(signal.PRESETS) == {"fsr402", "light", "loudness", "joystick", "radar"}
        for preset in signal.PRESETS.values():
            assert isinstance(preset, Stage)
            assert 0.0 <= preset(0) <= 1.0
