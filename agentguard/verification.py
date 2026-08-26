from __future__ import annotations

from dataclasses import dataclass

from .accounts import AccountError
from .browser import BrowserSessionManager


_CHALLENGE_STATES = frozenset(
    {
        "email_required",
        "phone_required",
        "otp_required",
        "mfa_required",
        "captcha_detected",
        "provider_blocked",
    }
)
_DONE_MESSAGES = frozenset({"done", "تم", "completed", "تم التحقق", "verification completed"})


class VerificationRequired(AccountError):
    """Provider reported a verification challenge; no code is carried here."""

    def __init__(self, state: str):
        if state not in _CHALLENGE_STATES:
            raise ValueError("unsupported verification challenge")
        self.state = state
        super().__init__("provider verification is required")


@dataclass(frozen=True)
class ChatVerificationEvent:
    session_id: str
    domain: str
    verification_state: str
    message: str
    status: str = "awaiting_user_verification"

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "verification_required",
            "session_id": self.session_id,
            "domain": self.domain,
            "verification_state": self.verification_state,
            "status": self.status,
            "message": self.message,
        }


class ChatVerificationHandoff:
    """Chat-safe bridge: it transports status and a completion signal, never a code."""

    def __init__(self, browser: BrowserSessionManager):
        self.browser = browser

    def event_for_session(self, session_id: str, domain: str) -> ChatVerificationEvent | None:
        manifest = self.browser.get(session_id)
        if manifest.verification_state not in _CHALLENGE_STATES:
            return None
        return ChatVerificationEvent(
            session_id=session_id,
            domain=domain,
            verification_state=manifest.verification_state,
            message=(
                "Verification required. Complete the provider verification in the browser, "
                "then reply Done in this chat. Do not send the verification code here."
            ),
        )

    def resume_from_chat(self, session_id: str, domain: str, message: str) -> dict[str, object]:
        normalized = " ".join((message or "").casefold().split())
        if normalized not in _DONE_MESSAGES:
            raise AccountError("only a completion signal is accepted; verification codes are not accepted in chat")
        return self.browser.resume_after_verification(session_id, domain)
