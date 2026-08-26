from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .accounts import AccountError, AccountVault, AgentAccount
from .browser import BrowserSessionManager, BrowserSessionManifest
from .provider import ProviderAdapter, ProviderSession


@dataclass(frozen=True)
class AgentIdentity:
    identity_id: str
    agent_id: str
    provider: str
    key_fingerprint: str
    created_at: float

    def safe_metadata(self) -> dict[str, object]:
        return {
            "identity_id": self.identity_id,
            "agent_id": self.agent_id,
            "provider": self.provider,
            "key_fingerprint": self.key_fingerprint,
            "created_at": self.created_at,
        }


@dataclass
class CorePath:
    identity: AgentIdentity
    account: AgentAccount
    credential_ref: str
    browser: BrowserSessionManifest
    provider_session: ProviderSession
    action_result: dict[str, object] | None = None
    killed: bool = False

    def safe_metadata(self) -> dict[str, object]:
        return {
            "identity": self.identity.safe_metadata(),
            "account": self.account.safe_metadata(),
            "credential_ref": self.credential_ref,
            "browser": self.browser.__dict__.copy(),
            "provider_session": self.provider_session.safe_metadata(),
            "action_result": self.action_result,
            "killed": self.killed,
        }


class AccountStore:
    """Persistent Account Record storage, separate from credentials and providers."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, account: AgentAccount) -> None:
        path = self._path(account.account_id)
        path.write_text(json.dumps(account.safe_metadata(), indent=2) + "\n", encoding="utf-8")

    def get(self, account_id: str) -> AgentAccount:
        if not account_id or "/" in account_id or "\\" in account_id:
            raise ValueError("invalid account id")
        path = self._path(account_id)
        if not path.exists():
            raise FileNotFoundError(f"account record not found: {account_id}")
        return AgentAccount(**json.loads(path.read_text(encoding="utf-8")))

    def _path(self, account_id: str) -> Path:
        return self.root / f"{account_id}.json"


class AccountRuntime:
    """Core orchestration for an Agent Account and provider session.

    The provider adapter is deliberately outside this class. The runtime owns
    lifecycle ordering and safe metadata; the adapter owns provider behavior.
    """

    def __init__(
        self,
        root: Path,
        adapter: ProviderAdapter,
        browser: BrowserSessionManager | None = None,
        vault: AccountVault | None = None,
    ):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.adapter = adapter
        self.vault = vault or AccountVault(self.root / "credential-vault")
        self.accounts = AccountStore(self.root / "account-records")
        self.browser = browser or BrowserSessionManager(self.root / "browser-sessions")

    def start(
        self,
        agent_key: str,
        agent_id: str,
        display_name: str,
        ttl: float,
        allowed_domains: tuple[str, ...],
        action: str,
    ) -> CorePath:
        if not agent_key:
            raise AccountError("agent_key is required")
        identity = self._identity_from_key(agent_key, agent_id)
        account = self.adapter.provision_account(agent_key, agent_id, display_name)
        account.identity_id = identity.identity_id
        account.state = "provisioned"
        self.accounts.save(account)
        credential_ref = self.adapter.initialize_credentials(account, self.vault, agent_key)
        profile_dir = self.browser.root / "profiles" / account.account_id
        account = self.adapter.initialize_browser_profile(account, profile_dir)
        self.accounts.save(account)
        browser_manifest = self.browser.create(
            ttl=ttl,
            allowed_domains=allowed_domains,
            identity_provider=self.adapter.provider,
            identity_id=identity.identity_id,
            account_id=account.account_id,
            persistent_profile=True,
        )
        provider_session = self.adapter.authenticate(account, credential_ref, self.vault)
        account.session_state = "active"
        account.state = "active"
        account.updated_at = time.time()
        self.accounts.save(account)
        action_result = self.adapter.execute_action(provider_session, action, self.vault)
        return CorePath(identity, account, credential_ref, browser_manifest, provider_session, action_result)

    def kill(self, path: CorePath, reason: str = "user_kill") -> CorePath:
        self.browser.cleanup(path.browser.session_id, reason=reason)
        path.provider_session = self.adapter.revoke_session(path.provider_session, self.vault)
        path.account.session_state = "killed"
        path.account.state = "session_killed"
        path.account.updated_at = time.time()
        self.accounts.save(path.account)
        path.browser = self.browser.get(path.browser.session_id)
        path.killed = True
        return path

    def restart(self, path: CorePath, ttl: float, action: str) -> CorePath:
        if not path.killed:
            raise AccountError("kill the current path before restart")
        account = self.accounts.get(path.account.account_id)
        browser_manifest = self.browser.create(
            ttl=ttl,
            allowed_domains=path.browser.allowed_domains,
            identity_provider=path.identity.provider,
            identity_id=path.identity.identity_id,
            account_id=account.account_id,
            persistent_profile=True,
        )
        provider_session = self.adapter.authenticate(account, path.credential_ref, self.vault)
        account.session_state = "active"
        account.state = "active"
        account.updated_at = time.time()
        self.accounts.save(account)
        action_result = self.adapter.execute_action(provider_session, action, self.vault)
        return CorePath(path.identity, account, path.credential_ref, browser_manifest, provider_session, action_result)

    def _identity_from_key(self, agent_key: str, agent_id: str) -> AgentIdentity:
        if not agent_id.strip():
            raise AccountError("agent_id is required")
        fingerprint = hashlib.sha256(agent_key.encode("utf-8")).hexdigest()
        return AgentIdentity(
            identity_id="identity-" + uuid.uuid4().hex,
            agent_id=agent_id.strip(),
            provider=self.adapter.provider,
            key_fingerprint=fingerprint,
            created_at=time.time(),
        )
