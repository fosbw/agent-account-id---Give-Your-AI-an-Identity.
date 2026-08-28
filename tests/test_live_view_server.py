from __future__ import annotations

import json
from urllib.request import Request, urlopen

from agentguard.live_view import LiveViewHub
from agentguard.live_view_server import LiveViewServer


def test_live_view_server_serves_safe_events_and_controls() -> None:
    hub = LiveViewHub()
    hub.start("session-server")
    hub.publish_state("session-server", "running", page="safe page otp=123456")
    hub.publish_frame("session-server", frame_ref="frame://opaque-1")
    server = LiveViewServer(hub)
    base = server.start()
    try:
        with urlopen(base + "health", timeout=2) as response:
            assert json.loads(response.read()) == {"ok": True}

        with urlopen(base + "api/events?session_id=session-server&after=0", timeout=2) as response:
            payload = json.loads(response.read())
        assert len(payload["events"]) == 3
        assert "123456" not in json.dumps(payload)
        assert payload["events"][-1]["frame_ref"] == "frame://opaque-1"

        request = Request(
            base + "api/control",
            data=json.dumps({"session_id": "session-server", "action": "pause"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            control = json.loads(response.read())
        assert control["state"] == "paused"
    finally:
        server.stop()


def test_live_view_server_is_local_only() -> None:
    hub = LiveViewHub()
    try:
        LiveViewServer(hub, host="0.0.0.0")
    except ValueError:
        pass
    else:
        raise AssertionError("non-local bind must be rejected")
