"""The activation state machine.

Deliberately synchronous and side-effect free: `handle` takes an event and
returns a transition. Timers, sockets, and hardware live outside and feed events
in. That keeps the whole conversation lifecycle testable with no camera, no
microphone, and no clock.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from chatface.session.states import DeviceState, Event, SessionState, device_state_for

# Explicit transition table: (from state, event) -> to state.
# Anything not listed is ignored, which makes stray events from a flaky browser
# harmless rather than a crash.
_TRANSITIONS: dict[tuple[SessionState, Event], SessionState] = {
    # A tap is the only way into a conversation.
    (SessionState.IDLE, Event.TAP): SessionState.WAKE,
    # Identification never blocks the conversation: either outcome, or the
    # timeout, moves us on. The mic is already open throughout.
    (SessionState.WAKE, Event.IDENTITY_RESOLVED): SessionState.LISTENING,
    (SessionState.WAKE, Event.IDENTITY_TIMEOUT): SessionState.LISTENING,
    (SessionState.WAKE, Event.SPEECH_START): SessionState.LISTENING,
    # The conversation loop.
    (SessionState.LISTENING, Event.SPEECH_END): SessionState.THINKING,
    (SessionState.THINKING, Event.RESPONSE_READY): SessionState.SPEAKING,
    (SessionState.SPEAKING, Event.PLAYBACK_DONE): SessionState.LISTENING,
    # Barge-in: the child talking over the response cuts it short.
    (SessionState.SPEAKING, Event.SPEECH_START): SessionState.LISTENING,
    (SessionState.THINKING, Event.SPEECH_START): SessionState.LISTENING,
    # Ways out.
    (SessionState.LISTENING, Event.SILENCE_TIMEOUT): SessionState.IDLE,
    (SessionState.WAKE, Event.SILENCE_TIMEOUT): SessionState.IDLE,
    (SessionState.OFFLINE, Event.CONNECTION_RESTORED): SessionState.IDLE,
}

# STOP and CONNECTION_LOST apply from any live state.
_ALWAYS: dict[Event, SessionState] = {
    Event.STOP: SessionState.IDLE,
    Event.CONNECTION_LOST: SessionState.OFFLINE,
}


@dataclass(frozen=True, slots=True)
class Transition:
    """A state change that actually happened."""

    event: Event
    frm: SessionState
    to: SessionState
    device: DeviceState


class SessionMachine:
    """Tracks one conversation's state.

    Args:
        on_transition: Called after each accepted transition, for broadcasting
            the new state to the browser. Must not raise.
    """

    def __init__(
        self,
        on_transition: Callable[[Transition], None] | None = None,
    ) -> None:
        self._state = SessionState.IDLE
        self._on_transition = on_transition

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def device(self) -> DeviceState:
        """Which sensors are currently live."""
        return device_state_for(self._state)

    def handle(self, event: Event) -> Transition | None:
        """Apply `event`. Returns the transition, or None if it did not apply.

        A transition to the state we are already in is treated as a no-op so
        that repeated taps or duplicate socket messages do not re-fire side
        effects.
        """
        target = _ALWAYS.get(event) or _TRANSITIONS.get((self._state, event))
        if target is None or target is self._state:
            return None

        transition = Transition(
            event=event,
            frm=self._state,
            to=target,
            device=device_state_for(target),
        )
        self._state = target
        if self._on_transition is not None:
            self._on_transition(transition)
        return transition
