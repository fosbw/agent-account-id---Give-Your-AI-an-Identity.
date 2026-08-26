from __future__ import annotations

import json
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from .accounts import AccountError, AccountVault, AgentAccount
from .browser_auth import BrowserAutomation, LoginRequest
from .provider import ProviderSession
from .provisioning import ExternalAccount, ProvisioningRequest


class ExpandTestingProvider:
    """Real browser provider for the public Expand Testing practice environment."""

    __test__ = False

    provider = "expandtesting"
    target = "practice.expandtesting.com"
    signup_url = "https://practice.expandtesting.com/register"
    login_url = "https://practice.expandtesting.com/login"
    success_path = "/secure"

    def capabilities(self):
        from .accounts import ProviderCapabilities

        return ProviderCapabilities(
            provider=self.provider,
            account_creation="supported_public_test_site_browser",
            identity_initialization="supported_deterministic",
            credential_initialization="supported_internal_vault",
            browser_session="supported_real_browser",
            persistent_session="supported_profile",
            verification="provider_state_required",
            recovery="provider_session_process_bound_reauthentication_required",
            credential_rotation="provider_test_site_not_implemented",
            revocation="supported_test_account_delete",
        )

    def create_external_account(
        self,
        account: AgentAccount,
        request: ProvisioningRequest,
        vault: AccountVault,
        browser: BrowserAutomation,
    ) -> ExternalAccount:
        browser.open(self.signup_url, Path(account.browser_profile or "."))
        time.sleep(2)
        refs = self._refs(browser.snapshot())
        self._find_ref(refs, "Username", "textbox")
        self._find_ref(refs, "Password", "textbox")
        self._find_ref(refs, "Confirm Password", "textbox")
        self._find_ref(refs, "Register", "button")

        username = self._username(request, account)
        password = "Aa1!" + secrets.token_urlsafe(18)
        secret_value = json.dumps({"username": username, "password": password})
        credential_ref = vault.put_secret(account.handle, "provider_login", secret_value)

        def submit_signup(secret: str) -> ExternalAccount:
            try:
                credentials = json.loads(secret)
                browser.fill("#username", credentials["username"])
                browser.fill("#password", credentials["password"])
                browser.fill("#confirmPassword", credentials["password"])
                browser.press("Enter")
                time.sleep(1)
                browser.wait_for_load()
                url = browser.current_url()
                if url.rstrip("/").endswith("/register"):
                    browser.submit("button[type=submit]")
                    time.sleep(1)
                    browser.wait_for_load()
                page = browser.page_text()
                url = browser.current_url()
            except Exception as exc:
                raise AccountError("provider signup interaction failed") from exc
            if not self._signup_succeeded(url, page):
                raise AccountError("provider did not confirm external account creation")
            return ExternalAccount(
                provider=self.provider,
                external_account_ref="external-account-" + uuid.uuid4().hex[:16],
                credential_ref=credential_ref,
                created_at=time.time(),
                verified=True,
            )

        return vault.use_secret(credential_ref, submit_signup)

    def login(self, request: LoginRequest, vault: AccountVault, browser: BrowserAutomation) -> ProviderSession:
        if request.target != self.target or not request.login_url.startswith(self.login_url):
            raise AccountError("Expand Testing login target is invalid")
        browser.open(request.login_url, request.profile_dir or Path("."))
        time.sleep(2)
        refs = self._refs(browser.snapshot())
        self._find_ref(refs, "Username", "textbox")
        self._find_ref(refs, "Password", "textbox")
        self._find_ref(refs, "Login", "button")
        try:
            credential_ref = vault.find_active_secret_reference(request.account_handle, "provider_login")
        except FileNotFoundError as exc:
            raise AccountError("provider credentials are not configured in this process") from exc

        def submit_login(secret: str) -> ProviderSession:
            try:
                credentials = json.loads(secret)
                browser.fill("#username", credentials["username"])
                browser.fill("#password", credentials["password"])
                browser.press("Enter")
                time.sleep(1)
                browser.wait_for_load()
                url = browser.current_url()
                if url.rstrip("/").endswith("/login"):
                    browser.submit("button[type=submit]")
                    time.sleep(1)
                    browser.wait_for_load()
                page = browser.page_text()
                url = browser.current_url()
            except Exception as exc:
                raise AccountError("provider login interaction failed") from exc
            if not url.rstrip("/").endswith(self.success_path) or "You logged into a secure area!" not in page:
                raise AccountError("provider authentication did not reach the secure area")
            now = time.time()
            return ProviderSession(
                session_id="expand-session-" + uuid.uuid4().hex[:12],
                provider=self.provider,
                account_id=request.account_handle.rsplit("/", 1)[-1],
                credential_ref=credential_ref,
                provider_session_ref="expand-provider-session-" + uuid.uuid4().hex[:12],
                state="active",
                authenticated=True,
                created_at=now,
                updated_at=now,
            )

        return vault.use_secret(credential_ref, submit_login)

    @staticmethod
    def _refs(snapshot: dict[str, Any]) -> dict[str, Any]:
        refs = snapshot.get("refs", {}) if isinstance(snapshot, dict) else {}
        return refs if isinstance(refs, dict) else {}

    @staticmethod
    def _find_ref(refs: dict[str, Any], name: str, role: str) -> str:
        for ref, payload in refs.items():
            if isinstance(payload, dict) and payload.get("role") == role and str(payload.get("name") or "").casefold() == name.casefold():
                return "@" + str(ref)
        for ref, payload in refs.items():
            if isinstance(payload, dict) and payload.get("role") == role and name.casefold() in str(payload.get("name") or "").casefold():
                return "@" + str(ref)
        raise AccountError(f"provider form element not found: {name}")

    @staticmethod
    def _username(request: ProvisioningRequest, account: AgentAccount) -> str:
        base = "-".join(part.strip().lower().replace(" ", "-") for part in (request.organization_id, request.agent_id))
        safe = "".join(char for char in base if char.isalnum() or char == "-")
        safe = re.sub(r"-+", "-", safe).strip("-")[:24].rstrip("-")
        suffix = account.account_id.rsplit("-", 1)[-1][:10]
        return f"{safe or 'agent'}-{suffix}"[:39].rstrip("-")

    @staticmethod
    def _signup_succeeded(url: str, page: str) -> bool:
        text = " ".join((url, page)).casefold()
        return any(marker in text for marker in ("registration successful", "successfully registered", "registration completed", "account created")) or "/login" in url.rstrip("/")
