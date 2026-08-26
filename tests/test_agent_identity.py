from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.accounts import AccountError
from agentguard.agent_identity import AgentIdentityStore


def test_agent_identity_aggregate_tracks_safe_web_identity_graph(tmp_path: Path) -> None:
    store = AgentIdentityStore(tmp_path / "agent-identities")
    identity = store.create("identity-agent-1", "research-agent", "example", "fingerprint")

    identity.register_account(
        "agent_account://example/acct-agent-1",
        "/profiles/acct-agent-1",
        "secret-ref-1",
    )
    identity.set_permissions(("web.read", "web.navigate"))
    identity.register_session({
        "session_id": "session-1",
        "provider": "example",
        "account_id": "acct-agent-1",
        "provider_session_ref": "provider-session-1",
        "state": "active",
        "authenticated": True,
        "updated_at": 1.0,
    })
    identity.add_activity("read authenticated page", "session-1")
    identity.register_memory_ref("memory://agent/research-agent/preferences")
    store.save(identity)

    loaded = store.get("identity-agent-1")
    assert loaded.account_handles == ["agent_account://example/acct-agent-1"]
    assert loaded.browser_profiles == ["/profiles/acct-agent-1"]
    assert loaded.credential_refs == ["secret-ref-1"]
    assert loaded.sessions[0]["provider_session_ref"] == "provider-session-1"
    assert loaded.permissions == ["web.navigate", "web.read"]
    assert loaded.activity_history[0]["action"] == "read authenticated page"
    assert loaded.memory_refs == ["memory://agent/research-agent/preferences"]
    assert "password" not in str(loaded.safe_metadata()).casefold()
    assert "cookie" not in str(loaded.safe_metadata()).casefold()


def test_agent_identity_rejects_secret_session_metadata(tmp_path: Path) -> None:
    identity = AgentIdentityStore(tmp_path / "agent-identities").create(
        "identity-agent-2", "agent-2", "example", "fingerprint"
    )

    with pytest.raises(AccountError, match="secret fields"):
        identity.register_session({"session_id": "session-2", "password": "never-store"})


def test_agent_identity_enforces_account_ownership(tmp_path: Path) -> None:
    store = AgentIdentityStore(tmp_path / "agent-identities")
    identity = store.create("identity-agent-3", "agent-3", "example", "fingerprint")
    identity.register_account("agent_account://example/acct-owned")
    store.save(identity)

    store.assert_account_owner("identity-agent-3", "agent_account://example/acct-owned")
    with pytest.raises(AccountError, match="not authorized"):
        store.assert_account_owner("identity-agent-3", "agent_account://example/acct-other")
