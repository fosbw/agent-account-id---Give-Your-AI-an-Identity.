from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.accounts import AccountError, AgentAccount
from agentguard.browser_auth import BrowserAuthenticationRuntime
from agentguard.browser import BrowserSessionManager
from agentguard.runtime import AgentIdentity
from agentguard.security import SecurityBoundary


def test_security_boundary_redacts_nested_secret_values() -> None:
    boundary = SecurityBoundary()
    payload = {
        "password": "canary-password",
        "nested": {
            "token": "canary-token",
            "cookies": "canary-cookie",
            "message": "bearer canary-bearer",
        },
        "safe": "visible",
    }

    safe = str(boundary.safe_object(payload))
    assert "canary-password" not in safe
    assert "canary-token" not in safe
    assert "canary-cookie" not in safe
    assert "canary-bearer" not in safe
    assert "visible" in safe


def test_browser_authentication_safe_page_label_redacts_secrets() -> None:
    safe = BrowserAuthenticationRuntime._safe_page_label(
        "Dashboard password=canary-password token=canary-token secret=canary-secret cookies=canary-cookie bearer canary-bearer"
    )
    assert safe is not None
    for canary in ("canary-password", "canary-token", "canary-secret", "canary-cookie", "canary-bearer"):
        assert canary not in safe


def test_security_boundary_rejects_cross_agent_account() -> None:
    boundary = SecurityBoundary()
    identity = AgentIdentity("identity-a", "agent-a", "provider", "fingerprint", 1.0)
    account = AgentAccount(
        account_id="acct-b",
        handle="agent_account://provider/acct-b",
        display_name="Agent B account",
        agent_id="agent-b",
        provider="provider",
        identity_id="identity-b",
        state="active",
        session_state="active",
        created_at=1.0,
        updated_at=1.0,
    )

    with pytest.raises(AccountError, match="not authorized"):
        boundary.authorize_account(identity, account)


def test_security_boundary_blocks_screenshot_during_authentication(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(60, ("example.com",), identity_provider="example")
    manifest.login_state = "login_required"

    with pytest.raises(AccountError, match="screenshots are blocked"):
        SecurityBoundary().assert_screenshot_allowed(manifest)

    manifest.login_state = "active"
    manifest.current_action = "credential_fill"
    with pytest.raises(AccountError, match="screenshots are blocked"):
        SecurityBoundary().assert_screenshot_allowed(manifest)
