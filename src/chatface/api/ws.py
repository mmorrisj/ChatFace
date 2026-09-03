"""WebSocket endpoint driving one kiosk browser.

The browser is the only client. It sends events (taps, speech boundaries,
playback completion) and receives state updates, which it renders as the face.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from chatface.config import settings
from chatface.session import (
    Event,
    SessionMachine,
    SessionState,
    Transition,
    device_state_for,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Events the browser is allowed to raise. The CONNECTION_* events are ours.
_CLIENT_EVENTS = frozenset(
    {
        Event.TAP,
        Event.SPEECH_START,
        Event.SPEECH_END,
        Event.RESPONSE_READY,
        Event.PLAYBACK_DONE,
        Event.STOP,
    }
)


def _timeouts() -> dict[SessionState, tuple[float, Event]]:
    """How long each state may sit before it times out on its own."""
    return {
        SessionState.WAKE: (settings.identity_timeout_s, Event.IDENTITY_TIMEOUT),
        SessionState.LISTENING: (settings.silence_timeout_s, Event.SILENCE_TIMEOUT),
    }


class Connection:
    """Owns the state machine and its timers for one browser connection."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._outbox: asyncio.Queue[Transition] = asyncio.Queue()
        self._machine = SessionMachine(on_transition=self._outbox.put_nowait)
        self._timer: asyncio.Task[None] | None = None

    async def run(self) -> None:
        """Pump client events and outbound state updates until disconnect."""
        await self._send_state(self._machine.state)
        sender = asyncio.create_task(self._send_loop())
        try:
            await self._receive_loop()
        finally:
            sender.cancel()
            self._cancel_timer()
            with contextlib.suppress(asyncio.CancelledError):
                await sender

    async def _receive_loop(self) -> None:
        while True:
            try:
                message = await self._ws.receive_json()
            except WebSocketDisconnect:
                return
            raw = message.get("event") if isinstance(message, dict) else None
            if not isinstance(raw, str):
                logger.warning("ignoring malformed message %r", message)
                continue
            try:
                event = Event(raw)
            except ValueError:
                logger.warning("ignoring unknown event %r", raw)
                continue
            if event not in _CLIENT_EVENTS:
                logger.warning("ignoring client-forbidden event %s", event)
                continue
            self._apply(event)

    async def _send_loop(self) -> None:
        while True:
            transition = await self._outbox.get()
            with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                await self._send_state(transition.to)

    def _apply(self, event: Event) -> None:
        """Feed the machine, and reset the deadline if the state changed."""
        if self._machine.handle(event) is not None:
            self._arm_timer()

    def _arm_timer(self) -> None:
        self._cancel_timer()
        entry = _timeouts().get(self._machine.state)
        if entry is None:
            return
        seconds, event = entry
        self._timer = asyncio.create_task(self._fire_after(seconds, event))

    async def _fire_after(self, seconds: float, event: Event) -> None:
        await asyncio.sleep(seconds)
        # Clear the handle before re-entering _apply, so the re-arm below does
        # not try to cancel the task it is running on.
        self._timer = None
        self._apply(event)

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    async def _send_state(self, state: SessionState) -> None:
        device = device_state_for(state)
        await self._ws.send_json(
            {
                "state": state.value,
                "mic_open": device.mic_open,
                "camera_open": device.camera_open,
            }
        )


@router.websocket("/ws")
async def session_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await Connection(websocket).run()
