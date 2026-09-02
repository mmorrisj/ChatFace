"""States, events, and the derived device state for a conversation session.

The privacy properties of the device are defined here: `device_state_for` is the
single place that decides whether the microphone and camera are open, derived
purely from the session state. Nothing else in the codebase may open them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SessionState(StrEnum):
    """Where a conversation currently is."""

    IDLE = "idle"
    """Nothing happening. Screen is ambient, mic and camera are off."""

    WAKE = "wake"
    """The child tapped. Camera grabs a frame or two to identify them."""

    LISTENING = "listening"
    """Mic is open and we are waiting for (or receiving) child speech."""

    THINKING = "thinking"
    """The child finished a turn; a response is being produced."""

    SPEAKING = "speaking"
    """Audio is playing back through the browser."""

    OFFLINE = "offline"
    """The browser is disconnected or a dependency is unreachable."""


class Event(StrEnum):
    """Things that can happen to a session."""

    TAP = "tap"
    IDENTITY_RESOLVED = "identity_resolved"
    IDENTITY_TIMEOUT = "identity_timeout"
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    RESPONSE_READY = "response_ready"
    PLAYBACK_DONE = "playback_done"
    SILENCE_TIMEOUT = "silence_timeout"
    STOP = "stop"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"


@dataclass(frozen=True, slots=True)
class DeviceState:
    """Which sensors are live. Derived from `SessionState`, never set directly."""

    mic_open: bool
    camera_open: bool


# The camera is open only during WAKE -- roughly one second per conversation,
# just long enough to grab frames for identification. The mic stays open through
# THINKING and SPEAKING so the child can interrupt (barge-in).
_DEVICE_STATES: dict[SessionState, DeviceState] = {
    SessionState.IDLE: DeviceState(mic_open=False, camera_open=False),
    SessionState.WAKE: DeviceState(mic_open=True, camera_open=True),
    SessionState.LISTENING: DeviceState(mic_open=True, camera_open=False),
    SessionState.THINKING: DeviceState(mic_open=True, camera_open=False),
    SessionState.SPEAKING: DeviceState(mic_open=True, camera_open=False),
    SessionState.OFFLINE: DeviceState(mic_open=False, camera_open=False),
}


def device_state_for(state: SessionState) -> DeviceState:
    """Return which sensors are live in `state`."""
    return _DEVICE_STATES[state]
