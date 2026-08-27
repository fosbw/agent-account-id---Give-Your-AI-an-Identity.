from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.accounts import AccountError, AgentAccount
from agentguard.agent_identity import AgentIdentityStore
from agentguard.agent_web_identity import AgentWebIdentity
from agentguard.browser import BrowserSessionManager
from agentguard.runtime import AccountStore, AgentIdentity
from agentguard.verification import ChatVerificationHandoff
from agentguard.web_runtime import UniversalWebRuntime


class FakeElement:
    def __init__(self, driver: "FakeDriver", name: str) -> None:
        self.driver = driver
        self.name = name
        self.values: list[str] = []

    def clear(self) -> None:
        self.values.clear()

    def send_keys(self, value: str) -> None:
        self.values.append(value)
        self.driver.inputs[self.name] = value

    def click(self) -> None:
        self.driver.clicked.append(self.name)


class FakeDriver:
    def __init__(self, otp_page_persists: bool = False) -> None:
        self.otp_page_persists = otp_page_persists
        self.inputs: dict[str, str] = {}
        self.clicked: list[str] = []

    def find_element(self, by: object, value: str) -> FakeElement:
        if value == "code" and not self.otp_page_persists and "verify" in self.clicked:
            raise LookupError("code field no longer present")
        return FakeElement(self, value)

    def click(self) -> None:
        return None

    def mark_click(self, value: str) -> None:
        self.clicked.append(value)


class FakeWait:
    def __init__(self, driver: FakeDriver, timeout: int) -> None:
        self.driver = driver

    def until(self, condition):
        return condition(self.driver)


def make_handoff(tmp_path: Path) -> ChatVerificationHandoff:
    return ChatVerificationHandoff(BrowserSessionManager(tmp_path / "browser"))


def test_done_before_phone_or_otp_is_rejected(tmp_path: Path) -> None:
    handoff = make_handoff(tmp_path)
    with pytest.raises(AccountError, match="Verification not completed"):
        handoff.resume_from_chat("session", "example.test", "Done")


def test_invalid_inputs_are_rejected(tmp_path: Path) -> None:
    handoff = make_handoff(tmp_path)
    with pytest.raises(AccountError, match="Invalid input"):
        handoff.resume_from_chat("session", "example.test", "not-a-phone-or-code")
    with pytest.raises(AccountError, match="send your phone number first"):
        handoff.resume_from_chat("session", "example.test", "123456")


def test_driver_unavailable_returns_safe_state(tmp_path: Path) -> None:
    handoff = make_handoff(tmp_path)
    result = handoff.enter_phone_number("01234567890")
    assert "driver not available" in result
    assert handoff.verification_completed is False


def test_fake_driver_otp_failure_keeps_state_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handoff = make_handoff(tmp_path)
    driver = FakeDriver(otp_page_persists=True)
    handoff.set_driver(driver)
    monkeypatch.setattr("agentguard.verification.time.sleep", lambda _seconds: None)
    result = handoff.enter_otp("123456")
    assert "verification failed" in result.lower()
    assert handoff.verification_completed is False


def test_fake_driver_otp_success_requires_page_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handoff = make_handoff(tmp_path)
    driver = FakeDriver(otp_page_persists=False)
    handoff.set_driver(driver)
    monkeypatch.setattr("agentguard.verification.time.sleep", lambda _seconds: None)
    result = handoff.enter_otp("123456")
    assert "verified" in result.lower()
    assert handoff.verification_completed is True


def test_event_does_not_contain_test_otp(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(60, ("example.test",))
    manager.begin_verification_handoff(manifest.session_id, "otp_required", "example.test")
    event = ChatVerificationHandoff(manager).event_for_session(manifest.session_id, "example.test")
    assert event is not None
    assert "987654" not in str(event.to_dict())
    assert "password" not in str(event.to_dict()).casefold()


def test_persistent_profile_survives_manager_restart(tmp_path: Path) -> None:
    root = tmp_path / "browser"
    first = BrowserSessionManager(root)
    manifest = first.create(
        60,
        ("example.test",),
        identity_provider="example",
        identity_id="identity-a",
        account_id="acct-a",
        persistent_profile=True,
    )
    second = BrowserSessionManager(root)
    restored = second.get(manifest.session_id)
    assert restored.account_id == "acct-a"
    assert restored.identity_id == "identity-a"
    assert restored.profile_dir == manifest.profile_dir
    assert Path(restored.profile_dir).is_dir()


def test_wrong_agent_session_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    identity = AgentIdentity("identity-a", "agent-a", "example", "fingerprint", 1.0)
    identities = AgentIdentityStore(root / "agent-identities")
    aggregate = identities.create(identity.identity_id, identity.agent_id, identity.provider, identity.key_fingerprint)
    account = AgentAccount(
        account_id="acct-a", handle="agent_account://example/acct-a", display_name="A",
        agent_id="agent-a", provider="example", identity_id="identity-a", state="active",
        created_at=1.0, updated_at=1.0, session_state="active",
    )
    aggregate.register_account(account.handle, "/profiles/acct-a", "secret-ref-a")
    aggregate.set_permissions(("web.read",))
    identities.save(aggregate)
    accounts = AccountStore(root / "account-records")
    accounts.save(account)
    manager = BrowserSessionManager(root / "browser")
    other = manager.create(60, ("example.test",), identity_provider="example", identity_id="identity-b", account_id="acct-b")
    facade = AgentWebIdentity.from_runtime(identity, root, manager, UniversalWebRuntime(manager, object()))
    with pytest.raises(AccountError, match="not authorized"):
        facade._authorize_session(account.handle, other.session_id)


def test_handoff_state_is_reused_by_facade(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    identity = AgentIdentity("identity-a", "agent-a", "example", "fingerprint", 1.0)
    identities = AgentIdentityStore(root / "agent-identities")
    aggregate = identities.create(identity.identity_id, identity.agent_id, identity.provider, identity.key_fingerprint)
    account = AgentAccount(
        account_id="acct-a", handle="agent_account://example/acct-a", display_name="A",
        agent_id="agent-a", provider="example", identity_id="identity-a", state="active",
        created_at=1.0, updated_at=1.0, session_state="active",
    )
    aggregate.register_account(account.handle, "/profiles/acct-a", "secret-ref-a")
    aggregate.set_permissions(("web.read",))
    identities.save(aggregate)
    accounts = AccountStore(root / "account-records")
    accounts.save(account)
    manager = BrowserSessionManager(root / "browser")
    manifest = manager.create(60, ("example.test",), identity_provider="example", identity_id="identity-a", account_id="acct-a")
    facade = AgentWebIdentity.from_runtime(identity, root, manager, UniversalWebRuntime(manager, object()))
    phone = facade.resume_verification_from_chat(account.handle, manifest.session_id, "example.test", "01234567890")
    assert phone["status"] == "phone_received"
    first_handoff = facade._handoff
    otp = facade.resume_verification_from_chat(account.handle, manifest.session_id, "example.test", "123456")
    assert otp["status"] == "otp_received"
    assert facade._handoff is first_handoff
    assert facade._handoff is not None
    assert facade._handoff.phone_number == "01234567890"


def test_repeated_done_can_be_idempotent_with_completed_handoff(tmp_path: Path) -> None:
    handoff = make_handoff(tmp_path)
    handoff.phone_number = "01234567890"
    handoff.otp_code = "123456"
    handoff.verification_completed = True
    handoff.browser.resume_after_verification = lambda _session, _domain: {
        "status": "resume_requested",
        "authentication_recheck_required": True,
    }
    first = handoff.resume_from_chat("session", "example.test", "Done")
    second = handoff.resume_from_chat("session", "example.test", "Done")
    assert first == second


def test_unallowed_domain_is_blocked(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(60, ("example.test",))
    decision = manager.request_navigation(manifest.session_id, "https://not-allowed.test/")
    assert decision.allowed is False
    assert "allowlist" in decision.reason


def test_invalid_input_error_does_not_echo_sensitive_candidate(tmp_path: Path) -> None:
    handoff = make_handoff(tmp_path)
    candidate = "987654"
    with pytest.raises(AccountError) as exc_info:
        handoff.resume_from_chat("session", "example.test", candidate)
    assert candidate not in str(exc_info.value)
