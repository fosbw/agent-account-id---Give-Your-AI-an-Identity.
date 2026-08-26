from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .accounts import AccountError
from .browser import BrowserSessionManager
from .browser_auth import BrowserAutomation
from .security import SecurityBoundary


WebOperation = Literal["navigate", "read", "click", "fill", "select", "submit"]
_SECRET_SELECTOR_WORDS = (
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "api-key",
    "apikey",
    "private-key",
    "recovery-code",
)


@dataclass(frozen=True)
class WebActionRequest:
    """A planner-supplied browser mechanic; credentials are adapter-only."""

    operation: WebOperation
    url: str | None = None
    selector: str | None = None
    value: str | None = None


@dataclass(frozen=True)
class SafeWebResult:
    operation: WebOperation
    ok: bool
    current_url: str
    page: str | None
    content: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "ok": self.ok,
            "current_url": self.current_url,
            "page": self.page,
            "content": self.content,
            "reason": self.reason,
        }


class UniversalWebRuntime:
    """Provider-neutral browser mechanics under the existing browser policy."""

    def __init__(self, browser_manager: BrowserSessionManager, browser: BrowserAutomation):
        self.browser_manager = browser_manager
        self.browser = browser
        self.security = SecurityBoundary()

    def execute(self, session_id: str, request: WebActionRequest) -> SafeWebResult:
        manifest = self.browser_manager.get(session_id)
        operation = request.operation
        if operation == "navigate":
            if not request.url:
                raise AccountError("navigate requires a URL")
            decision = self.browser_manager.request_navigation(session_id, request.url)
            if not decision.allowed:
                raise AccountError(f"navigation blocked: {decision.reason}")
            self.browser.open(decision.canonical_url or request.url, Path(manifest.profile_dir))
            self.browser.wait_for_load()
            return self._observed(session_id, operation, "navigated")

        if operation in {"click", "fill", "select", "submit"} and not request.selector:
            raise AccountError(f"{operation} requires a selector")
        if operation in {"fill", "select"} and self._looks_secret_selector(request.selector or ""):
            raise AccountError("credential fields are restricted to provider authentication adapters")

        if operation == "read":
            return self._read(session_id)
        if operation == "click":
            self.browser.click(request.selector or "")
        elif operation == "submit":
            self.browser.submit(request.selector or "")
        elif operation == "fill":
            if request.value is None:
                raise AccountError("fill requires a value")
            self.browser.fill(request.selector or "", request.value)
        elif operation == "select":
            if request.value is None:
                raise AccountError("select requires a value")
            self.browser.select(request.selector or "", request.value)
        self.browser.wait_for_load()
        return self._observed(session_id, operation, "action completed")

    def _read(self, session_id: str) -> SafeWebResult:
        url = self.browser.current_url()
        decision = self.browser_manager.request_navigation(session_id, url)
        if not decision.allowed:
            raise AccountError(f"read blocked: {decision.reason}")
        raw = self.browser.page_text()
        safe_content = self.security.safe_text(raw)
        return self._observed(session_id, "read", "page read", content=safe_content)

    def _observed(
        self,
        session_id: str,
        operation: WebOperation,
        action: str,
        content: str | None = None,
    ) -> SafeWebResult:
        url = self.browser.current_url()
        page_text = self.browser.page_text()
        safe_page = self.security.safe_text(re.sub(r"\s+", " ", page_text).strip(), limit=128) or None
        decision = self.browser_manager.record_browser_state(session_id, url, safe_page, action)
        if not decision.allowed:
            raise AccountError(f"browser state blocked: {decision.reason}")
        return SafeWebResult(
            operation=operation,
            ok=True,
            current_url=decision.canonical_url or url,
            page=safe_page,
            content=content,
        )

    @staticmethod
    def _looks_secret_selector(selector: str) -> bool:
        normalized = selector.casefold()
        return any(word in normalized for word in _SECRET_SELECTOR_WORDS)
