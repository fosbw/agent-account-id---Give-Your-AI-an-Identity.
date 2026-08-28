from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from agentguard.accounts import AccountError
from agentguard.live_view import LiveViewHub


def test_live_view_publishes_safe_state_and_frame_events() -> None:
    hub = LiveViewHub()
    started = hub.start("session-a")
    state = hub.publish_state(
        "session-a",
        "verification_required",
        current_url="https://example.test/verify",
        page="Phone verification otp=123456 password=hidden",
        overlay="OTP required; phone=+201234567890",
    )
    frame = hub.publish_frame(
        "session-a",
        current_url="https://example.test/verify",
        page="verification page otp=123456",
        frame_ref="frame://opaque-1",
    )

    assert started.sequence == 1
    assert state.sequence == 2
    assert frame is not None
    assert frame.sequence == 3
    assert "123456" not in str(state.to_dict())
    assert "+201234567890" not in str(state.to_dict())
    assert "hidden" not in str(state.to_dict())
    assert frame.frame_ref == "frame://opaque-1"
    assert all(event.to_dict()["secrets_exposed"] is False for event in hub.events("session-a"))


def test_live_view_controls_pause_resume_and_kill() -> None:
    hub = LiveViewHub()
    hub.start("session-controls")
    hub.publish_state("session-controls", "running")

    paused = hub.control("session-controls", "pause")
    assert paused.state == "paused"
    assert hub.publish_frame("session-controls", page="hidden") is None

    resumed = hub.control("session-controls", "resume")
    assert resumed.state == "running"
    assert hub.publish_frame("session-controls", page="visible") is not None

    killed = hub.control("session-controls", "kill")
    assert killed.state == "killed"
    assert hub.publish_frame("session-controls", page="hidden") is None

    with pytest.raises(AccountError, match="terminated"):
        hub.control("session-controls", "resume")


def test_live_view_event_cursor_and_bounded_history() -> None:
    hub = LiveViewHub(max_events_per_session=3)
    hub.start("session-history")
    hub.publish_state("session-history", "running")
    hub.publish_state("session-history", "paused")
    hub.publish_state("session-history", "running")

    events = hub.events("session-history")
    assert [event.sequence for event in events] == [2, 3, 4]
    assert [event.sequence for event in hub.events("session-history", after_sequence=2)] == [3, 4]


def test_live_view_rejects_raw_or_invalid_frame_reference() -> None:
    hub = LiveViewHub()
    hub.start("session-ref")

    with pytest.raises(ValueError, match="opaque reference"):
        hub.publish_frame("session-ref", frame_ref="data:image/png;base64,raw-bytes")

    with pytest.raises(ValueError, match="opaque reference"):
        hub.publish_frame("session-ref", frame_ref="x" * 257)


def test_live_view_isolates_concurrent_sessions() -> None:
    hub = LiveViewHub()
    session_ids = [f"session-{index}" for index in range(16)]
    for session_id in session_ids:
        hub.start(session_id)

    def publish(session_id: str):
        event = hub.publish_frame(
            session_id,
            current_url=f"https://example.test/{session_id}",
            page=f"safe page for {session_id}",
            frame_ref=f"frame://{session_id}",
        )
        assert event is not None
        return session_id, event

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(publish, session_ids))

    assert {session_id for session_id, _event in results} == set(session_ids)
    for session_id, event in results:
        assert event.session_id == session_id
        assert session_id in (event.page or "")
        assert event.page == f"safe page for {session_id}"
