"""Mirroring the bus to Pd, SuperCollider, Godot, or another laptop."""
from __future__ import annotations

import pytest

from kitlib import signal
from kitlib.bus import Bus
from kitlib.sinks.forward import Forward


@pytest.fixture
def downstream(buses):
    """Something listening at the far end, with a collector already attached."""
    bus = buses(listen_port=0)
    bus.start()
    return bus


class TestConstruction:
    def test_it_needs_somewhere_to_send(self):
        with pytest.raises(ValueError):
            Forward()

    def test_route_is_chainable(self):
        forward = Forward(Bus(port=1))
        assert forward.route("/a").route("/b") is forward
        assert len(forward.routes) == 2

    def test_repr_names_the_targets_and_route_count(self):
        forward = Forward(Bus(host="10.0.0.5", port=9001)).route("/sensor/*")
        assert repr(forward) == "Forward(10.0.0.5:9001, 1 routes)"


class TestMirroring:
    def test_with_no_routes_it_mirrors_everything(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        Forward(buses(port=downstream.bound[1])).attach(listening)
        out = buses(port=listening.bound[1])
        out.send("/sensor/radar", 1)
        out.send("/wwise/rtpc", "X", 2)
        assert collector.wait_for(2)
        assert sorted(collector.addresses) == ["/sensor/radar", "/wwise/rtpc"]

    def test_a_pattern_narrows_what_is_forwarded(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        Forward(buses(port=downstream.bound[1])).route("/sensor/*").attach(listening)
        out = buses(port=listening.bound[1])
        out.send("/sensor/light", 1)
        out.send("/private/thing", 2)
        assert collector.wait_for(1)
        collector.settle()
        assert collector.addresses == ["/sensor/light"]

    def test_arguments_survive_unchanged(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        Forward(buses(port=downstream.bound[1])).attach(listening)
        buses(port=listening.bound[1]).send("/sensor/radar", 12.5, "tag", 3)
        assert collector.wait_for(1)
        assert collector.messages[0][1] == (pytest.approx(12.5), "tag", 3)


class TestRenaming:
    def test_an_address_can_be_rewritten_on_the_way(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        (Forward(buses(port=downstream.bound[1]))
         .route("/sensor/radar", to="/pd/prox").attach(listening))
        buses(port=listening.bound[1]).send("/sensor/radar", 1.0)
        assert collector.wait_for(1)
        assert collector.messages[0][0] == "/pd/prox"

    def test_each_route_keeps_its_own_rename(
            self, downstream, buses, collector, listening):
        """Routes registered in a loop must not share the last one's target."""
        downstream.on("/*", collector)
        (Forward(buses(port=downstream.bound[1]))
         .route("/sensor/light", to="/pd/one")
         .route("/sensor/force", to="/pd/two")
         .attach(listening))
        out = buses(port=listening.bound[1])
        out.send("/sensor/light", 1)
        out.send("/sensor/force", 2)
        assert collector.wait_for(2)
        assert sorted(collector.addresses) == ["/pd/one", "/pd/two"]


class TestConditioning:
    def test_a_stage_scales_the_first_argument(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        (Forward(buses(port=downstream.bound[1]))
         .route("/sensor/radar", stage=signal.RADAR_CM).attach(listening))
        buses(port=listening.bound[1]).send("/sensor/radar", 20.0, 0.9)
        assert collector.wait_for(1)
        distance, magnitude = collector.messages[0][1]
        assert distance == pytest.approx(0.5, rel=1e-6)
        assert magnitude == pytest.approx(0.9, rel=1e-6)

    def test_a_dropped_sample_is_not_forwarded(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        (Forward(buses(port=downstream.bound[1]))
         .route("/sensor/light", stage=signal.Deadband(100)).attach(listening))
        out = buses(port=listening.bound[1])
        out.send("/sensor/light", 10.0)
        out.send("/sensor/light", 11.0)
        assert collector.wait_for(1)
        collector.settle()
        assert len(collector) == 1

    def test_a_message_with_no_arguments_still_forwards(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        (Forward(buses(port=downstream.bound[1]))
         .route("/wwise/stop", stage=signal.RADAR_CM).attach(listening))
        buses(port=listening.bound[1]).send("/wwise/stop")
        assert collector.wait_for(1)
        assert collector.messages[0] == ("/wwise/stop", ())


class TestReshaping:
    """Two namespaces that count their arguments differently.

    ``/sensor/*`` puts its reading first. ``/wwise/*`` puts the name of the
    thing being driven first and takes a fixed number after it. Renaming alone
    does not bridge that, so ``lead`` and ``take`` exist to do the rest.
    """

    def test_lead_puts_fixed_arguments_on_the_front(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        (Forward(buses(port=downstream.bound[1]))
         .route("/sensor/radar", to="/wwise/rtpc", lead=("Proximity",))
         .attach(listening))
        buses(port=listening.bound[1]).send("/sensor/radar", 12.5)
        assert collector.wait_for(1)
        assert collector.messages[0] == ("/wwise/rtpc", ("Proximity", 12.5))

    def test_take_drops_the_readings_the_far_end_did_not_ask_for(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        (Forward(buses(port=downstream.bound[1]))
         .route("/sensor/radar", take=1).attach(listening))
        buses(port=listening.bound[1]).send("/sensor/radar", 12.5, 880.0)
        assert collector.wait_for(1)
        assert collector.messages[0][1] == (12.5,)

    def test_taking_more_than_arrived_is_not_an_error(
            self, downstream, buses, collector, listening):
        """A sensor that sometimes omits its second reading still forwards."""
        downstream.on("/*", collector)
        (Forward(buses(port=downstream.bound[1]))
         .route("/sensor/radar", take=5).attach(listening))
        buses(port=listening.bound[1]).send("/sensor/radar", 12.5)
        assert collector.wait_for(1)
        assert collector.messages[0][1] == (12.5,)

    def test_the_stage_runs_before_take_trims_and_lead_prepends(
            self, downstream, buses, collector, listening):
        """Order matters: conditioning applies to the reading, not to the name."""
        downstream.on("/*", collector)
        (Forward(buses(port=downstream.bound[1]))
         .route("/sensor/radar", to="/wwise/rtpc", lead=("Proximity",),
                take=1, stage=signal.RADAR_CM).attach(listening))
        buses(port=listening.bound[1]).send("/sensor/radar", 20.0, 880.0)
        assert collector.wait_for(1)
        address, (name, value) = collector.messages[0]
        assert (address, name) == ("/wwise/rtpc", "Proximity")
        assert value == pytest.approx(0.5)

    def test_neither_is_needed_to_mirror_a_namespace_unchanged(
            self, downstream, buses, collector, listening):
        downstream.on("/*", collector)
        Forward(buses(port=downstream.bound[1])).route("/sensor/*").attach(listening)
        buses(port=listening.bound[1]).send("/sensor/radar", 12.5, 880.0)
        assert collector.wait_for(1)
        assert collector.messages[0] == ("/sensor/radar", (12.5, 880.0))


class TestFanOut:
    def test_one_message_reaches_every_target(self, buses, listening):
        first, second = buses(listen_port=0), buses(listen_port=0)
        first.start()
        second.start()
        from tests.conftest import Collector
        seen_first, seen_second = Collector(), Collector()
        first.on("/*", seen_first)
        second.on("/*", seen_second)

        (Forward(buses(port=first.bound[1]), buses(port=second.bound[1]))
         .route("/sensor/*").attach(listening))
        buses(port=listening.bound[1]).send("/sensor/radar", 7)

        assert seen_first.wait_for(1)
        assert seen_second.wait_for(1)
        assert seen_first.messages == seen_second.messages
