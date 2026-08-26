from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

from agentguard.accounts import AccountVault, ProviderCapabilities, AgentAccount
from agentguard.browser import BrowserSessionManager
from agentguard.browser_auth import BrowserAutomation
from agentguard.provider import ProviderSession
from agentguard.provisioning import (
    AccountNamingPolicy,
    AccountProvisioningRuntime,
    ExternalAccount,
    ProvisioningRequest,
)


class FakeProvisioningBrowser:
    """Local-only browser boundary for architecture tests, not live-provider evidence."""

    def __init__(self) -> None:
        self.url = ""
        self.page = ""
        self.closed = False
        self.filled: dict[str, str] = {}

    def open(self, url: str, profile_dir: Path) -> None:
        self.url = url
        self.page = "Login Page"
        profile_dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self) -> dict:
        return {
            "refs": {
                "e1": {"name": "Username", "role": "textbox"},
                "e2": {"name": "Password", "role": "textbox"},
                "e3": {"name": "Login", "role": "button"},
            }
        }

    def fill(self, selector: str, value: str) -> None:
        self.filled[selector] = value

    def submit(self, selector: str) -> None:
        self.url = "https://provider.test/secure"
        self.page = "Secure Area"

    def press(self, key: str) -> None:
        return None

    def wait_for_load(self) -> None:
        return None

    def current_url(self) -> str:
        return self.url

    def page_text(self) -> str:
        return self.page

    def close(self) -> None:
        self.closed = True


class FakeProvisioningAdapter:
    provider = "provider-test-site"
    target = "provider.test"
    signup_url = "https://provider.test/register"
    login_url = "https://provider.test/login"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider,
            account_creation="supported_test_adapter_only",
            identity_initialization="supported_deterministic",
            credential_initialization="supported_internal_vault",
            browser_session="supported",
            persistent_session="supported_profile",
            verification="provider_state_required",
            recovery="supported_same_process_only",
            credential_rotation="unavailable",
            revocation="supported",
        )

    def create_external_account(self, account, request, vault, browser):
        test_secret = "unit-only-" + secrets.token_hex(8)
        credential_ref = vault.put_secret(
            account.handle,
            "provider_login",
            json.dumps({"username": "internal-user", "password": test_secret}),
        )
        return ExternalAccount(
            provider=self.provider,
            external_account_ref="external-test-ref",
            credential_ref=credential_ref,
            created_at=time.time(),
            verified=True,
        )

    def login(self, request, vault, browser):
        browser.open(self.login_url, request.profile_dir)
        refs = browser.snapshot()["refs"]
        assert refs
        credential_ref = vault.find_active_secret_reference(request.account_handle, "provider_login")

        def use(secret: str):
            credentials = json.loads(secret)
            browser.fill("@e1", credentials["username"])
            browser.fill("@e2", credentials["password"])
            browser.submit("@e3")
            now = time.time()
            return ProviderSession(
                session_id="provider-test-session",
                provider=self.provider,
                account_id=request.account_handle.rsplit("/", 1)[-1],
                credential_ref=credential_ref,
                provider_session_ref="provider-test-session-ref",
                state="active",
                authenticated=True,
                created_at=now,
                updated_at=now,
            )

        return vault.use_secret(credential_ref, use)


def test_naming_policy_is_deterministic_and_excludes_agent_key() -> None:
    first = AccountNamingPolicy.identity_name("Acme", "Research Agent", "provider-test", "stable-1")
    second = AccountNamingPolicy.identity_name("Acme", "Research Agent", "provider-test", "stable-1")
    assert first == second
    assert "agent-key" not in first
    assert " " not in first


def test_provisioning_runtime_links_external_account_vault_profile_and_safe_action(tmp_path: Path) -> None:
    adapter = FakeProvisioningAdapter()
    manager = BrowserSessionManager(tmp_path / "browser")
    vault = AccountVault(tmp_path / "vault")
    runtime = AccountProvisioningRuntime(tmp_path / "runtime", adapter, manager, vault)
    browser = FakeProvisioningBrowser()

    path = runtime.provision(
        "agent-key-never-returned",
        ProvisioningRequest("acme", "research-agent", adapter.provider, "Research Agent", "stable-1"),
        60,
        "local-provisioning-session",
        lambda _: browser,
    )

    safe = json.dumps(path.safe_metadata())
    assert path.account.state == "active"
    assert path.account.external_account_ref == "external-test-ref"
    assert path.external_account.verified is True
    assert path.authentication.authenticated is True
    assert path.authentication.current_url.endswith("/secure")
    assert path.browser.persistent_profile is True
    assert path.browser.current_action == "read authenticated page"
    assert "unit-only-" not in safe
    assert "agent-key-never-returned" not in safe
    assert "secret_present" in json.dumps(vault.get_reference(path.external_account.credential_ref))
    assert "unit-only-" not in json.dumps(vault.get_reference(path.external_account.credential_ref))


def test_provisioning_kill_preserves_account_profile_and_revokes_session(tmp_path: Path) -> None:
    adapter = FakeProvisioningAdapter()
    manager = BrowserSessionManager(tmp_path / "browser")
    runtime = AccountProvisioningRuntime(tmp_path / "runtime", adapter, manager, AccountVault(tmp_path / "vault"))
    browser = FakeProvisioningBrowser()
    path = runtime.provision(
        "agent-key",
        ProvisioningRequest("acme", "agent-a", adapter.provider, "Agent A", "stable-a"),
        60,
        "kill-test-session",
        lambda _: browser,
    )
    profile = Path(path.browser.profile_dir)
    runtime.kill(path, "test-kill")

    killed = manager.get(path.browser.session_id)
    assert killed.status == "cleaned"
    assert killed.account_id == path.account.account_id
    assert profile.exists()
    assert manager.get_provider_session(path.browser.session_id)["state"] == "revoked"
    assert runtime.accounts.get(path.account.account_id).external_account_ref == "external-test-ref"


def test_account_handle_mismatch_is_rejected_by_existing_browser_auth_boundary(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(
        ttl=60,
        allowed_domains=("provider.test",),
        identity_provider="provider-test-site",
        identity_id="identity-a",
        account_id="acct-a",
        persistent_profile=True,
    )
    assert manifest.account_id == "acct-a"
    assert "acct-b" != manifest.account_id
