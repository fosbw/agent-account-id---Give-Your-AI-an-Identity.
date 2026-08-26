from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .accounts import AccountError, validate_account_handle


@dataclass
class AgentIdentityAggregate:
    """Persistent safe view of one Agent's web identity graph."""

    identity_id: str
    agent_id: str
    provider: str
    key_fingerprint: str
    created_at: float
    last_seen_at: float
    lifetime_state: str = "active"
    account_handles: list[str] = field(default_factory=list)
    browser_profiles: list[str] = field(default_factory=list)
    credential_refs: list[str] = field(default_factory=list)
    sessions: list[dict[str, object]] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    activity_history: list[dict[str, object]] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)

    def safe_metadata(self) -> dict[str, object]:
        return asdict(self)

    def register_account(
        self,
        account_handle: str,
        browser_profile: str | None = None,
        credential_ref: str | None = None,
    ) -> None:
        validate_account_handle(account_handle)
        if account_handle not in self.account_handles:
            self.account_handles.append(account_handle)
        if browser_profile and browser_profile not in self.browser_profiles:
            self.browser_profiles.append(browser_profile)
        if credential_ref and credential_ref not in self.credential_refs:
            self.credential_refs.append(credential_ref)
        self.touch()

    def register_session(self, metadata: dict[str, object]) -> None:
        forbidden = ("password", "cookie", "token", "secret", "private_key")
        if any(any(word in str(key).casefold() for word in forbidden) for key in metadata):
            raise AccountError("identity session metadata cannot contain secret fields")
        safe = {
            "session_id": metadata.get("session_id"),
            "provider": metadata.get("provider"),
            "account_id": metadata.get("account_id"),
            "provider_session_ref": metadata.get("provider_session_ref"),
            "state": metadata.get("state"),
            "authenticated": metadata.get("authenticated"),
            "updated_at": metadata.get("updated_at"),
        }
        self.sessions = [row for row in self.sessions if row.get("session_id") != safe.get("session_id")]
        self.sessions.append(safe)
        self.touch()

    def add_activity(self, action: str, session_id: str | None = None, result: str = "completed") -> None:
        if not action or "\n" in action or "\r" in action or len(action) > 160:
            raise AccountError("activity action must be a bounded single-line value")
        self.activity_history.append({
            "action": action,
            "session_id": session_id,
            "result": result,
            "at": time.time(),
        })
        self.activity_history = self.activity_history[-100:]
        self.touch()

    def register_memory_ref(self, memory_ref: str) -> None:
        if not memory_ref or "\n" in memory_ref or "\r" in memory_ref or len(memory_ref) > 256:
            raise AccountError("memory reference must be a bounded non-secret value")
        if memory_ref not in self.memory_refs:
            self.memory_refs.append(memory_ref)
        self.touch()

    def set_permissions(self, permissions: list[str] | tuple[str, ...]) -> None:
        clean = sorted({permission.strip() for permission in permissions if permission.strip()})
        if any("\n" in permission or len(permission) > 120 for permission in clean):
            raise AccountError("permission must be a bounded single-line value")
        self.permissions = clean
        self.touch()

    def touch(self) -> None:
        self.last_seen_at = time.time()


class AgentIdentityStore:
    """Safe aggregate storage; raw credentials and browser state never enter it."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, identity: AgentIdentityAggregate) -> None:
        path = self._path(identity.identity_id)
        path.write_text(json.dumps(identity.safe_metadata(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def get(self, identity_id: str) -> AgentIdentityAggregate:
        if not identity_id or "/" in identity_id or "\\" in identity_id:
            raise ValueError("invalid identity id")
        path = self._path(identity_id)
        if not path.exists():
            raise FileNotFoundError(f"agent identity not found: {identity_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise AccountError("agent identity metadata is invalid")
        return AgentIdentityAggregate(**data)

    def create(self, identity_id: str, agent_id: str, provider: str, key_fingerprint: str) -> AgentIdentityAggregate:
        now = time.time()
        identity = AgentIdentityAggregate(identity_id, agent_id, provider, key_fingerprint, now, now)
        self.save(identity)
        return identity

    def assert_account_owner(self, identity_id: str, account_handle: str) -> AgentIdentityAggregate:
        identity = self.get(identity_id)
        validate_account_handle(account_handle)
        if account_handle not in identity.account_handles:
            raise AccountError("Agent is not authorized to use this account")
        identity.touch()
        self.save(identity)
        return identity

    def _path(self, identity_id: str) -> Path:
        return self.root / f"{identity_id}.json"
