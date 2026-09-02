"""End-to-end checks over the WebSocket the kiosk browser actually speaks."""

from __future__ import annotations

from fastapi.testclient import TestClient

from chatface.main import app


def test_kiosk_page_and_health_are_served() -> None:
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        page = client.get("/")
        assert page.status_code == 200
        assert "ChatFace" in page.text


def test_socket_reports_initial_state_with_sensors_closed() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        assert socket.receive_json() == {
            "state": "idle",
            "mic_open": False,
            "camera_open": False,
        }


def test_tap_wakes_the_session_and_opens_the_camera() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_json({"event": "tap"})
        assert socket.receive_json() == {
            "state": "wake",
            "mic_open": True,
            "camera_open": True,
        }


def test_browser_cannot_forge_internal_events() -> None:
    """Only the server may decide that identification or a timeout happened."""
    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_json({"event": "tap"})
        socket.receive_json()

        socket.send_json({"event": "identity_resolved"})
        socket.send_json({"event": "silence_timeout"})
        socket.send_json({"event": "nonsense"})
        # None of those moved us; a legitimate event still gets through.
        socket.send_json({"event": "speech_start"})
        assert socket.receive_json()["state"] == "listening"


def test_stop_closes_every_sensor() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_json({"event": "tap"})
        socket.receive_json()
        socket.send_json({"event": "stop"})
        final = socket.receive_json()
        assert final["state"] == "idle"
        assert not final["mic_open"]
        assert not final["camera_open"]
