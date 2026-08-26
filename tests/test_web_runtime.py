from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.accounts import AccountError
from agentguard.browser import BrowserSessionManager
from agentguard.web_runtime import UniversalWebRuntime, WebActionRequest


class FakeBrowser:
    def __init__(self) -> None:
        self.url = "https://example.test/"
        self.page = "Example home"
        self.actions: list[tuple[str, str, str | None]] = []

    def open(self, url: str, profile_dir: Path) -> None:
        self.url = url
        self.actions.append(("open", url, str(profile_dir)))

    def snapshot(self) -> dict:
        return {"refs": {}}

    def fill(self, selector: str, value: str) -> None:
        self.actions.append(("fill", selector, value))

    def select(self, selector: str, value: str) -> None:
        self.actions.append(("select", selector, value))

    def check(self, selector: str) -> None:
        self.actions.append(("check", selector, None))

    def click(self, selector: str) -> None:
        self.actions.append(("click", selector, None))

    def submit(self, selector: str) -> None:
        self.actions.append(("submit", selector, None))

    def press(self, key: str) -> None:
        self.actions.append(("press", key, None))

    def wait_for_load(self) -> None:
        return None

    def current_url(self) -> str:
        return self.url

    def page_text(self) -> str:
        return self.page

    def close(self) -> None:
        return None


def _session(tmp_path: Path) -> tuple[BrowserSessionManager, FakeBrowser, str]:
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(
        ttl=60,
        allowed_domains=("example.test",),
        identity_provider="test",
        identity_id="identity-test",
        account_id="acct-test",
        persistent_profile=True,
    )
    return manager, FakeBrowser(), manifest.session_id


def test_universal_web_runtime_navigates_and_reads_safe_content(tmp_path: Path) -> None:
    manager, browser, session_id = _session(tmp_path)
    browser.page = "Dashboard password=should-not-leak token=hidden normal content"
    runtime = UniversalWebRuntime(manager, browser)

    navigated = runtime.execute(
        session_id,
        WebActionRequest("navigate", url="https://example.test/dashboard"),
    )
    result = runtime.execute(session_id, WebActionRequest("read"))

    assert navigated.ok is True
    assert result.ok is True
    assert result.current_url == "https://example.test/dashboard"
    assert "[REDACTED_PASSWORD]" in result.content
    assert "should-not-leak" not in (result.content or "")
    assert "token=hidden" not in (result.content or "")
    assert manager.get(session_id).current_action == "page read"


def test_universal_web_runtime_allows_non_secret_actions(tmp_path: Path) -> None:
    manager, browser, session_id = _session(tmp_path)
    runtime = UniversalWebRuntime(manager, browser)

    runtime.execute(session_id, WebActionRequest("fill", selector="#search", value="public query"))
    runtime.execute(session_id, WebActionRequest("select", selector="#country", value="US"))
    runtime.execute(session_id, WebActionRequest("click", selector="#go"))

    assert [(kind, selector) for kind, selector, _ in browser.actions[-3:]] == [
        ("fill", "#search"),
        ("select", "#country"),
        ("click", "#go"),
    ]


def test_universal_web_runtime_rejects_secret_fields(tmp_path: Path) -> None:
    manager, browser, session_id = _session(tmp_path)
    runtime = UniversalWebRuntime(manager, browser)

    with pytest.raises(AccountError, match="credential fields"):
        runtime.execute(
            session_id,
            WebActionRequest("fill", selector="#password", value="not-revealed"),
        )


def test_universal_web_runtime_enforces_allowlist(tmp_path: Path) -> None:
    manager, browser, session_id = _session(tmp_path)
    runtime = UniversalWebRuntime(manager, browser)

    with pytest.raises(AccountError, match="navigation blocked"):
        runtime.execute(
            session_id,
            WebActionRequest("navigate", url="https://not-allowed.test/"),
        )
