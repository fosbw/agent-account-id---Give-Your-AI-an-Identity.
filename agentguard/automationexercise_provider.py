from __future__ import annotations

import json
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from .accounts import AccountError, AccountVault, AgentAccount, ProviderCapabilities
from .browser_auth import BrowserAutomation
from .provider import ProviderSession
from .provisioning import ExternalAccount, ProvisioningRequest


class AutomationExerciseProvider:
    """Real browser provider for the public AutomationExercise test environment."""

    __test__ = False

    provider = "automationexercise"
    target = "automationexercise.com"
    signup_url = "https://automationexercise.com/signup"
    login_url = "https://automationexercise.com/login"
    logout_url = "https://automationexercise.com/logout"

    def capabilities(self) -> ProviderCapabilities:
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
            revocation="provider_test_site_not_implemented",
        )

    def create_external_account(
        self,
        account: AgentAccount,
        request: ProvisioningRequest,
        vault: AccountVault,
        browser: BrowserAutomation,
    ) -> ExternalAccount:
        browser.open(self.signup_url, Path(account.browser_profile or "."))
        time.sleep(3)
        initial = self._refs(browser.snapshot())
        self._require_ref(initial, "Name", "textbox")
        self._require_ref(initial, "Email Address", "textbox")
        self._require_ref(initial, "Signup", "button")

        name = self._display_name(request)
        email = self._email(account)
        password = "Aa1!" + secrets.token_urlsafe(18)
        secret_value = json.dumps({
            "name": name,
            "email": email,
            "username": email,
            "password": password,
        })
        credential_ref = vault.put_secret(account.handle, "provider_login", secret_value)

        def complete_signup(secret: str) -> ExternalAccount:
            try:
                credentials = json.loads(secret)
                browser.fill('[data-qa="signup-name"]', credentials["name"])
                browser.fill('[data-qa="signup-email"]', credentials["email"])
                browser.submit('[data-qa="signup-button"]')
                browser.wait_for_load()
                time.sleep(2)
                form = self._refs(browser.snapshot())
                self._require_ref(form, "Name *", "textbox")
                self._require_ref(form, "Password *", "textbox")
                self._fill_account_form(browser, credentials)
                browser.press("Enter")
                browser.wait_for_load()
                time.sleep(2)
                url = browser.current_url()
                page = browser.page_text()
            except Exception as exc:
                raise AccountError("AutomationExercise signup interaction failed") from exc
            if "/account_created" not in url or "ACCOUNT CREATED" not in page.upper():
                raise AccountError("provider did not confirm external account creation")
            # The practice site may auto-authenticate immediately after signup.
            # Logout first so Browser Authentication proves an independent login.
            browser.open(self.logout_url, Path(account.browser_profile or "."))
            browser.wait_for_load()
            time.sleep(1)
            return ExternalAccount(
                provider=self.provider,
                external_account_ref="external-account-" + uuid.uuid4().hex[:16],
                credential_ref=credential_ref,
                created_at=time.time(),
                verified=True,
            )

        return vault.use_secret(credential_ref, complete_signup)

    def login(self, request, vault: AccountVault, browser: BrowserAutomation) -> ProviderSession:
        if request.target != self.target or not request.login_url.startswith(self.login_url):
            raise AccountError("AutomationExercise login target is invalid")
        browser.open(request.login_url, request.profile_dir or Path("."))
        browser.wait_for_load()
        time.sleep(3)
        refs = self._refs(browser.snapshot())
        if not self._has_ref(refs, "Email Address", "textbox"):
            browser.open(request.login_url, request.profile_dir or Path("."))
            browser.wait_for_load()
            time.sleep(2)
            refs = self._refs(browser.snapshot())
        self._require_ref(refs, "Email Address", "textbox")
        self._require_ref(refs, "Password", "textbox")
        self._require_ref(refs, "Login", "button")
        try:
            credential_ref = vault.find_active_secret_reference(request.account_handle, "provider_login")
        except FileNotFoundError as exc:
            raise AccountError("provider credentials are not configured in this process") from exc

        def complete_login(secret: str) -> ProviderSession:
            try:
                credentials = json.loads(secret)
                browser.fill('[data-qa="login-email"]', credentials["email"])
                browser.fill('[data-qa="login-password"]', credentials["password"])
                browser.press("Enter")
                browser.wait_for_load()
                time.sleep(2)
                url = browser.current_url()
                page = browser.page_text()
            except Exception as exc:
                raise AccountError("AutomationExercise login interaction failed") from exc
            if "Logged in as" not in page or "automationexercise.com" not in url:
                raise AccountError("provider authentication did not confirm logged-in state")
            now = time.time()
            return ProviderSession(
                session_id="automationexercise-session-" + uuid.uuid4().hex[:12],
                provider=self.provider,
                account_id=request.account_handle.rsplit("/", 1)[-1],
                credential_ref=credential_ref,
                provider_session_ref="automationexercise-provider-session-" + uuid.uuid4().hex[:12],
                state="active",
                authenticated=True,
                created_at=now,
                updated_at=now,
            )

        return vault.use_secret(credential_ref, complete_login)

    @staticmethod
    def _refs(snapshot: dict[str, Any]) -> dict[str, Any]:
        refs = snapshot.get("refs", {}) if isinstance(snapshot, dict) else {}
        return refs if isinstance(refs, dict) else {}

    @staticmethod
    def _has_ref(refs: dict[str, Any], name: str, role: str) -> bool:
        return any(
            isinstance(payload, dict)
            and payload.get("role") == role
            and str(payload.get("name") or "").casefold() == name.casefold()
            for payload in refs.values()
        )

    @staticmethod
    def _require_ref(refs: dict[str, Any], name: str, role: str) -> str:
        for ref, payload in refs.items():
            if isinstance(payload, dict) and payload.get("role") == role and str(payload.get("name") or "").casefold() == name.casefold():
                return "@" + str(ref)
        raise AccountError(f"AutomationExercise form element not found: {name}")

    @staticmethod
    def _display_name(request: ProvisioningRequest) -> str:
        name = request.display_name.strip() or request.agent_id.strip()
        return re.sub(r"[^A-Za-z0-9 -]", "", name)[:40] or "Agent Test"

    @staticmethod
    def _email(account: AgentAccount) -> str:
        suffix = account.account_id.rsplit("-", 1)[-1]
        return f"agent-{suffix}@example.test"

    @staticmethod
    def _fill_account_form(browser: BrowserAutomation, credentials: dict[str, str]) -> None:
        fields = {
            '[data-qa="password"]': credentials["password"],
            '[data-qa="first_name"]': "Agent",
            '[data-qa="last_name"]': "Test",
            '[data-qa="address"]': "1 Test Street",
            '[data-qa="state"]': "Test State",
            '[data-qa="city"]': "Test City",
            '[data-qa="zipcode"]': "00000",
            '[data-qa="mobile_number"]': "5550100",
        }
        for selector, value in fields.items():
            browser.fill(selector, value)
        browser.select("#country", "United States")
        browser.select("#days", "1")
        browser.select("#months", "January")
        browser.select("#years", "2000")
        browser.check("#id_gender1")
        browser.fill('[data-qa="mobile_number"]', fields['[data-qa="mobile_number"]'])
