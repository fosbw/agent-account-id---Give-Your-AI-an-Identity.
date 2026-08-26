from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .accounts import AccountError, AccountVault, AgentAccount, ProviderCapabilities, ProviderOperationUnavailable
from .provider import ProviderSession


class GitHubProviderError(AccountError):
    """Raised when a GitHub provider operation fails."""


@dataclass(frozen=True)
class GitHubProviderConfig:
    api_base: str = "https://api.github.com"
    installation_id: str | None = None
    token: str | None = None
    timeout_seconds: int = 20

    @classmethod
    def from_environment(cls) -> "GitHubProviderConfig":
        token = os.environ.get("AGENT_ACCOUNT_GITHUB_INSTALLATION_TOKEN") or os.environ.get("GITHUB_TOKEN")
        installation_id = os.environ.get("AGENT_ACCOUNT_GITHUB_INSTALLATION_ID")
        api_base = os.environ.get("AGENT_ACCOUNT_GITHUB_API_BASE", "https://api.github.com").rstrip("/")
        return cls(
            api_base=api_base,
            installation_id=installation_id,
            token=token,
            timeout_seconds=int(os.environ.get("AGENT_ACCOUNT_GITHUB_TIMEOUT", "20")),
        )

    def safe_metadata(self) -> dict[str, object]:
        return {
            "api_base": self.api_base,
            "installation_id": self.installation_id,
            "token_configured": bool(self.token),
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class GitHubSession:
    session_id: str
    account_id: str
    provider: str
    auth_mode: str
    subject: str | None
    state: str
    created_at: float
    updated_at: float

    def as_provider_session(self, credential_ref: str) -> ProviderSession:
        return ProviderSession(
            session_id=self.session_id,
            provider=self.provider,
            account_id=self.account_id,
            credential_ref=credential_ref,
            provider_session_ref=f"github-session-ref-{self.session_id}",
            state=self.state,
            authenticated=self.state == "active",
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class GitHubProviderAdapter:
    """Official GitHub REST provider using an opaque, caller-owned token.

    The adapter supports linking an existing GitHub App installation or
    authorized token. It does not create consumer accounts. Tokens are passed
    into the internal vault and are never returned in provider metadata.
    """

    provider = "github"

    def __init__(self, config: GitHubProviderConfig | None = None):
        self.config = config or GitHubProviderConfig.from_environment()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider,
            account_creation="unavailable_external_account_creation",
            authentication="supported_official_api",
            identity_initialization="supported_via_github_app_or_oauth",
            credential_initialization="supported_via_internal_vault_boundary",
            browser_session="supported_with_external_runtime",
            persistent_session="supported_with_external_runtime",
            verification="supported_via_provider_response",
            recovery="provider_managed_only",
            credential_rotation="provider_managed_only",
            revocation="supported_by_token_revocation_or_app_uninstall",
        )

    def provision_account(self, agent_key: str, agent_id: str, display_name: str) -> AgentAccount:
        if not agent_key or not agent_id.strip() or not display_name.strip():
            raise AccountError("agent_key, agent_id, and display_name are required")
        if not self.config.installation_id:
            raise ProviderOperationUnavailable(
                "GitHub account provisioning is unavailable; configure an existing App installation ID to link an Agent Account"
            )
        account_id = f"github-installation-{self.config.installation_id}"
        now = time.time()
        return AgentAccount(
            account_id=account_id,
            handle=f"agent_account://github/{self.config.installation_id}",
            agent_id=agent_id.strip(),
            provider=self.provider,
            display_name=display_name.strip(),
            state="linked",
            created_at=now,
            updated_at=now,
            verification_state="provider_state_required",
            session_state="not_started",
            authorization_basis="github_app_installation_or_oauth",
        )

    def initialize_credentials(self, account: AgentAccount, vault: AccountVault, agent_key: str) -> str:
        del agent_key
        if not self.config.token:
            raise ProviderOperationUnavailable(
                "GitHub credentials are unavailable; configure AGENT_ACCOUNT_GITHUB_INSTALLATION_TOKEN or GITHUB_TOKEN"
            )
        return vault.put_secret(account.handle, "github_provider_token", self.config.token)

    def initialize_browser_profile(self, account: AgentAccount, profile_dir: Path) -> AgentAccount:
        profile_dir.mkdir(parents=True, exist_ok=True)
        account.browser_profile = str(profile_dir.resolve())
        account.state = "browser_initialized"
        account.updated_at = time.time()
        return account

    def authenticate(self, account: AgentAccount, credential_ref: str, vault: AccountVault) -> ProviderSession:
        def authenticate_with_token(token: str) -> ProviderSession:
            payload = self._request("GET", "/user", token=token)
            subject = str(payload.get("login") or payload.get("id") or "github-installation")
            now = time.time()
            session = GitHubSession(
                session_id="github-session-" + uuid.uuid4().hex[:12],
                account_id=account.account_id,
                provider=self.provider,
                auth_mode="oauth_or_app_token",
                subject=subject,
                state="active",
                created_at=now,
                updated_at=now,
            )
            return session.as_provider_session(credential_ref)

        return vault.use_secret(credential_ref, authenticate_with_token)

    def refresh_session(self, session: ProviderSession, vault: AccountVault) -> ProviderSession:
        if session.state != "active":
            raise AccountError("GitHub provider session is not active")
        session.updated_at = time.time()
        self._request_with_reference("GET", "/user", session.credential_ref, vault)
        return session

    def revoke_session(self, session: ProviderSession, vault: AccountVault) -> ProviderSession:
        session.state = "revoked"
        session.authenticated = False
        session.updated_at = time.time()
        return session

    def execute_action(self, session: ProviderSession, action: str, vault: AccountVault) -> dict[str, object]:
        if session.state != "active" or not session.authenticated:
            raise AccountError("GitHub provider session is not active")
        if action == "get_authenticated_user":
            payload = self._request_with_reference("GET", "/user", session.credential_ref, vault)
            return self._safe_user_result(session, payload)
        if action == "list_installation_repositories":
            payload = self._request_with_reference("GET", "/installation/repositories", session.credential_ref, vault)
            repositories = payload.get("repositories", []) if isinstance(payload, dict) else []
            return {
                "ok": True,
                "provider": self.provider,
                "action": action,
                "session_id": session.session_id,
                "account_id": session.account_id,
                "repository_count": len(repositories) if isinstance(repositories, list) else 0,
                "repositories": [self._safe_repository(item) for item in repositories if isinstance(item, dict)],
            }
        raise GitHubProviderError(f"unsupported GitHub action: {action}")

    def create_issue(
        self,
        session: ProviderSession,
        vault: AccountVault,
        owner: str,
        repo: str,
        title: str,
        body: str = "",
        confirm: bool = False,
    ) -> dict[str, object]:
        """Create an issue only with explicit caller confirmation.

        This method is intentionally not invoked by CLI defaults or tests.
        """
        if not confirm:
            raise GitHubProviderError("issue creation requires explicit confirmation")
        if not all((owner, repo, title)) or len(title) > 256:
            raise GitHubProviderError("owner, repo, and a short title are required")
        payload = self._request_with_reference(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            session.credential_ref,
            vault,
            body={"title": title, "body": body},
        )
        return {
            "ok": True,
            "provider": self.provider,
            "action": "create_issue",
            "issue_number": payload.get("number"),
            "html_url": payload.get("html_url"),
        }

    def _request_with_reference(
        self,
        method: str,
        path: str,
        credential_ref: str,
        vault: AccountVault,
        body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        return vault.use_secret(credential_ref, lambda token: self._request(method, path, token=token, body=body))

    def _request(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        url = self.config.api_base + path
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agent-account-google-id",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:256]
            raise GitHubProviderError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise GitHubProviderError(f"GitHub API request failed: {exc.reason}") from exc
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise GitHubProviderError("GitHub API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise GitHubProviderError("GitHub API returned an unexpected response")
        return payload

    @staticmethod
    def _safe_user_result(session: ProviderSession, payload: dict[str, Any]) -> dict[str, object]:
        return {
            "ok": True,
            "provider": "github",
            "action": "get_authenticated_user",
            "session_id": session.session_id,
            "account_id": session.account_id,
            "login": payload.get("login"),
            "user_id": payload.get("id"),
            "html_url": payload.get("html_url"),
        }

    @staticmethod
    def _safe_repository(payload: dict[str, Any]) -> dict[str, object]:
        return {
            "id": payload.get("id"),
            "name": payload.get("name"),
            "full_name": payload.get("full_name"),
            "private": payload.get("private"),
            "html_url": payload.get("html_url"),
        }
