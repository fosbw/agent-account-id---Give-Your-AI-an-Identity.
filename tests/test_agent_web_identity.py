from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.accounts import AccountError, AgentAccount
from agentguard.agent_identity import AgentIdentityStore
from agentguard.agent_web_identity import AgentWebIdentity
from agentguard.browser import BrowserSessionManager
from agentguard.runtime import AccountStore, AgentIdentity
from agentguard.web_runtime import UniversalWebRuntime, WebActionRequest


class FacadeFakeBrowser:
    def __init__(self) -> None:
        self.url = "https://example.test/"
        self.page = "Dashboard"

    def open(self, url: str, profile_dir: Path) -> None:
        self.url = url

    def snapshot(self) -> dict:
        return {"refs": {}}

    def fill(self, selector: str, value: str) -> None:
        return None

    def select(self, selector: str, value: str) -> None:
        return None

    def check(self, selector: str) -> None:
        return None

    def click(self, selector: str) -> None:
        return None

    def submit(self, selector: str) -> None:
        return None

    def press(self, key: str) -> None:
        return None

    def wait_for_load(self) -> None:
        return None

    def current_url(self) -> str:
        return self.url

    def page_text(self) -> str:
        return self.page

    def close(self) -> None:
        return None


def _facade(tmp_path: Path) -> tuple[AgentWebIdentity, FacadeFakeBrowser, str, str]:
    root = tmp_path / "runtime"
    identity = AgentIdentity("identity-a", "agent-a", "example", "fingerprint", 1.0)
    aggregate_store = AgentIdentityStore(root / "agent-identities")
    aggregate = aggregate_store.create(identity.identity_id, identity.agent_id, identity.provider, identity.key_fingerprint)
    account = AgentAccount(
        account_id="acct-a",
        handle="agent_account://example/acct-a",
        display_name="Agent A account",
        agent_id="agent-a",
        provider="example",
        identity_id=identity.identity_id,
        state="active",
        created_at=1.0,
        updated_at=1.0,
        session_state="active",
    )
    aggregate.register_account(account.handle, "/profiles/acct-a", "secret-ref-a")
    aggregate.set_permissions(("web.read", "web.navigate", "web.interact"))
    aggregate_store.save(aggregate)
    accounts = AccountStore(root / "account-records")
    accounts.save(account)
    manager = BrowserSessionManager(root / "browser")
    manifest = manager.create(
        60,
        ("example.test",),
        identity_provider="example",
        identity_id=identity.identity_id,
        account_id=account.account_id,
        persistent_profile=True,
    )
    browser = FacadeFakeBrowser()
    web = UniversalWebRuntime(manager, browser)
    facade = AgentWebIdentity.from_runtime(identity, root, manager, web)
    return facade, browser, manifest.session_id, account.handle


def test_agent_web_identity_executes_safe_action_and_records_activity(tmp_path: Path) -> None:
    facade, browser, session_id, handle = _facade(tmp_path)
    browser.page = "Authenticated dashboard password=do-not-return token=hidden"

    result = facade.execute(handle, session_id, WebActionRequest("read"))

    assert result["identity_handle"] == "identity-a"
    assert result["account_handle"] == handle
    safe_result = str(result["result"])
    assert "do-not-return" not in safe_result
    assert "hidden" not in safe_result
    metadata = facade.metadata()
    assert metadata["activity"][-1]["action"] == "web.read"


def test_agent_web_identity_enforces_explicit_permissions(tmp_path: Path) -> None:
    facade, _browser, session_id, handle = _facade(tmp_path)
    facade.set_permissions(("web.navigate",))

    with pytest.raises(AccountError, match="permission required: web.read"):
        facade.execute(handle, session_id, WebActionRequest("read"))


# ========== 🔥 التعديلات الجديدة ==========

def test_agent_web_identity_chat_event_contains_new_message(tmp_path: Path) -> None:
    """Test that verification chat event contains the new message format."""
    facade, _browser, session_id, handle = _facade(tmp_path)

    assert facade.verification_chat_event(handle, session_id, "example.test") is None

    facade.browser.begin_verification_handoff(session_id, "otp_required", "example.test")
    event = facade.verification_chat_event(handle, session_id, "example.test")
    assert event is not None
    assert event["type"] == "verification_required"
    assert event["verification_state"] == "otp_required"
    
    # 🔥 الرسالة الجديدة
    expected_message = (
        "🔐 Verification required.\n\n"
        "📱 Please send:\n"
        "1. Your phone number (international format, e.g., +201234567890)\n"
        "2. After receiving the SMS, send the OTP code (4-6 digits)\n\n"
        "⚠️ Do not send DONE until after you've sent both the phone number and OTP."
    )
    assert event["message"] == expected_message
    assert "123456" not in str(event)


def test_agent_web_identity_chat_resume_accepts_phone_and_otp(tmp_path: Path) -> None:
    """Test that resume_from_chat accepts phone number and OTP."""
    facade, _browser, session_id, handle = _facade(tmp_path)
    facade.browser.begin_verification_handoff(session_id, "mfa_required", "example.test")

    # 🔥 إرسال رقم التليفون (مقبول دلوقتي)
    phone_result = facade.resume_verification_from_chat(handle, session_id, "example.test", "01234567890")
    assert phone_result["status"] == "phone_received"
    assert phone_result["next_step"] == "send_otp"

    # 🔥 إرسال OTP (مقبول دلوقتي)
    otp_result = facade.resume_verification_from_chat(handle, session_id, "example.test", "123456")
    assert otp_result["status"] == "otp_received"
    assert otp_result["next_step"] == "done"

    # 🔥 إرسال DONE
    resumed = facade.resume_verification_from_chat(handle, session_id, "example.test", "Done")
    assert resumed["status"] == "resume_requested"
    assert resumed["authentication_recheck_required"] is True


def test_agent_web_identity_resume_rejects_invalid_input(tmp_path: Path) -> None:
    """Test that invalid input raises error."""
    facade, _browser, session_id, handle = _facade(tmp_path)
    facade.browser.begin_verification_handoff(session_id, "mfa_required", "example.test")

    # 🔥 إدخال غير صالح
    with pytest.raises(AccountError, match="Invalid input"):
        facade.resume_verification_from_chat(handle, session_id, "example.test", "invalid")

    # 🔥 OTP بدون رقم
    with pytest.raises(AccountError, match="send your phone number first"):
        facade.resume_verification_from_chat(handle, session_id, "example.test", "123456")


def test_agent_web_identity_rejects_wrong_browser_session(tmp_path: Path) -> None:
    facade, _browser, session_id, handle = _facade(tmp_path)
    other_manager = BrowserSessionManager(tmp_path / "other-browser")
    other_manifest = other_manager.create(
        60,
        ("example.test",),
        identity_provider="example",
        identity_id="identity-b",
        account_id="acct-b",
        persistent_profile=True,
    )

    with pytest.raises(AccountError, match="not authorized to use this browser session"):
        facade.execute(handle, other_manifest.session_id, WebActionRequest("read"))
