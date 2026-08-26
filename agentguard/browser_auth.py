from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .accounts import AccountError, AccountVault
from .browser import BrowserSessionManager
from .provider import ProviderSession


@dataclass(frozen=True)
class LoginRequest:
    account_handle: str
    target: str
    login_url: str
    session_id: str
    profile_dir: Path | None = None


@dataclass(frozen=True)
class SafeAuthenticationState:
    authenticated: bool
    account_handle: str
    provider: str
    session_id: str
    browser_session_id: str
    current_url: str
    page: str | None
    action: str
    verification_state: str

    def to_dict(self) -> dict[str, object]:
        return {
            "authenticated": self.authenticated,
            "account_handle": self.account_handle,
            "provider": self.provider,
            "session_id": self.session_id,
            "browser_session_id": self.browser_session_id,
            "current_url": self.current_url,
            "page": self.page,
            "action": self.action,
            "verification_state": self.verification_state,
        }


class BrowserAutomation(Protocol):
    def open(self, url: str, profile_dir: Path) -> None:
        ...

    def snapshot(self) -> dict[str, Any]:
        ...

    def fill(self, selector: str, value: str) -> None:
        ...

    def submit(self, selector: str) -> None:
        ...

    def current_url(self) -> str:
        ...

    def page_text(self) -> str:
        ...

    def close(self) -> None:
        ...


class LoginAdapter(Protocol):
    provider: str
    target: str

    def login(self, request: LoginRequest, vault: AccountVault, browser: BrowserAutomation) -> ProviderSession:
        ...


class BrowserAuthenticationRuntime:
    """Coordinates provider login inside an already-isolated browser session."""

    def __init__(self, browser_manager: BrowserSessionManager, vault: AccountVault):
        self.browser_manager = browser_manager
        self.vault = vault

    def login(self, request: LoginRequest, adapter: LoginAdapter, browser: BrowserAutomation) -> SafeAuthenticationState:
        manifest = self.browser_manager.get(request.session_id)
        if manifest.account_id is None:
            raise AccountError("browser session is not attached to an Agent Account")
        account_id = request.account_handle.rsplit("/", 1)[-1]
        if account_id != manifest.account_id:
            raise AccountError("login request account handle does not match browser account")
        self.browser_manager.record_login_state(request.session_id, "login_required", request.target)
        self.browser_manager.record_login_state(request.session_id, "authenticating", request.target)
        try:
            session = adapter.login(request, self.vault, browser)
            self.browser_manager.record_provider_session(request.session_id, session.safe_metadata())
            self.browser_manager.record_verification_state(request.session_id, "completed", request.target)
            self.browser_manager.record_login_state(request.session_id, "active", request.target)
            current_url = browser.current_url()
            page = self._safe_page_label(browser.page_text())
            self.browser_manager.record_browser_state(request.session_id, current_url, page, "authenticated")
            return SafeAuthenticationState(
                authenticated=session.authenticated,
                account_handle=request.account_handle,
                provider=session.provider,
                session_id=session.session_id,
                browser_session_id=request.session_id,
                current_url=current_url,
                page=page,
                action="authenticated",
                verification_state="completed",
            )
        except Exception:
            self.browser_manager.record_login_state(request.session_id, "failed", request.target)
            raise

    @staticmethod
    def _safe_page_label(text: str) -> str | None:
        if not text:
            return None
        first = re.sub(r"\s+", " ", text).strip()
        return first[:128] or None


class AgentBrowserAutomation:
    """Subprocess driver for agent-browser with an isolated named session."""

    def __init__(self, session_name: str, executable: str = "agent-browser", timeout_seconds: int = 30):
        self.session_name = session_name
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.profile_dir: Path | None = None

    def _run(self, *args: str, stdin: str | None = None) -> str:
        command = [self.executable, "--session", self.session_name]
        if self.profile_dir is not None:
            command.extend(["--profile", str(self.profile_dir)])
        command.extend(args)
        try:
            result = subprocess.run(
                command,
                input=stdin,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AccountError(f"agent-browser command failed: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[:512]
            raise AccountError(f"agent-browser command failed: {detail}")
        return result.stdout.strip()

    def open(self, url: str, profile_dir: Path) -> None:
        self.profile_dir = profile_dir.resolve()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._run("open", url)

    def snapshot(self) -> dict[str, Any]:
        raw = self._run("snapshot", "-i", "--json")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AccountError("agent-browser returned invalid snapshot JSON") from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise AccountError("agent-browser snapshot was not successful")
        data = payload.get("data", {})
        return data if isinstance(data, dict) else {}

    def fill(self, selector: str, value: str) -> None:
        self._run("fill", selector, value)

    def submit(self, selector: str) -> None:
        self._run("click", selector)

    def current_url(self) -> str:
        return self._run("get", "url")

    def page_text(self) -> str:
        return self._run("get", "text", "body")

    def close(self) -> None:
        try:
            self._run("close")
        except AccountError:
            pass


class DemoCredentialProvider:
    """Loads public Demo credentials supplied through an internal process boundary."""

    username_env = "AGENT_ACCOUNT_DEMO_USERNAME"
    password_env = "AGENT_ACCOUNT_DEMO_PASSWORD"

    @classmethod
    def install(cls, account_handle: str, vault: AccountVault) -> str:
        username = os.environ.get(cls.username_env)
        password = os.environ.get(cls.password_env)
        if not username or not password:
            raise AccountError(
                "Demo credentials must be supplied through the internal demo credential boundary"
            )
        return vault.put_secret(
            account_handle,
            "demo_login",
            json.dumps({"username": username, "password": password}),
        )


class DemoLoginAdapter:
    """First narrowly scoped login integration for the public demo site."""

    provider = "demo-site"
    target = "the-internet.herokuapp.com"
    login_path = "/login"
    success_path = "/secure"

    def login(self, request: LoginRequest, vault: AccountVault, browser: BrowserAutomation) -> ProviderSession:
        if request.target != self.target:
            raise AccountError("DemoLoginAdapter only handles the configured demo target")
        if not request.login_url.startswith("https://the-internet.herokuapp.com/login"):
            raise AccountError("demo login URL is outside the configured target")
        browser.open(request.login_url, request.profile_dir or Path("."))
        snapshot = browser.snapshot()
        refs = snapshot.get("refs", {}) if isinstance(snapshot, dict) else {}
        username_ref = self._find_ref(refs, "Username")
        password_ref = self._find_ref(refs, "Password")
        submit_ref = self._find_ref(refs, "Login", role="button")
        credential_ref = self._credential_ref(request.account_handle, vault)

        def fill_and_submit(secret: str) -> ProviderSession:
            credentials = json.loads(secret)
            browser.fill(username_ref, credentials["username"])
            browser.fill(password_ref, credentials["password"])
            browser.submit(submit_ref)
            url = browser.current_url()
            page = browser.page_text()
            if not url.endswith(self.success_path) or "Secure Area" not in page:
                raise AccountError("demo authentication did not reach the secure area")
            now = time.time()
            return ProviderSession(
                session_id="demo-session-" + uuid.uuid4().hex[:12],
                provider=self.provider,
                account_id=request.account_handle.rsplit("/", 1)[-1],
                credential_ref=credential_ref,
                provider_session_ref="demo-provider-session-" + uuid.uuid4().hex[:12],
                state="active",
                authenticated=True,
                created_at=now,
                updated_at=now,
            )

        return vault.use_secret(credential_ref, fill_and_submit)

    @staticmethod
    def _credential_ref(handle: str, vault: AccountVault) -> str:
        try:
            return vault.find_active_secret_reference(handle, "demo_login")
        except FileNotFoundError as exc:
            raise AccountError("demo credentials are not configured for this account") from exc

    @staticmethod
    def _find_ref(refs: dict[str, Any], name: str, role: str | None = None) -> str:
        # Prefer an exact accessible-name match so instructional headings do
        # not win merely because they contain words such as Username/Password.
        for exact in (True, False):
            for ref, payload in refs.items():
                if not isinstance(payload, dict):
                    continue
                actual_name = str(payload.get("name") or "")
                matches_name = actual_name == name if exact else name.casefold() in actual_name.casefold()
                matches_role = role is None or payload.get("role") == role
                if matches_name and matches_role:
                    return "@" + str(ref)
        raise AccountError(f"login form element not found: {name}")
