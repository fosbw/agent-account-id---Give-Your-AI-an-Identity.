from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .accounts import AccountError, AccountVault, AgentAccount, ProviderCapabilities


@dataclass
class ProviderSession:
    session_id: str
    provider: str
    account_id: str
    credential_ref: str
    provider_session_ref: str
    state: str
    authenticated: bool
    created_at: float
    updated_at: float

    def safe_metadata(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "account_id": self.account_id,
            "credential_ref": self.credential_ref,
            "provider_session_ref": self.provider_session_ref,
            "state": self.state,
            "authenticated": self.authenticated,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProviderAdapter(Protocol):
    provider: str

    def capabilities(self) -> ProviderCapabilities:
        ...

    def provision_account(self, agent_key: str, agent_id: str, display_name: str) -> AgentAccount:
        ...

    def initialize_credentials(self, account: AgentAccount, vault: AccountVault, agent_key: str) -> str:
        ...

    def initialize_browser_profile(self, account: AgentAccount, profile_dir: Path) -> AgentAccount:
        ...

    def authenticate(self, account: AgentAccount, credential_ref: str, vault: AccountVault) -> ProviderSession:
        ...

    def refresh_session(self, session: ProviderSession, vault: AccountVault) -> ProviderSession:
        ...

    def revoke_session(self, session: ProviderSession, vault: AccountVault) -> ProviderSession:
        ...

    def execute_action(self, session: ProviderSession, action: str, vault: AccountVault) -> dict[str, object]:
        ...


class TestProviderAdapter:
    """Deterministic provider adapter used to prove the runtime architecture.

    It is outside the Core Runtime and uses synthetic provider state. It never
    represents a Google account or contacts an external website.
    """

    __test__ = False

    provider = "test-provider"

    def __init__(self, website: str = "test.example"):
        self.website = website
        self._sessions: dict[str, ProviderSession] = {}
        self._actions: list[dict[str, object]] = []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider,
            account_creation="supported_test_adapter",
            authentication="supported_test_adapter",
            identity_initialization="supported_test_adapter",
            credential_initialization="supported_internal_vault",
            browser_session="supported_test_adapter",
            persistent_session="supported_test_adapter",
            verification="supported_test_adapter",
            recovery="supported_test_adapter",
            credential_rotation="supported_test_adapter",
            revocation="supported_test_adapter",
        )

    def provision_account(self, agent_key: str, agent_id: str, display_name: str) -> AgentAccount:
        if not agent_key or not agent_id.strip() or not display_name.strip():
            raise AccountError("agent_key, agent_id, and display_name are required")
        account_id = "acct-" + uuid.uuid4().hex
        handle = f"agent_account://{self.provider}/{account_id}"
        now = time.time()
        return AgentAccount(
            account_id=account_id,
            handle=handle,
            agent_id=agent_id.strip(),
            provider=self.provider,
            display_name=display_name.strip(),
            state="provisioned",
            created_at=now,
            updated_at=now,
            verification_state="completed",
            session_state="not_started",
            authorization_basis="test_provider_authorized",
        )

    def initialize_credentials(self, account: AgentAccount, vault: AccountVault, agent_key: str) -> str:
        if not agent_key:
            raise AccountError("agent_key is required")
        digest = hashlib.sha256(agent_key.encode("utf-8")).hexdigest()[:16]
        internal_value = f"test-secret:{digest}"
        ref = vault.put_secret(account.handle, "provider_session_secret", internal_value)
        account.state = "credentials_initialized"
        account.updated_at = time.time()
        return ref

    def initialize_browser_profile(self, account: AgentAccount, profile_dir: Path) -> AgentAccount:
        profile_dir.mkdir(parents=True, exist_ok=True)
        account.browser_profile = str(profile_dir.resolve())
        account.state = "browser_initialized"
        account.updated_at = time.time()
        return account

    def authenticate(self, account: AgentAccount, credential_ref: str, vault: AccountVault) -> ProviderSession:
        session_id = "provider-session-" + uuid.uuid4().hex[:12]

        def authenticate_with_secret(secret: str) -> ProviderSession:
            if not secret.startswith("test-secret:"):
                raise AccountError("test provider credential is invalid")
            now = time.time()
            session = ProviderSession(
                session_id=session_id,
                provider=self.provider,
                account_id=account.account_id,
                credential_ref=credential_ref,
                provider_session_ref="provider-session-ref-" + uuid.uuid4().hex[:12],
                state="active",
                authenticated=True,
                created_at=now,
                updated_at=now,
            )
            self._sessions[session_id] = session
            return session

        return vault.use_secret(credential_ref, authenticate_with_secret)

    def refresh_session(self, session: ProviderSession, vault: AccountVault) -> ProviderSession:
        if session.state != "active":
            raise AccountError("provider session is not refreshable")
        session.updated_at = time.time()
        session.state = "active"
        return session

    def revoke_session(self, session: ProviderSession, vault: AccountVault) -> ProviderSession:
        session.state = "revoked"
        session.authenticated = False
        session.updated_at = time.time()
        self._sessions[session.session_id] = session
        return session

    def execute_action(self, session: ProviderSession, action: str, vault: AccountVault) -> dict[str, object]:
        if session.state != "active" or not session.authenticated:
            raise AccountError("provider session is not active")
        if not action or "\n" in action or "\r" in action or len(action) > 256:
            raise AccountError("action must be a short single-line value")
        result = {
            "ok": True,
            "provider": self.provider,
            "site": self.website,
            "action": action,
            "session_id": session.session_id,
            "account_id": session.account_id,
        }
        self._actions.append(result)
        return result

    @property
    def action_history(self) -> tuple[dict[str, object], ...]:
        return tuple(self._actions)
