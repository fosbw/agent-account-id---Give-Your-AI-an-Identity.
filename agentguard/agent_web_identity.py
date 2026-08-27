from __future__ import annotations

import pytest
from pathlib import Path
import json

from agentguard.agent_web_identity import AgentWebIdentity
from agentguard.accounts import AccountError
from agentguard.browser import BrowserSessionManager
from agentguard.runtime import AgentIdentity
from agentguard.web_runtime import UniversalWebRuntime, WebActionRequest


@pytest.fixture
def session_id():
    return "test-session-123"


@pytest.fixture
def domain():
    return "google.com"


@pytest.fixture
def account_handle():
    return "agent_account://local/test-account"


@pytest.fixture
def facade(tmp_path):
    # Create test runtime
    root = tmp_path / "agentguard"
    root.mkdir(parents=True, exist_ok=True)
    
    identity = AgentIdentity(
        identity_id="test-identity",
        agent_id="test-agent",
        account_handles=set(),
        browser_profiles=set(),
        sessions=set(),
        permissions={"web.*"},
        activity_history=[],
        memory_refs=[],
        created_at=0.0,
        last_seen_at=0.0,
        lifetime_state="active"
    )
    
    browser = BrowserSessionManager(root / "browser")
    web = UniversalWebRuntime(root / "web")
    
    # Create a test account
    from agentguard.runtime import AccountStore
    accounts = AccountStore(root / "accounts")
    account = accounts.create("test-agent", "Test Account")
    account_handle = account.handle
    
    # Create session
    manifest = browser.create(
        ttl=60.0,
        allowed_domains=("google.com",),
        identity_provider="google",
        identity_id=identity.identity_id,
        account_id=account.account_id,
        persistent_profile=False
    )
    
    return AgentWebIdentity.from_runtime(
        identity=identity,
        root=root,
        browser=browser,
        web=web
    )


def test_verification_chat_event(facade, account_handle, session_id, domain):
    """Test that verification chat event contains the new message format."""
    event = facade.verification_chat_event(account_handle, session_id, domain)
    assert event is not None
    assert event["type"] == "verification_required"
    assert event["session_id"] == session_id
    assert event["domain"] == domain
    assert event["status"] == "awaiting_user_verification"
    
    # 🔥 التعديل هنا: توقع الرسالة الجديدة
    expected_message = (
        "🔐 Verification required.\n\n"
        "📱 Please send:\n"
        "1. Your phone number (international format, e.g., +201234567890)\n"
        "2. After receiving the SMS, send the OTP code (4-6 digits)\n\n"
        "⚠️ Do not send DONE until after you've sent both the phone number and OTP."
    )
    assert event["message"] == expected_message


def test_resume_verification_from_chat_phone_number(facade, account_handle, session_id, domain):
    """Test that phone number is accepted."""
    # 🔥 التعديل هنا: قبول رقم التليفون
    result = facade.resume_verification_from_chat(
        account_handle, session_id, domain, "01234567890"
    )
    assert result["status"] == "phone_received"
    assert "Phone number" in result["message"]
    assert result["next_step"] == "send_otp"


def test_resume_verification_from_chat_otp(facade, account_handle, session_id, domain):
    """Test that OTP is accepted and processed."""
    # First send phone number
    facade.resume_verification_from_chat(
        account_handle, session_id, domain, "01234567890"
    )
    
    # 🔥 التعديل هنا: قبول OTP بدلاً من رفضه
    result = facade.resume_verification_from_chat(
        account_handle, session_id, domain, "123456"
    )
    assert result["status"] == "otp_received"
    assert "OTP" in result["message"]
    assert result["next_step"] == "done"


def test_resume_verification_from_chat_done(facade, account_handle, session_id, domain):
    """Test that DONE is accepted."""
    # First send phone and OTP to complete verification
    facade.resume_verification_from_chat(
        account_handle, session_id, domain, "01234567890"
    )
    facade.resume_verification_from_chat(
        account_handle, session_id, domain, "123456"
    )
    
    result = facade.resume_verification_from_chat(
        account_handle, session_id, domain, "DONE"
    )
    # Should return the browser resume result
    assert "authenticated" in result.get("status", "") or "resumed" in str(result)


def test_resume_verification_from_chat_invalid(facade, account_handle, session_id, domain):
    """Test that invalid input raises error."""
    # 🔥 التعديل هنا: رسالة الخطأ الجديدة
    with pytest.raises(AccountError) as excinfo:
        facade.resume_verification_from_chat(
            account_handle, session_id, domain, "invalid"
        )
    assert "Invalid input" in str(excinfo.value)


def test_resume_verification_from_chat_otp_without_phone(facade, account_handle, session_id, domain):
    """Test that OTP without phone number raises error."""
    with pytest.raises(AccountError) as excinfo:
        facade.resume_verification_from_chat(
            account_handle, session_id, domain, "123456"
        )
    assert "send your phone number first" in str(excinfo.value)
