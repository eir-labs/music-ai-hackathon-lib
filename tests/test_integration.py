"""The paths that cross tracks, end to end over a real socket.

Every other test file checks one component in isolation. These check the claims
the README makes about what happens when the components are chained, because
that is what six teams actually depend on: a Ch3 radar driving a Ch4 Wwise
session, an Arduino on one laptop reaching a bridge on another, a namespace
mirrored to a Pd patch. Nothing here is mocked except the hardware at the two
far ends. The bus in the middle is a real UDP socket.

These are also the guard rails for extending the kit. Add a verb to
``kitlib.contract`` and forget to wire it into the Wwise sink, and
``TestEveryPublishedVerbReachesWwise`` fails with the verb's own name in the
output. Add a source and its readings can be run through the same chain here to
prove they land on the contract rather than beside it.

The convention throughout: build the chain, run a terminating source, then wait
on the far end. Messages cross a socket and land on a server thread, so
asserting without waiting sees an empty log rather than a real failure.
"""
from __future__ import annotations

from typing import NamedTuple

import pytest

from doubles import frame_at_cm, note_on
from kitlib import chords, contract, signal
from kitlib.bus import Bus
from kitlib.sinks.forward import Forward
from kitlib.sinks.midi import MidiSink
from kitlib.sinks.wwise import WwiseSink
from kitlib.sources import arduino, midi, radar

#: One plausible value per argument name used in the contract, so a message can
#: be built from a Spec without the test knowing which verb it is looking at.
SAMPLE = {
    "EventName": "Play_Music",
    "RtpcName": "Proximity",
    "Group": "Weather",
    "State": "Rain",
    "float": 0.5,
    "gameObj": 7,
    "x": 1.0, "y": 2.0, "z": 3.0,
    "ChordName": "Cmaj7",
    "note": 60,
    "velocity": 100,
    "channel": 1,
    "controller": 74,
    "value": 64,
}

#: What each verb is supposed to become on the other side of the bridge.
WAAPI_FOR = {
    contract.EVENT: "ak.soundengine.postEvent",
    contract.RTPC: "ak.soundengine.setRTPCValue",
    contract.SWITCH: "ak.soundengine.setSwitch",
    contract.STATE: "ak.soundengine.setState",
    contract.POS: "ak.soundengine.setPosition",
    contract.STOP: "ak.soundengine.stopAll",
}

REGISTER = "ak.soundengine.registerGameObj"
RTPC_CALL = WAAPI_FOR[contract.RTPC]

#: What each MIDI verb is supposed to become at the port.
MIDI_FOR = {
    contract.MIDI_NOTE: "note_on",
    contract.MIDI_CHORD: "note_on",
    contract.MIDI_CC: "control_change",
    contract.MIDI_PANIC: None,      # releases only what is already sounding
}


def required(spec: contract.Spec) -> list:
    """The arguments a spec publishes as mandatory, with the optional ones left off."""
    return [SAMPLE[name] for name in spec.args if not name.endswith("?")]


def every(spec: contract.Spec) -> list:
    """Every argument a spec publishes, optional ones included."""
    return [SAMPLE[name.rstrip("?")] for name in spec.args]


class Bridge(NamedTuple):
    """A Wwise bridge and the two ends of the bus it sits on.

    The two buses are deliberately separate names. Handlers only fire on the
    one that is serving, so registering a mapping on the sending end is a
    silent no-op and the commonest way to write a test that proves nothing.
    """

    sink: WwiseSink
    listen: Bus     #: already serving; register handlers here
    send: Bus       #: points at it; sources and hand-sent messages go here


@pytest.fixture
def bridge(sink, listening) -> Bridge:
    """A Wwise bridge attached to a serving bus, with a sender pointed at it.

    This is the two-laptop arrangement collapsed onto one machine.
    """
    sink.attach(listening)
    return Bridge(sink, listening, Bus(port=listening.bound[1]))


class TestEveryPublishedVerbReachesWwise:
    """The contract is a promise about the wire, so it is tested on the wire.

    ``kitlib contract`` is what a team reads before writing a patch. If a verb
    prints there it has to work when sent, whether the sender is Pd, a
    SuperCollider ``NetAddr``, or another team's Python.
    """

    @pytest.mark.parametrize("address", sorted(contract.WWISE_SPECS))
    def test_the_published_shape_produces_the_right_waapi_call(self, address, bridge):
        sink, bus = bridge.sink, bridge.send
        spec = contract.SPECS[address]

        bus.send(address, *required(spec))

        assert sink.client.wait_for_of(WAAPI_FOR[address]), \
            f"{address} never became {WAAPI_FOR[address]}"

    @pytest.mark.parametrize("address", sorted(contract.WWISE_SPECS))
    def test_the_optional_arguments_are_genuinely_optional(self, address, bridge):
        """A ``?`` in the contract means a patch may omit it and still be heard."""
        sink, bus = bridge.sink, bridge.send
        spec = contract.SPECS[address]

        bus.send(address, *every(spec))
        bus.send(address, *required(spec))

        assert sink.client.wait_for_of(WAAPI_FOR[address], 2), \
            f"{address} was heard with its optional arguments but not without"

    def test_a_verb_with_no_arguments_at_all_is_heard(self, bridge):
        """``/wwise/stop`` with nothing after it stops the default object."""
        sink, bus = bridge.sink, bridge.send

        bus.send(contract.STOP)

        assert sink.client.wait_for_of("ak.soundengine.stopAll")
        assert sink.client.of("ak.soundengine.stopAll") == [{"gameObject": 1}]

    def test_an_invented_game_object_is_registered_before_it_is_used(self, bridge):
        """Wwise drops calls against an unknown object, so registration comes first."""
        sink, bus = bridge.sink, bridge.send

        bus.send(contract.EVENT, "Play_Music", 42)

        assert sink.client.wait_for_of("ak.soundengine.postEvent")
        uris = sink.client.uris()
        assert uris.index(REGISTER) < uris.index("ak.soundengine.postEvent")
        assert {"gameObject": 42, "name": "osc_42"} in sink.client.of(REGISTER)

    def test_a_bad_name_does_not_take_the_bridge_down_with_it(
            self, listening, waapi, capsys):
        """One team's typo must not stop the machine everyone else is sharing."""
        waapi.fail = True
        WwiseSink(waapi).attach(listening)
        bus = Bus(port=listening.bound[1])

        bus.send(contract.RTPC, "NoSuchRtpc", 0.5)
        bus.send(contract.EVENT, "Play_Music")

        assert waapi.wait_for(3)
        assert "WAAPI error" in capsys.readouterr().err


class TestRadarToWwise:
    """Ch3 to Ch4: the headline claim, that one team's sensor drives another's mix."""

    def test_a_reading_becomes_a_game_parameter(self, bridge, fake_board):
        sink, bus = bridge.sink, bridge.send
        sink.map_rtpc(bridge.listen, radar.ADDRESS, "Proximity")
        fake_board([frame_at_cm(12.5)])

        radar.run("COM3", bus)

        assert sink.client.wait_for_of(RTPC_CALL)
        assert sink.client.of("ak.soundengine.setRTPCValue") == [
            {"rtpc": "Proximity", "value": 12.5, "gameObject": 1}]

    def test_conditioning_happens_before_the_wire_not_after(
            self, bridge, fake_board):
        """What crosses the bus is already the 0..1 an RTPC wants.

        The scaling belongs to the source because the far end may be a Pd patch
        that has no idea what a centimetre is.
        """
        sink, bus = bridge.sink, bridge.send
        sink.map_rtpc(bridge.listen, radar.ADDRESS, "Proximity")
        fake_board([frame_at_cm(10.0)])

        radar.run("COM3", bus, stage=signal.RADAR_CM)

        assert sink.client.wait_for_of(RTPC_CALL)
        value = sink.client.of("ak.soundengine.setRTPCValue")[0]["value"]
        assert value == pytest.approx(0.25)

    def test_the_magnitude_rides_along_without_reaching_the_rtpc(
            self, bridge, fake_board):
        """``/sensor/radar`` carries ``<cm> <magnitude>``; only the distance maps.

        The magnitude is how a patch tells a real reflection from noise, so it
        stays on the bus for anyone who wants it.
        """
        sink, bus = bridge.sink, bridge.send
        sink.map_rtpc(bridge.listen, radar.ADDRESS, "Proximity")
        fake_board([frame_at_cm(20.0, magnitude=880.0)])

        radar.run("COM3", bus)

        assert sink.client.wait_for_of(RTPC_CALL)
        call = sink.client.of("ak.soundengine.setRTPCValue")[0]
        assert call["value"] == pytest.approx(20.0)
        assert 880.0 not in call.values()

    def test_a_rate_limited_source_does_not_flood_the_bridge(
            self, bridge, fake_board, clock):
        """650 Hz of radar is not 650 RTPC writes a second."""
        sink, bus = bridge.sink, bridge.send
        sink.map_rtpc(bridge.listen, radar.ADDRESS, "Proximity")
        fake_board([frame_at_cm(cm) for cm in (5, 6, 7, 8, 9, 10)])

        radar.run("COM3", bus,
                  stage=signal.RateLimit(60, time_fn=clock))

        assert sink.client.wait_for_of(RTPC_CALL)
        sink.client.settle()
        # The clock never advances, so only the first sample gets through.
        assert len(sink.client.of("ak.soundengine.setRTPCValue")) == 1


class TestArduinoToWwise:
    """One sketch, several sensors, each arriving under its own name."""

    def test_each_named_reading_lands_on_its_own_address(
            self, bridge, fake_serial):
        sink, bus = bridge.sink, bridge.send
        sink.map_rtpc(bridge.listen, contract.sensor("light"), "Brightness")
        sink.map_rtpc(bridge.listen, contract.sensor("force"), "Pressure")
        fake_serial(["light 600\n", "force 325\n"])

        arduino.run("COM5", bus=bus)

        assert sink.client.wait_for_of(RTPC_CALL, 2)
        calls = sink.client.of("ak.soundengine.setRTPCValue")
        assert {"rtpc": "Brightness", "value": 600.0, "gameObject": 1} in calls
        assert {"rtpc": "Pressure", "value": 325.0, "gameObject": 1} in calls

    def test_the_preset_ranges_from_the_setup_doc_hold_end_to_end(
            self, bridge, fake_serial):
        """The force sensor tops out near 650, so 325 is half travel, not a third.

        This is the number teams get wrong when they assume a 10-bit analog read
        runs to 1023. It is pinned here because the value Wwise receives is what
        the mix is built against.
        """
        sink, bus = bridge.sink, bridge.send
        sink.map_rtpc(bridge.listen, contract.sensor("force"), "Pressure")
        fake_serial(["force 325\n"])

        arduino.run("COM5", bus=bus, stages={"force": signal.FSR402})

        assert sink.client.wait_for_of(RTPC_CALL)
        assert sink.client.of("ak.soundengine.setRTPCValue")[0]["value"] == \
            pytest.approx(0.5)

    def test_banner_lines_from_the_sketch_do_not_reach_wwise(
            self, bridge, fake_serial):
        """Sketches print greetings on boot. They must not become messages."""
        sink, bus = bridge.sink, bridge.send
        sink.map_rtpc(bridge.listen, contract.sensor("light"), "Brightness")
        fake_serial(["Grove kit ready\n", "--------\n", "light 600\n"])

        arduino.run("COM5", bus=bus)

        assert sink.client.wait_for_of(RTPC_CALL)
        sink.client.settle()
        assert len(sink.client.of("ak.soundengine.setRTPCValue")) == 1


class TestAcrossMachines:
    """The other laptop. Forwarding is what makes the bus bigger than one host."""

    def test_a_namespace_arrives_unchanged_on_the_far_side(
            self, buses, listening, collector, fake_board):
        """A radar on one machine, a Pd patch on another, nothing rewritten."""
        far = listening
        far.on("/sensor/*", collector)

        near = buses(listen_port=0)
        Forward(buses(port=far.bound[1])).route("/sensor/*").attach(near)
        near.start()

        fake_board([frame_at_cm(12.5, magnitude=880.0)])
        radar.run("COM3", buses(port=near.bound[1]))

        assert collector.wait_for(1)
        assert collector.messages[0][0] == radar.ADDRESS
        assert collector.messages[0][1] == pytest.approx((12.5, 880.0))

    def test_a_sensor_can_be_reshaped_into_a_wwise_verb_on_the_way(
            self, bridge, buses):
        """Crossing namespaces needs the RTPC name added and the extra reading dropped.

        This is the arrangement where the receiving laptop runs a bare bridge
        with no ``--map`` of its own, so the sending side does the shaping.
        """
        sink, wwise_bus = bridge.sink, bridge.send

        near = buses(listen_port=0)
        Forward(buses(port=wwise_bus.port)).route(
            radar.ADDRESS, to=contract.RTPC, lead=("Proximity",), take=1,
            stage=signal.RADAR_CM).attach(near)
        near.start()

        buses(port=near.bound[1]).send(radar.ADDRESS, 10.0, 880.0)

        assert sink.client.wait_for_of(RTPC_CALL)
        assert sink.client.of("ak.soundengine.setRTPCValue") == [
            {"rtpc": "Proximity", "value": pytest.approx(0.25), "gameObject": 1}]

    def test_renaming_alone_misnames_the_rtpc_after_the_reading(
            self, bridge, buses):
        """The trap, pinned so the diagnosis is written down somewhere.

        ``/sensor/radar`` carries its value first and ``/wwise/rtpc`` wants its
        name first, so a bare rename sets a parameter called "10.0". Wwise
        accepts the call and nothing appears to be wrong, which is why this is
        worth a test rather than a comment.
        """
        sink, wwise_bus = bridge.sink, bridge.send

        near = buses(listen_port=0)
        Forward(buses(port=wwise_bus.port)).route(
            radar.ADDRESS, to=contract.RTPC).attach(near)
        near.start()

        buses(port=near.bound[1]).send(radar.ADDRESS, 10.0, 880.0)

        assert sink.client.wait_for_of(RTPC_CALL)
        call = sink.client.of("ak.soundengine.setRTPCValue")[0]
        assert call["rtpc"] == "10.0"        # the distance, used as a name
        assert call["value"] == 880.0        # the magnitude, used as the value

    def test_one_source_reaches_several_machines_at_once(
            self, buses, listening, collector, fake_board):
        """Pd here, Godot there, the room's projection over the network."""
        pd, godot = buses(listen_port=0), buses(listen_port=0)
        for machine in (pd, godot):
            machine.on("/sensor/*", collector)
            machine.start()

        near = listening
        Forward(buses(port=pd.bound[1]),
                buses(port=godot.bound[1])).route("/sensor/*").attach(near)

        fake_board([frame_at_cm(12.5)])
        radar.run("COM3", buses(port=near.bound[1]))

        assert collector.wait_for(2)
        assert collector.addresses == [radar.ADDRESS, radar.ADDRESS]


@pytest.fixture
def keyboard(fake_midi, listening):
    """A MIDI sink attached to a serving bus, with a sender pointed at it."""
    port = fake_midi()
    sink = MidiSink(port)
    sink.attach(listening)
    return Bridge(sink, listening, Bus(port=listening.bound[1])), port


class TestEveryPublishedMidiVerbReachesThePort:
    """The same promise as the Wwise verbs, for the other sink.

    Add a verb to ``contract.MIDI_SPECS`` and forget to wire it into
    ``MidiSink.attach`` and these fail with the verb's own name.
    """

    @pytest.mark.parametrize("address", sorted(contract.MIDI_SPECS))
    def test_the_published_shape_is_accepted_without_error(
            self, address, keyboard, capsys):
        bridge, port = keyboard
        spec = contract.SPECS[address]

        bridge.send.send(address, *required(spec))

        expected = MIDI_FOR[address]
        if expected is None:               # panic releases nothing when nothing sounds
            port.settle()
        else:
            assert port.wait_for(1), f"{address} produced no MIDI at all"
            assert port.sent[0].type == expected
        assert "MIDI error" not in capsys.readouterr().err

    @pytest.mark.parametrize("address", sorted(contract.MIDI_SPECS))
    def test_the_optional_arguments_are_genuinely_optional(self, address, keyboard):
        """A ``?`` in the contract means a patch may omit it and still be heard."""
        bridge, port = keyboard
        spec = contract.SPECS[address]

        bridge.send.send(address, *every(spec))
        bridge.send.send(address, *required(spec))

        if MIDI_FOR[address] is not None:
            assert port.wait_for(2)

    def test_a_chord_name_arrives_as_the_notes_of_that_chord(self, keyboard):
        bridge, port = keyboard

        bridge.send.send(contract.MIDI_CHORD, "Cmaj7")

        assert port.wait_for(4)
        assert port.notes_on() == chords.spell("Cmaj7")


class TestChordCatToTheRestOfTheEvent:
    """Ch6 to anywhere: a chord played on the kit reaching another track."""

    def test_a_chord_played_on_the_keyboard_lands_on_the_bus_named(
            self, fake_midi, listening, collector, buses):
        listening.on(contract.CHORD_NAME, collector)
        fake_midi(incoming=[note_on(n) for n in chords.spell("Am7")])

        midi.run(bus=buses(port=listening.bound[1]))

        assert collector.wait_for(1)
        assert collector.messages[-1][1] == ("Am7", 9, "m7")

    def test_a_chord_can_drive_a_wwise_switch_without_anyone_knowing_midi(
            self, bridge, fake_midi, buses):
        """The whole point of a shared namespace.

        A Ch4 team forwards ``/chord/name`` into their own switch group. They
        never learn what a MIDI note number is, and the Ch6 team never learns
        what a switch is.
        """
        sink, wwise_bus = bridge.sink, bridge.send

        near = buses(listen_port=0)
        Forward(buses(port=wwise_bus.port)).route(
            contract.CHORD_NAME, to=contract.SWITCH,
            lead=("Harmony",), take=1).attach(near)
        near.start()

        fake_midi(incoming=[note_on(n) for n in chords.spell("Am7")])
        midi.run(bus=buses(port=near.bound[1]))

        # Played one key at a time, the hand passes through Am on the way to
        # Am7, and every step is published. What matters is where it lands.
        assert sink.client.wait_for_of("ak.soundengine.setSwitch", 2)
        assert sink.client.of("ak.soundengine.setSwitch")[-1] == {
            "switchGroup": "Harmony", "switchState": "Am7", "gameObject": 1}

    def test_a_radar_can_play_the_keyboard_through_a_progression(
            self, keyboard, fake_board, buses):
        """Ch3 to Ch6, the accessible-instrument shape.

        A hand moving in front of a radar walks a chord progression. Nothing in
        the chain knows about anything else in it.
        """
        bridge, port = keyboard
        bridge.sink.map_chord(bridge.listen, radar.ADDRESS, ["C", "Am", "F", "G"])
        fake_board([frame_at_cm(30.0)])     # three quarters of the way along

        radar.run("COM3", bridge.send, stage=signal.RADAR_CM)

        assert port.wait_for(len(chords.spell("G")))
        assert port.notes_on() == chords.spell("G")

    def test_the_keyboard_and_wwise_can_share_one_bus(
            self, fake_midi, listening, waapi, buses):
        """Ch4 and Ch6 on one laptop, which is what the kit table looks like."""
        port = fake_midi()
        MidiSink(port).attach(listening)
        WwiseSink(waapi).attach(listening)
        bus = buses(port=listening.bound[1])

        bus.send(contract.MIDI_CHORD, "C")
        bus.send(contract.RTPC, "Proximity", 0.5)

        assert port.wait_for(3)
        assert waapi.wait_for_of(RTPC_CALL)
        assert port.notes_on() == chords.spell("C")


class TestTheBusStaysUsableWhileShared:
    """Several tracks on one port is the normal case at the event, not the odd one."""

    def test_a_wwise_bridge_and_a_monitor_both_see_the_same_message(
            self, sink, listening, collector):
        """``kitlib monitor`` is the first debugging step, so it must not steal traffic."""
        sink.attach(listening)
        listening.on("/wwise/*", collector)
        bus = Bus(port=listening.bound[1])

        bus.send(contract.RTPC, "Proximity", 0.5)

        assert sink.client.wait_for_of(RTPC_CALL)
        assert collector.wait_for(1)
        assert collector.messages[0][1] == pytest.approx(("Proximity", 0.5))

    def test_a_private_track_namespace_is_ignored_by_the_bridge(
            self, bridge, collector):
        """The contract tells teams to prefix their own traffic, e.g. ``/ch5/...``.

        Doing so has to be free: the Wwise bridge should not see it, and no
        other track's handlers should either.
        """
        sink, bus = bridge.sink, bridge.send

        bus.send("/ch5/pose/left_hand", 0.2, 0.4, 0.6)
        bus.send(contract.EVENT, "Play_Music")

        assert sink.client.wait_for_of("ak.soundengine.postEvent")
        sink.client.settle()
        assert sink.client.uris() == [REGISTER, "ak.soundengine.postEvent"]
        assert collector.messages == []
