from __future__ import annotations

from dataclasses import dataclass, field

from .accounts import AccountError, validate_account_handle
from .agent_identity import AgentIdentityStore
from .browser import BrowserSessionManager
from .runtime import AccountStore, AgentIdentity
from .security import SecurityBoundary
from .web_runtime import SafeWebResult, UniversalWebRuntime, WebActionRequest
from .verification import ChatVerificationHandoff


_OPERATION_PERMISSIONS = {
    "navigate": "web.navigate",
    "search": "web.navigate",
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
    _handoff: ChatVerificationHandoff | None = field(default=None, repr=False)

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

    def verification_chat_event(self, account_handle: str, session_id: str, domain: str) -> dict[str, object] | None:
        self._authorize_session(account_handle, session_id)
        event = ChatVerificationHandoff(self.browser).event_for_session(session_id, domain)
        return event.to_dict() if event else None

    def resume_verification_from_chat(self, account_handle: str, session_id: str, domain: str, message: str) -> dict[str, object]:
        """
        Resume verification from chat.
        Accepts phone number, OTP, or DONE.
        """
        self._authorize_session(account_handle, session_id)

        # 🔥 استخدم نفس الـ handoff لو موجود، وإلا أنشئ واحد جديد
        if self._handoff is None:
            self._handoff = ChatVerificationHandoff(self.browser)
            try:
                driver = self.browser.get_driver(session_id)
                if driver:
                    self._handoff.set_driver(driver)
            except Exception:
                pass

        return self._handoff.resume_from_chat(session_id, domain, message)

    def _authorize_session(self, account_handle: str, session_id: str):
        validate_account_handle(account_handle)
        account = self.accounts.find_by_handle(account_handle)
        self.security.authorize_account(self.identity, account)
        try:
            manifest = self.browser.get(session_id)
        except (FileNotFoundError, ValueError):
            raise AccountError("Agent is not authorized to use this browser session") from None
        if manifest.identity_id != self.identity.identity_id or manifest.account_id != account.account_id:
            raise AccountError("Agent is not authorized to use this browser session")
        return manifest

    def execute(self, account_handle: str, session_id: str, request: WebActionRequest) -> dict[str, object]:
        validate_account_handle(account_handle)
        aggregate = self.identities.assert_account_owner(self.identity.identity_id, account_handle)
        account = self.accounts.find_by_handle(account_handle)
        self.security.authorize_account(self.identity, account)
        required = _OPERATION_PERMISSIONS[request.operation]
        if required not in aggregate.permissions and "web.*" not in aggregate.permissions:
            raise AccountError(f"permission required: {required}")
        manifest = self._authorize_session(account_handle, session_id)
        result: SafeWebResult = self.web.execute(session_id, request)
        aggregate.add_activity(f"web.{request.operation}", session_id, "completed")
        self.identities.save(aggregate)
        return {
            "identity_handle": aggregate.identity_id,
            "account_handle": account.handle,
            "session_id": session_id,
            "result": self.security.safe_object(result.to_dict()),
        }
