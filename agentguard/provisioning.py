from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .accounts import AccountError, AccountVault, AgentAccount
from .browser import BrowserSessionManager, BrowserSessionManifest
from .browser_auth import BrowserAuthenticationRuntime, BrowserAutomation, LoginRequest, SafeAuthenticationState
from .provider import ProviderSession
from .runtime import AccountStore, AgentIdentity


@dataclass(frozen=True)
class ProvisioningRequest:
    organization_id: str
    agent_id: str
    provider: str
    display_name: str
    stable_agent_id: str | None = None


@dataclass(frozen=True)
class ExternalAccount:
    provider: str
    external_account_ref: str
    credential_ref: str
    created_at: float
    verified: bool

    def safe_metadata(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "external_account_ref": self.external_account_ref,
            "credential_ref": self.credential_ref,
            "created_at": self.created_at,
            "verified": self.verified,
        }


class AccountNamingPolicy:
    """Creates a stable, provider-scoped identity without embedding Agent Keys."""

    @staticmethod
    def identity_name(
        organization_id: str,
        agent_id: str,
        provider: str,
        stable_agent_id: str | None = None,
    ) -> str:
        parts = [organization_id, agent_id, provider]
        normalized = "-".join(_slug(part) for part in parts if _slug(part))
        stable = stable_agent_id or agent_id
        digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:8]
        return f"{normalized[:48]}-{digest}"


class AccountProvisioningAdapter(Protocol):
    provider: str
    target: str
    signup_url: str
    login_url: str

    def create_external_account(
        self,
        account: AgentAccount,
        request: ProvisioningRequest,
        vault: AccountVault,
        browser: BrowserAutomation,
    ) -> ExternalAccount:
        ...

    def login(
        self,
        request: LoginRequest,
        vault: AccountVault,
        browser: BrowserAutomation,
    ) -> ProviderSession:
        ...


@dataclass
class ProvisionedPath:
    identity: AgentIdentity
    account: AgentAccount
    external_account: ExternalAccount
    browser: BrowserSessionManifest
    authentication: SafeAuthenticationState

    def safe_metadata(self) -> dict[str, object]:
        return {
            "identity": self.identity.safe_metadata(),
            "account": self.account.safe_metadata(),
            "external_account": self.external_account.safe_metadata(),
            "browser": self.browser.__dict__.copy(),
            "authentication": self.authentication.to_dict(),
        }


class AccountProvisioningRuntime:
    """Runs real external account creation before Browser Authentication."""

    def __init__(
        self,
        root: Path,
        adapter: AccountProvisioningAdapter,
        browser: BrowserSessionManager | None = None,
        vault: AccountVault | None = None,
    ):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.adapter = adapter
        self.browser = browser or BrowserSessionManager(self.root / "browser-sessions")
        self.vault = vault or AccountVault(self.root / "credential-vault")
        self.accounts = AccountStore(self.root / "account-records")

    def provision(
        self,
        agent_key: str,
        request: ProvisioningRequest,
        ttl: float,
        browser_session_name: str,
        browser_automation_factory,
    ) -> ProvisionedPath:
        if not agent_key:
            raise AccountError("agent_key is required")
        if request.provider != self.adapter.provider:
            raise AccountError("provisioning request provider does not match adapter")
        if request.agent_id.strip() == "" or request.organization_id.strip() == "":
            raise AccountError("organization_id and agent_id are required")
        identity = self._identity_from_key(agent_key, request)
        stable_name = AccountNamingPolicy.identity_name(
            request.organization_id,
            request.agent_id,
            request.provider,
            request.stable_agent_id,
        )
        account_id = "acct-" + stable_name
        account = AgentAccount(
            account_id=account_id,
            handle=f"agent_account://{request.provider}/{account_id}",
            agent_id=request.agent_id.strip(),
            provider=request.provider,
            display_name=request.display_name.strip() or stable_name,
            state="provisioning",
            created_at=time.time(),
            updated_at=time.time(),
            identity_id=identity.identity_id,
            authorization_basis="public_test_site_authorized",
        )
        self.accounts.save(account)
        profile_dir = self.browser.root / "profiles" / account.account_id
        account.browser_profile = str(profile_dir.resolve())
        browser_manifest = self.browser.create(
            ttl=ttl,
            allowed_domains=(self.adapter.target,),
            identity_provider=self.adapter.provider,
            identity_id=identity.identity_id,
            account_id=account.account_id,
            persistent_profile=True,
        )
        browser = browser_automation_factory(browser_session_name)
        try:
            external = self.adapter.create_external_account(account, request, self.vault, browser)
            account.external_account_ref = external.external_account_ref
            account.verification_state = "completed" if external.verified else "provider_state_required"
            account.session_state = "initialized"
            account.state = "external_account_created"
            account.updated_at = time.time()
            self.accounts.save(account)
            login_request = LoginRequest(
                account_handle=account.handle,
                target=self.adapter.target,
                login_url=self.adapter.login_url,
                session_id=browser_manifest.session_id,
                profile_dir=Path(browser_manifest.profile_dir),
            )
            authentication = BrowserAuthenticationRuntime(self.browser, self.vault).login(
                login_request, self.adapter, browser
            )
            self.browser.record_browser_state(
                browser_manifest.session_id,
                authentication.current_url,
                authentication.page,
                "read authenticated page",
            )
            account.session_state = "active"
            account.state = "active"
            account.updated_at = time.time()
            self.accounts.save(account)
            return ProvisionedPath(identity, account, external, self.browser.get(browser_manifest.session_id), authentication)
        except Exception:
            try:
                account.state = "provisioning_failed"
                account.verification_state = "provider_state_required"
                account.updated_at = time.time()
                self.accounts.save(account)
            finally:
                browser.close()
            raise
        finally:
            browser.close()

    def kill(self, path: ProvisionedPath, reason: str = "user_kill") -> None:
        self.browser.cleanup(path.browser.session_id, reason=reason)
        account = self.accounts.get(path.account.account_id)
        account.session_state = "killed"
        account.state = "session_killed"
        account.updated_at = time.time()
        self.accounts.save(account)

    def _identity_from_key(self, agent_key: str, request: ProvisioningRequest) -> AgentIdentity:
        fingerprint = hashlib.sha256(agent_key.encode("utf-8")).hexdigest()
        stable_id = request.stable_agent_id or request.agent_id
        identity_id = "identity-" + hashlib.sha256(
            f"{request.organization_id}:{request.provider}:{stable_id}".encode("utf-8")
        ).hexdigest()[:16]
        return AgentIdentity(
            identity_id=identity_id,
            agent_id=request.agent_id.strip(),
            provider=request.provider,
            key_fingerprint=fingerprint,
            created_at=time.time(),
        )


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return text or "agent"
