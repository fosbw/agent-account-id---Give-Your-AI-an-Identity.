from __future__ import annotations

import re
import time
from dataclasses import dataclass
from threading import RLock
from typing import Literal

from .accounts import AccountError
from .redaction import Redactor


LiveViewState = Literal[
    "idle",
    "starting",
    "running",
    "paused",
    "verification_required",
    "stopped",
    "killed",
    "failed",
]
LiveViewEventKind = Literal["state", "frame", "control"]

# Live view must not expose values that the generic redactor cannot identify
# from context alone. The view publishes status and safe labels, never raw frame
# bytes or provider credentials.
_LIVE_SENSITIVE_PATTERNS = (
    (re.compile(r"(?i)(otp|one[- ]time password|verification code)\s*[=:]\s*[^\s,;]+"), r"\1=[REDACTED_VERIFICATION_CODE]"),
    (re.compile(r"(?i)(phone|phone number|mobile)\s*[=:]\s*[^\s,;]+"), r"\1=[REDACTED_PHONE]"),
)


@dataclass(frozen=True)
class LiveViewEvent:
    session_id: str
    sequence: int
    kind: LiveViewEventKind
    state: LiveViewState
    current_url: str | None = None
    page: str | None = None
    overlay: str | None = None
    frame_ref: str | None = None
    created_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "live_view_event",
            "session_id": self.session_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "state": self.state,
            "current_url": self.current_url,
            "page": self.page,
            "overlay": self.overlay,
            "frame_ref": self.frame_ref,
            "created_at": self.created_at,
            "secrets_exposed": False,
        }


@dataclass
class _LiveSession:
    session_id: str
    state: LiveViewState = "idle"
    sequence: int = 0
    events: list[LiveViewEvent] | None = None

    def __post_init__(self) -> None:
        if self.events is None:
            self.events = []


class LiveViewHub:
    """Thread-safe local live-view event hub for a browser session.

    This is the control/data contract consumed by a future UI or streaming
    transport. It deliberately stores safe metadata and opaque frame references,
    not screenshots, passwords, cookies, tokens, or verification values.
    """

    def __init__(self, max_events_per_session: int = 256):
        if max_events_per_session <= 0:
            raise ValueError("max_events_per_session must be greater than zero")
        self.max_events_per_session = max_events_per_session
        self._sessions: dict[str, _LiveSession] = {}
        self._lock = RLock()
        self._redactor = Redactor()

    def start(self, session_id: str) -> LiveViewEvent:
        with self._lock:
            if session_id in self._sessions and self._sessions[session_id].state not in {"stopped", "killed", "failed"}:
                raise AccountError("live view session is already active")
            self._sessions[session_id] = _LiveSession(session_id=session_id)
            return self._publish_locked(session_id, "state", "starting")

    def publish_state(
        self,
        session_id: str,
        state: LiveViewState,
        *,
        current_url: str | None = None,
        page: str | None = None,
        overlay: str | None = None,
    ) -> LiveViewEvent:
        with self._lock:
            self._require_session(session_id)
            return self._publish_locked(
                session_id,
                "state",
                state,
                current_url=current_url,
                page=page,
                overlay=overlay,
            )

    def publish_frame(
        self,
        session_id: str,
        *,
        current_url: str | None = None,
        page: str | None = None,
        frame_ref: str | None = None,
    ) -> LiveViewEvent | None:
        """Publish a safe frame descriptor; never accept raw screenshot bytes."""
        with self._lock:
            session = self._require_session(session_id)
            if session.state in {"paused", "stopped", "killed", "failed"}:
                return None
            return self._publish_locked(
                session_id,
                "frame",
                session.state if session.state != "idle" else "running",
                current_url=current_url,
                page=page,
                frame_ref=frame_ref,
            )

    def control(self, session_id: str, action: Literal["pause", "resume", "kill"]) -> LiveViewEvent:
        with self._lock:
            session = self._require_session(session_id)
            if action == "pause":
                next_state: LiveViewState = "paused"
            elif action == "resume":
                if session.state in {"stopped", "killed", "failed"}:
                    raise AccountError("cannot resume a terminated live view")
                next_state = "running"
            else:
                next_state = "killed"
            return self._publish_locked(session_id, "control", next_state, overlay=f"control={action}")

    def events(self, session_id: str, after_sequence: int = 0) -> tuple[LiveViewEvent, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        with self._lock:
            session = self._require_session(session_id)
            return tuple(event for event in session.events or () if event.sequence > after_sequence)

    def state(self, session_id: str) -> LiveViewState:
        with self._lock:
            return self._require_session(session_id).state

    def _publish_locked(
        self,
        session_id: str,
        kind: LiveViewEventKind,
        state: LiveViewState,
        *,
        current_url: str | None = None,
        page: str | None = None,
        overlay: str | None = None,
        frame_ref: str | None = None,
    ) -> LiveViewEvent:
        session = self._require_session(session_id)
        session.sequence += 1
        event = LiveViewEvent(
            session_id=session_id,
            sequence=session.sequence,
            kind=kind,
            state=state,
            current_url=current_url,
            page=self._safe_text(page),
            overlay=self._safe_text(overlay),
            frame_ref=self._safe_frame_ref(frame_ref),
            created_at=time.time(),
        )
        session.state = state
        session.events = (session.events or [])[-(self.max_events_per_session - 1) :] + [event]
        return event

    def _require_session(self, session_id: str) -> _LiveSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise AccountError("live view session not found") from exc

    def _safe_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        safe = self._redactor.redact_text(str(value))
        for pattern, replacement in _LIVE_SENSITIVE_PATTERNS:
            safe = pattern.sub(replacement, safe)
        return safe[:512]

    @staticmethod
    def _safe_frame_ref(value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        if not value or len(value) > 256 or not re.fullmatch(r"[A-Za-z0-9._:/-]+", value):
            raise ValueError("frame_ref must be an opaque reference")
        return value
