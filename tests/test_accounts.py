import json
from pathlib import Path

import pytest

from agentguard.accounts import (
    AccountError,
    AccountVault,
    GoogleProvider,
    LocalManagedAccountProvisioner,
    ProviderOperationUnavailable,
)
from agentguard.browser import BrowserSessionManager
from agentguard.capabilities import CapabilityError, CapabilityRegistry


def test_local_account_lifecycle_keeps_account_after_browser_cleanup(tmp_path: Path):
    accounts = LocalManagedAccountProvisioner(tmp_path / "accounts")
    account = accounts.create_account("research-agent", "Research Agent")
    account = accounts.initialize_identity(account, "id-agent")
    browser = BrowserSessionManager(tmp_path / "browser")
    manifest = browser.create(
        ttl=10,
        allowed_domains=("example.com",),
        identity_provider="local",
        identity_id="id-agent",
        account_id=account.account_id,
        persistent_profile=True,
    )
    account = accounts.initialize_browser_session(account, Path(manifest.profile_dir))
    browser.cleanup(manifest.session_id, reason="test_cleanup")

    assert Path(account.browser_profile).exists()
    assert accounts.get(account.account_id).state == "browser_initialized"
    saved_manifest = json.loads((tmp_path / "browser" / manifest.session_id / "manifest.json").read_text())
    assert saved_manifest["persistent_profile"] is True
    assert saved_manifest["profile_dir"] == account.browser_profile
    assert saved_manifest["status"] == "cleaned"


def test_vault_rejects_raw_credential_fields(tmp_path: Path):
    vault = AccountVault(tmp_path / "vault")
    with pytest.raises(AccountError):
        vault.put_reference("agent_account://google/agent-1", {"password": "no"})
    with pytest.raises(AccountError):
        vault.put_reference("agent_account://google/agent-1", {"session_cookie": "no"})


def test_vault_accepts_opaque_handle_and_can_revoke(tmp_path: Path):
    vault = AccountVault(tmp_path / "vault")
    reference_id = vault.put_reference("agent_account://google/agent-1", {"purpose": "browser"})
    assert vault.get_reference(reference_id)["handle"] == "agent_account://google/agent-1"
    vault.revoke_reference(reference_id)
    with pytest.raises(FileNotFoundError):
        vault.get_reference(reference_id)


def test_google_provider_reports_unavailable_account_creation():
    provider = GoogleProvider()
    assert provider.can_create_account() is False
    assert provider.capabilities().account_creation == "unavailable"
    with pytest.raises(ProviderOperationUnavailable, match="does not expose"):
        provider.create_account("agent-1", "Research Agent")


def test_site_capabilities_do_not_allow_wildcard():
    registry = CapabilityRegistry()
    assert registry.check("youtube", "web.read") is False if "youtube" in {x.site_id for x in registry.list_sites()} else True
    with pytest.raises(CapabilityError):
        registry.require("github", "*")
    assert registry.check("github", "web.read") is True
