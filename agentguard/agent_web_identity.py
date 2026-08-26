from __future__ import annotations

from dataclasses import dataclass

from .accounts import AccountError, validate_account_handle
from .agent_identity import AgentIdentityStore
from .browser import BrowserSessionManager
from .runtime import AccountStore, AgentIdentity
from .security import SecurityBoundary
from .web_runtime import SafeWebResult, UniversalWebRuntime, WebActionRequest


_OPERATION_PERMISSIONS = {
    "navigate": "web.navigate",
    "read": "web.read",
    "click": "web.interact",
    "fill": "web.interact",
    "select": "web.interact",
    "submit": "web.interact",
}


@dataclass
class AgentWebIdentity:
    """The planner-facing identity facade; it owns no planning or raw secrets."""

    identity: AgentIdentity
    identities: AgentIdentityStore
    accounts: AccountStore
    browser: BrowserSessionManager
    web: UniversalWebRuntime
    security: SecurityBoundary

    @classmethod
    def from_runtime(
        cls,
        identity: AgentIdentity,
        root,
        browser: BrowserSessionManager,
        web: UniversalWebRuntime,
    ) -> "AgentWebIdentity":
        root = root.expanduser().resolve()
        return cls(
            identity=identity,
            identities=AgentIdentityStore(root / "agent-identities"),
            accounts=AccountStore(root / "account-records"),
            browser=browser,
            web=web,
            security=SecurityBoundary(),
        )

    def metadata(self) -> dict[str, object]:
        aggregate = self.identities.get(self.identity.identity_id)
        if aggregate.agent_id != self.identity.agent_id:
            raise AccountError("identity ownership mismatch")
        return {
            "identity_handle": aggregate.identity_id,
            "agent_id": aggregate.agent_id,
            "accounts": list(aggregate.account_handles),
            "browser_profiles": list(aggregate.browser_profiles),
            "sessions": list(aggregate.sessions),
            "permissions": list(aggregate.permissions),
            "activity": list(aggregate.activity_history),
            "memory_refs": list(aggregate.memory_refs),
            "lifetime": {
                "created_at": aggregate.created_at,
                "last_seen_at": aggregate.last_seen_at,
                "state": aggregate.lifetime_state,
            },
        }

    def set_permissions(self, permissions: list[str] | tuple[str, ...]) -> dict[str, object]:
        aggregate = self.identities.get(self.identity.identity_id)
        aggregate.set_permissions(permissions)
        self.identities.save(aggregate)
        return self.metadata()

    def execute(self, account_handle: str, session_id: str, request: WebActionRequest) -> dict[str, object]:
        validate_account_handle(account_handle)
        aggregate = self.identities.assert_account_owner(self.identity.identity_id, account_handle)
        account = self.accounts.find_by_handle(account_handle)
        self.security.authorize_account(self.identity, account)
        required = _OPERATION_PERMISSIONS[request.operation]
        if required not in aggregate.permissions and "web.*" not in aggregate.permissions:
            raise AccountError(f"permission required: {required}")
        try:
            manifest = self.browser.get(session_id)
        except (FileNotFoundError, ValueError) as exc:
            raise AccountError("Agent is not authorized to use this browser session") from None
        if manifest.identity_id != self.identity.identity_id or manifest.account_id != account.account_id:
            raise AccountError("Agent is not authorized to use this browser session")
        result: SafeWebResult = self.web.execute(session_id, request)
        aggregate.add_activity(f"web.{request.operation}", session_id, "completed")
        self.identities.save(aggregate)
        return {
            "identity_handle": aggregate.identity_id,
            "account_handle": account.handle,
            "session_id": session_id,
            "result": self.security.safe_object(result.to_dict()),
        }
