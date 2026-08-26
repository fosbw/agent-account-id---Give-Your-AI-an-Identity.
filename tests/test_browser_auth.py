import json
from pathlib import Path

import pytest

from agentguard.accounts import AccountError, AccountVault
from agentguard.browser import BrowserSessionManager
from agentguard.browser_auth import (
    BrowserAuthenticationRuntime,
    DemoCredentialProvider,
    DemoLoginAdapter,
    LoginRequest,
)


class FakeBrowserAutomation:
    """In-memory BrowserAutomation used to test the generic runtime boundary."""

    def __init__(self, valid_username: str = "demo-user", valid_password: str = "demo-pass"):
        self.valid_username = valid_username
        self.valid_password = valid_password
        self.username = ""
        self.password = ""
        self.url = ""
        self.page = ""
        self.closed = False
        self.fill_calls: list[tuple[str, bool]] = []

    def open(self, url: str, profile_dir: Path) -> None:
        self.url = url
        self.page = "Login Page"
        profile_dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self) -> dict:
        return {
            "refs": {
                "e1": {
                    "name": "Login instructions: enter Username and Password",
                    "role": "heading",
                },
                "e2": {"name": "Username", "role": "textbox"},
                "e3": {"name": "Password", "role": "textbox"},
                "e4": {"name": "Login", "role": "button"},
            }
        }

    def fill(self, selector: str, value: str) -> None:
        self.fill_calls.append((selector, bool(value)))
        if selector == "@e2":
            self.username = value
        elif selector == "@e3":
            self.password = value
        else:
            raise AssertionError(f"unexpected selector: {selector}")

    def submit(self, selector: str) -> None:
        assert selector == "@e4"
        if self.username == self.valid_username and self.password == self.valid_password:
            self.url = "https://the-internet.herokuapp.com/secure"
            self.page = "You logged into a secure area! Secure Area"
        else:
            self.url = "https://the-internet.herokuapp.com/login"
            self.page = "Your username is invalid! Login Page"

    def current_url(self) -> str:
        return self.url

    def page_text(self) -> str:
        return self.page

    def close(self) -> None:
        self.closed = True


def _make_request(manifest, account_handle: str) -> LoginRequest:
    return LoginRequest(
        account_handle=account_handle,
        target="the-internet.herokuapp.com",
        login_url="https://the-internet.herokuapp.com/login",
        session_id=manifest.session_id,
        profile_dir=Path(manifest.profile_dir),
    )


def test_browser_auth_runtime_keeps_credentials_out_of_safe_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    account_handle = "agent_account://demo-site/acct-demo"
    monkeypatch.setenv(DemoCredentialProvider.username_env, "demo-user")
    monkeypatch.setenv(DemoCredentialProvider.password_env, "demo-pass")
    vault = AccountVault(tmp_path / "vault")
    credential_ref = DemoCredentialProvider.install(account_handle, vault)
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(
        ttl=60,
        allowed_domains=("the-internet.herokuapp.com",),
        identity_provider="demo-site",
        identity_id="demo-identity",
        account_id="acct-demo",
        persistent_profile=True,
    )
    browser = FakeBrowserAutomation()

    state = BrowserAuthenticationRuntime(manager, vault).login(
        _make_request(manifest, account_handle), DemoLoginAdapter(), browser
    )

    assert state.authenticated is True
    assert state.account_handle == account_handle
    assert state.current_url.endswith("/secure")
    assert state.verification_state == "completed"
    assert browser.fill_calls == [("@e2", True), ("@e3", True)]
    assert browser.closed is False
    assert credential_ref.startswith("secret-")

    safe_text = json.dumps(state.to_dict())
    assert "demo-pass" not in safe_text
    assert "demo-user" not in safe_text
    vault_metadata = json.dumps(vault.get_reference(credential_ref))
    assert "demo-pass" not in vault_metadata
    assert "demo-user" not in vault_metadata
    assert "secret_present" in vault_metadata

    stored_session = manager.get_provider_session(manifest.session_id)
    assert stored_session["authenticated"] is True
    assert stored_session["provider"] == "demo-site"
    assert stored_session["credential_ref"] == credential_ref
    assert "demo-pass" not in json.dumps(stored_session)

    saved_manifest = manager.get(manifest.session_id)
    assert saved_manifest.login_state == "active"
    assert saved_manifest.verification_state == "completed"
    assert saved_manifest.current_url.endswith("/secure")
    assert saved_manifest.current_action == "authenticated"


def test_browser_auth_failure_marks_login_failed_without_provider_session(tmp_path: Path):
    account_handle = "agent_account://demo-site/acct-demo"
    vault = AccountVault(tmp_path / "vault")
    credential_ref = vault.put_secret(
        account_handle,
        "demo_login",
        json.dumps({"username": "wrong", "password": "wrong"}),
    )
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(
        ttl=60,
        allowed_domains=("the-internet.herokuapp.com",),
        account_id="acct-demo",
        persistent_profile=True,
    )
    browser = FakeBrowserAutomation()

    with pytest.raises(AccountError, match="secure area"):
        BrowserAuthenticationRuntime(manager, vault).login(
            _make_request(manifest, account_handle), DemoLoginAdapter(), browser
        )

    failed = manager.get(manifest.session_id)
    assert failed.login_state == "failed"
    assert failed.current_action == "login_state_updated"
    with pytest.raises(FileNotFoundError):
        manager.get_provider_session(manifest.session_id)
    assert credential_ref.startswith("secret-")


def test_browser_auth_kill_restart_reuses_same_account_and_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    account_handle = "agent_account://demo-site/acct-demo"
    monkeypatch.setenv(DemoCredentialProvider.username_env, "demo-user")
    monkeypatch.setenv(DemoCredentialProvider.password_env, "demo-pass")
    vault = AccountVault(tmp_path / "vault")
    DemoCredentialProvider.install(account_handle, vault)
    manager = BrowserSessionManager(tmp_path / "browser")
    runtime = BrowserAuthenticationRuntime(manager, vault)
    adapter = DemoLoginAdapter()

    first_manifest = manager.create(
        ttl=60,
        allowed_domains=("the-internet.herokuapp.com",),
        identity_provider="demo-site",
        identity_id="demo-identity",
        account_id="acct-demo",
        persistent_profile=True,
    )
    first_browser = FakeBrowserAutomation()
    first = runtime.login(_make_request(first_manifest, account_handle), adapter, first_browser)
    first_profile = Path(manager.get(first_manifest.session_id).profile_dir)
    assert first.authenticated is True
    assert first_profile.exists()

    manager.cleanup(first_manifest.session_id, reason="test_kill")
    killed = manager.get(first_manifest.session_id)
    assert killed.status == "cleaned"
    assert killed.account_id == "acct-demo"
    assert Path(killed.profile_dir).exists()
    revoked_session = manager.get_provider_session(first_manifest.session_id)
    assert revoked_session["state"] == "revoked"
    assert revoked_session["authenticated"] is False

    restarted_manifest = manager.create(
        ttl=60,
        allowed_domains=killed.allowed_domains,
        identity_provider=killed.identity_provider,
        identity_id=killed.identity_id,
        account_id=killed.account_id,
        persistent_profile=True,
    )
    second_browser = FakeBrowserAutomation()
    second = runtime.login(_make_request(restarted_manifest, account_handle), adapter, second_browser)

    assert second.authenticated is True
    assert second.account_handle == first.account_handle
    assert second.session_id != first.session_id
    assert Path(restarted_manifest.profile_dir) == first_profile
    assert Path(restarted_manifest.profile_dir).exists()
    assert manager.get_provider_session(restarted_manifest.session_id)["authenticated"] is True
    manager.cleanup(restarted_manifest.session_id, reason="test_complete")
    assert Path(restarted_manifest.profile_dir).exists()
