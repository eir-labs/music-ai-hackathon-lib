"""The bus, exercised over real UDP rather than against its dispatcher."""
from __future__ import annotations

import pytest

from kitlib.bus import Bus
from kitlib.contract import HOST, PORT


class TestDefaults:
    def test_it_lands_on_the_shared_port(self):
        bus = Bus()
        assert (bus.host, bus.port) == (HOST, PORT)
        assert bus.listen_port == PORT

    def test_the_listen_port_can_differ_for_forwarding(self):
        bus = Bus(port=9001, listen_port=9000)
        assert (bus.port, bus.listen_port) == (9001, 9000)

    def test_repr_names_both_ends(self):
        assert repr(Bus(port=9001, listen_port=9000)) == (
            "Bus(send=127.0.0.1:9001, listen=0.0.0.0:9000)")


class TestBinding:
    def test_constructing_a_bus_does_not_take_the_port(self):
        """A source and a sink on one laptop must not fight over 9000."""
        first = Bus(listen_port=0)
        assert first.bound is None
        second = Bus(listen_port=0)
        assert second.bound is None
        first.close()
        second.close()

    def test_the_port_is_readable_once_serving(self, listening):
        assert listening.bound is not None
        assert listening.bound[1] > 0

    def test_close_releases_the_port_for_another_bus(self):
        first = Bus(listen_port=0)
        first.start()
        port = first.bound[1]
        first.close()
        second = Bus(listen_port=port)
        second.start()
        assert second.bound[1] == port
        second.close()

    def test_it_works_as_a_context_manager(self):
        with Bus(listen_port=0) as bus:
            bus.start()
            assert bus.bound is not None
        assert bus.bound is None


class TestDelivery:
    def test_a_message_survives_the_round_trip(self, listening, sender, collector):
        listening.on("/sensor/radar", collector)
        sender.send("/sensor/radar", 12.5, 0.75)
        assert collector.wait_for(1)
        address, args = collector.messages[0]
        assert address == "/sensor/radar"
        assert args[0] == pytest.approx(12.5, rel=1e-6)
        assert args[1] == pytest.approx(0.75, rel=1e-6)

    def test_strings_and_numbers_travel_together(self, listening, sender, collector):
        listening.on("/wwise/rtpc", collector)
        sender.send("/wwise/rtpc", "Proximity", 0.5, 7)
        assert collector.wait_for(1)
        assert collector.messages[0][1] == ("Proximity", pytest.approx(0.5), 7)

    def test_a_message_with_no_arguments_is_legal(self, listening, sender, collector):
        """The Wwise stop verb takes nothing at all."""
        listening.on("/wwise/stop", collector)
        sender.send("/wwise/stop")
        assert collector.wait_for(1)
        assert collector.messages[0] == ("/wwise/stop", ())

    def test_unclaimed_addresses_are_ignored(self, listening, sender, collector):
        listening.on("/sensor/radar", collector)
        sender.send("/somewhere/else", 1)
        collector.settle()
        assert len(collector) == 0


class TestRouting:
    def test_a_glob_catches_a_whole_namespace(self, listening, sender, collector):
        listening.on("/sensor/*", collector)
        sender.send("/sensor/radar", 1)
        sender.send("/sensor/light", 2)
        sender.send("/wwise/rtpc", "X", 3)
        assert collector.wait_for(2)
        collector.settle()
        assert sorted(collector.addresses) == ["/sensor/light", "/sensor/radar"]

    def test_two_handlers_on_one_address_both_fire(self, listening, sender, collector):
        seen = []
        listening.on("/sensor/radar", collector)
        listening.on("/sensor/radar", lambda address, *args: seen.append(address))
        sender.send("/sensor/radar", 1)
        assert collector.wait_for(1)
        assert seen == ["/sensor/radar"]

    def test_the_default_handler_catches_what_nothing_claimed(
            self, listening, sender, collector):
        listening.on_default(collector)
        sender.send("/anything/at/all", 1)
        assert collector.wait_for(1)
        assert collector.messages[0][0] == "/anything/at/all"


class TestDecoratorForm:
    def test_on_registers_and_returns_the_function(self, listening, sender):
        seen = []

        @listening.on("/sensor/radar")
        def handle(address, *args):
            seen.append(args)

        assert callable(handle)
        sender.send("/sensor/radar", 4)
        for _ in range(200):
            if seen:
                break
            import time
            time.sleep(0.005)
        assert seen == [(4,)]

    def test_on_default_also_works_as_a_decorator(self, listening, sender, collector):
        listening.on_default()(collector)
        sender.send("/x", 1)
        assert collector.wait_for(1)


class TestLifecycle:
    def test_start_returns_a_running_daemon_thread(self, buses):
        bus = buses(listen_port=0)
        thread = bus.start()
        assert thread.is_alive() and thread.daemon

    def test_stop_ends_the_thread_but_keeps_the_socket(self, buses):
        bus = buses(listen_port=0)
        thread = bus.start()
        bus.stop()
        assert not thread.is_alive()
        assert bus.bound is not None

    def test_stop_and_close_are_safe_before_serving(self):
        bus = Bus(listen_port=0)
        bus.stop()
        bus.close()

    def test_close_is_idempotent(self, buses):
        bus = buses(listen_port=0)
        bus.start()
        bus.close()
        bus.close()
        assert bus.bound is None
