"""The whole conversation lifecycle, exercised with no hardware and no clock."""

from __future__ import annotations

import pytest

from chatface.session import (
    Event,
    SessionMachine,
    SessionState,
    Transition,
    device_state_for,
)


def drive(machine: SessionMachine, *events: Event) -> None:
    for event in events:
        machine.handle(event)


def test_a_tap_is_the_only_way_into_a_conversation() -> None:
    machine = SessionMachine()
    for event in Event:
        if event in (Event.TAP, Event.CONNECTION_LOST):
            continue
        assert machine.handle(event) is None
        assert machine.state is SessionState.IDLE

    assert machine.handle(Event.TAP) is not None
    assert machine.state is SessionState.WAKE


def test_full_conversation_round_trip() -> None:
    machine = SessionMachine()
    drive(machine, Event.TAP, Event.IDENTITY_RESOLVED)
    assert machine.state is SessionState.LISTENING

    drive(machine, Event.SPEECH_END)
    assert machine.state is SessionState.THINKING

    drive(machine, Event.RESPONSE_READY)
    assert machine.state is SessionState.SPEAKING

    drive(machine, Event.PLAYBACK_DONE)
    assert machine.state is SessionState.LISTENING


def test_identification_never_blocks_the_conversation() -> None:
    """A slow or failed face lookup must not strand the child in WAKE."""
    machine = SessionMachine()
    drive(machine, Event.TAP, Event.IDENTITY_TIMEOUT)
    assert machine.state is SessionState.LISTENING

    # Talking before identification resolves also moves things along.
    other = SessionMachine()
    drive(other, Event.TAP, Event.SPEECH_START)
    assert other.state is SessionState.LISTENING


@pytest.mark.parametrize("interrupted", [SessionState.THINKING, SessionState.SPEAKING])
def test_child_can_barge_in(interrupted: SessionState) -> None:
    machine = SessionMachine()
    drive(machine, Event.TAP, Event.IDENTITY_RESOLVED, Event.SPEECH_END)
    if interrupted is SessionState.SPEAKING:
        drive(machine, Event.RESPONSE_READY)
    assert machine.state is interrupted

    drive(machine, Event.SPEECH_START)
    assert machine.state is SessionState.LISTENING


def test_silence_ends_the_session() -> None:
    machine = SessionMachine()
    drive(machine, Event.TAP, Event.IDENTITY_RESOLVED, Event.SILENCE_TIMEOUT)
    assert machine.state is SessionState.IDLE


def test_stop_and_disconnect_apply_from_every_state() -> None:
    for state in SessionState:
        if state is SessionState.IDLE:
            continue
        machine = SessionMachine()
        machine._state = state  # noqa: SLF001 - reaching a state directly is the point

        machine.handle(Event.STOP)
        assert machine.state is SessionState.IDLE

        machine._state = state  # noqa: SLF001
        machine.handle(Event.CONNECTION_LOST)
        assert machine.state is SessionState.OFFLINE


def test_repeated_events_are_no_ops() -> None:
    """Duplicate socket messages and double taps must not re-fire side effects."""
    seen: list[Transition] = []
    machine = SessionMachine(on_transition=seen.append)

    machine.handle(Event.TAP)
    machine.handle(Event.TAP)
    assert len(seen) == 1

    machine.handle(Event.STOP)
    machine.handle(Event.STOP)
    assert len(seen) == 2


def test_transition_reports_the_device_state_it_lands_in() -> None:
    machine = SessionMachine()
    transition = machine.handle(Event.TAP)
    assert transition is not None
    assert transition.frm is SessionState.IDLE
    assert transition.to is SessionState.WAKE
    assert transition.device == device_state_for(SessionState.WAKE)


class TestPrivacyInvariants:
    """The sensor rules the device's privacy claims rest on."""

    def test_idle_and_offline_have_both_sensors_closed(self) -> None:
        for state in (SessionState.IDLE, SessionState.OFFLINE):
            device = device_state_for(state)
            assert not device.mic_open
            assert not device.camera_open

    def test_camera_opens_only_for_identification(self) -> None:
        camera_states = [s for s in SessionState if device_state_for(s).camera_open]
        assert camera_states == [SessionState.WAKE]

    def test_mic_stays_open_through_a_response_for_barge_in(self) -> None:
        for state in (SessionState.LISTENING, SessionState.THINKING, SessionState.SPEAKING):
            assert device_state_for(state).mic_open

    def test_every_state_has_a_defined_device_state(self) -> None:
        for state in SessionState:
            device_state_for(state)

    def test_no_sensor_is_live_before_a_tap(self) -> None:
        machine = SessionMachine()
        assert not machine.device.mic_open
        assert not machine.device.camera_open

    def test_sensors_close_again_when_the_session_ends(self) -> None:
        machine = SessionMachine()
        drive(machine, Event.TAP, Event.IDENTITY_RESOLVED, Event.STOP)
        assert not machine.device.mic_open
        assert not machine.device.camera_open
