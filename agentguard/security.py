from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .accounts import AccountError, AgentAccount
from .browser import BrowserSessionManifest
from .redaction import Redactor
from .runtime import AgentIdentity


_SECRET_WORDS = (
    "password",
    "passwd",
    "cookie",
    "token",
    "secret",
    "private_key",
    "recovery_code",
)


class SecurityBoundary:
    """Shared enforcement for Agent ownership and secret-safe surfaces."""

    def __init__(self, redactor: Redactor | None = None):
        self.redactor = redactor or Redactor()

    def authorize_account(self, identity: AgentIdentity, account: AgentAccount) -> None:
        if account.identity_id != identity.identity_id or account.agent_id != identity.agent_id:
            raise AccountError("Agent is not authorized to use this account")

    def safe_text(self, text: str, limit: int = 8192) -> str:
        return self.redactor.redact_text(text)[:limit]

    def safe_object(self, value: Any) -> Any:
        return self.redactor.redact_object(value)

    def assert_safe_metadata(self, metadata: Mapping[str, object]) -> None:
        for key in metadata:
            normalized = str(key).casefold()
            if any(word in normalized for word in _SECRET_WORDS):
                raise AccountError("security boundary rejected secret-bearing metadata")

    def assert_screenshot_allowed(self, manifest: BrowserSessionManifest) -> None:
        if manifest.login_state in {"login_required", "authenticating"}:
            raise AccountError("screenshots are blocked while credentials or authentication are active")
        if manifest.current_action.casefold() in {"credential_fill", "password_fill", "secret_fill"}:
            raise AccountError("screenshots are blocked during credential handling")
