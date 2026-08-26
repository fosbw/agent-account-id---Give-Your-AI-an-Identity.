from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .accounts import AccountError
from .browser import BrowserSessionManager


_CHALLENGE_STATES = frozenset(
    {
        "email_required",
        "phone_required",
        "otp_required",
        "mfa_required",
        "captcha_detected",
        "provider_blocked",
    }
)
_DONE_MESSAGES = frozenset({"done", "تم", "completed", "تم التحقق", "verification completed"})


class VerificationRequired(AccountError):
    """Provider reported a verification challenge; no code is carried here."""

    def __init__(self, state: str):
        if state not in _CHALLENGE_STATES:
            raise ValueError("unsupported verification challenge")
        self.state = state
        super().__init__("provider verification is required")


@dataclass(frozen=True)
class ChatVerificationEvent:
    session_id: str
    domain: str
    verification_state: str
    message: str
    status: str = "awaiting_user_verification"

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "verification_required",
            "session_id": self.session_id,
            "domain": self.domain,
            "verification_state": self.verification_state,
            "status": self.status,
            "message": self.message,
        }


class ChatVerificationHandoff:
    """
    Chat-safe bridge that accepts phone number and OTP from chat,
    then sends them to the browser automatically.
    """

    def __init__(self, browser: BrowserSessionManager, driver=None):
        self.browser = browser
        self.driver = driver
        self.phone_number: Optional[str] = None
        self.otp_code: Optional[str] = None
        self.verification_completed: bool = False

    def event_for_session(self, session_id: str, domain: str) -> ChatVerificationEvent | None:
        manifest = self.browser.get(session_id)
        if manifest.verification_state not in _CHALLENGE_STATES:
            return None
        return ChatVerificationEvent(
            session_id=session_id,
            domain=domain,
            verification_state=manifest.verification_state,
            message=(
                "🔐 Verification required.\n\n"
                "📱 Please send:\n"
                "1. Your phone number (11 digits, e.g., 01234567890)\n"
                "2. After receiving the SMS, send the OTP code (4-6 digits)\n\n"
                "⚠️ Do not send DONE until after you've sent both the phone number and OTP."
            ),
        )
def resume_from_chat(self, session_id: str, domain: str, message: str) -> dict[str, object]:
    """
    Accepts phone number, OTP, or DONE from chat.
    - Phone number: international format (e.g., +201234567890, 01234567890, +1 234 567 890)
    - OTP: 4-6 digits
    - DONE: signals completion
    """
    normalized = " ".join((message or "").strip().split())
    normalized_lower = normalized.casefold()

    # 1️⃣ Check if it's a DONE message
    if normalized_lower in _DONE_MESSAGES:
        if not self.verification_completed:
            raise AccountError(
                "⚠️ Verification not completed yet. "
                "Please send your phone number and OTP code first."
            )
        return self.browser.resume_after_verification(session_id, domain)

    # 2️⃣ Check if it's a phone number (international format)
    # Supports: +201234567890, 01234567890, +1 234 567 890, 0049123456789
    phone_pattern = re.compile(
        r'^(\+?\d{1,4}[\s\-]?)?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,9}$'
    )
    if re.match(r'^\+?[0-9\s\-()]{7,20}$', normalized):
        self.phone_number = normalized
        self.verification_completed = False
        
        # 🔥 Automatically enter phone number in browser
        result = self.enter_phone_number(normalized)
        
        return {
            "status": "phone_received",
            "message": f"✅ {result}",
            "next_step": "send_otp"
        }

    # 3️⃣ Check if it's an OTP code (4-6 digits)
    if re.match(r'^[0-9]{4,6}$', normalized):
        if not self.phone_number:
            raise AccountError(
                "⚠️ Please send your phone number first, then the OTP code."
            )
        
        self.otp_code = normalized
        self.verification_completed = True
        
        # 🔥 Automatically enter OTP in browser
        result = self.enter_otp(normalized)
        
        return {
            "status": "otp_received",
            "message": f"✅ {result}",
            "next_step": "done"
        }

    # 4️⃣ Invalid input
    raise AccountError(
        "⚠️ Invalid input.\n"
        "Please send:\n"
        "- Phone number: international format (e.g., +201234567890, 01234567890)\n"
        "- OTP code: 4-6 digits\n"
        "- DONE: after completing verification"
    )

    def set_driver(self, driver):
        """Set the Selenium driver for automatic input."""
        self.driver = driver

    def enter_phone_number(self, phone: str) -> str:
        """Enter phone number into the browser automatically."""
        if not self.driver:
            return "❌ Browser driver not available. Please complete verification manually in the browser."

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            phone_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "phoneNumberId"))
            )
            phone_input.clear()
            phone_input.send_keys(phone)
            self.driver.find_element(By.ID, "next").click()
            return "✅ Phone number entered. Waiting for OTP..."
        except Exception as e:
            return f"❌ Failed to enter phone number: {e}"

    def enter_otp(self, otp: str) -> str:
        """Enter OTP code into the browser automatically."""
        if not self.driver:
            return "❌ Browser driver not available. Please complete verification manually in the browser."

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            otp_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "code"))
            )
            otp_input.clear()
            otp_input.send_keys(otp)
            self.driver.find_element(By.ID, "verify").click()
            self.verification_completed = True
            return "✅ OTP code entered. Verification complete!"
        except Exception as e:
            return f"❌ Failed to enter OTP: {e}"
