import json
from pathlib import Path

from agentguard.accounts import AccountVault
from agentguard.browser import BrowserSessionManager
from agentguard.provider import TestProviderAdapter
from agentguard.runtime import AccountRuntime


def test_agent_account_end_to_end_lifecycle(tmp_path: Path):
    adapter = TestProviderAdapter(website="test.example")
    vault = AccountVault(tmp_path / "vault")
    browser = BrowserSessionManager(tmp_path / "browser")
    runtime = AccountRuntime(tmp_path / "runtime", adapter=adapter, browser=browser, vault=vault)

    first = runtime.start(
        agent_key="agent-key-for-test-only",
        agent_id="research-agent",
        display_name="Research Agent",
        ttl=60,
        allowed_domains=("test.example",),
        action="read test page",
    )

    assert first.identity.agent_id == "research-agent"
    assert first.identity.key_fingerprint
    assert first.identity.key_fingerprint != "agent-key-for-test-only"
    assert first.account.handle.startswith("agent_account://test-provider/")
    assert first.account.state == "active"
    assert first.credential_ref.startswith("secret-")
    assert first.provider_session.authenticated is True
    assert first.action_result == {
        "ok": True,
        "provider": "test-provider",
        "site": "test.example",
        "action": "read test page",
        "session_id": first.provider_session.session_id,
        "account_id": first.account.account_id,
    }
    assert Path(first.browser.profile_dir).exists()
    assert first.browser.persistent_profile is True

    vault_files = list((tmp_path / "vault").glob("*.json"))
    assert len(vault_files) == 1
    vault_text = vault_files[0].read_text(encoding="utf-8")
    assert "agent-key-for-test-only" not in vault_text
    assert "test-secret:" not in vault_text
    assert "secret_present" in vault_text
    vault_metadata = vault.get_reference(first.credential_ref)
    assert vault_metadata["secret_present"] is True
    assert "test-secret:" not in json.dumps(vault_metadata)
    safe_text = json.dumps(first.safe_metadata())
    assert "agent-key-for-test-only" not in safe_text
    assert "test-secret:" not in safe_text

    killed = runtime.kill(first, reason="test_kill")
    assert killed.killed is True
    assert killed.provider_session.state == "revoked"
    assert runtime.accounts.get(first.account.account_id).state == "session_killed"
    assert Path(first.browser.profile_dir).exists()

    restarted = runtime.restart(killed, ttl=60, action="continue after restart")
    assert restarted.killed is False
    assert restarted.account.account_id == first.account.account_id
    assert restarted.account.handle == first.account.handle
    assert restarted.identity.identity_id == first.identity.identity_id
    assert restarted.browser.account_id == first.account.account_id
    assert restarted.browser.profile_dir == first.browser.profile_dir
    assert restarted.provider_session.session_id != first.provider_session.session_id
    assert restarted.provider_session.authenticated is True
    assert restarted.action_result["action"] == "continue after restart"
    assert len(adapter.action_history) == 2

    browser.cleanup(restarted.browser.session_id, reason="test_complete")
    assert Path(restarted.browser.profile_dir).exists()
