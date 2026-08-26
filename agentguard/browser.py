from __future__ import annotations

import ipaddress
import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .events import EventLog
from .redaction import Redactor


DEFAULT_BLOCKED_HOSTS = (
    "mail.google.com",
    "drive.google.com",
    "myaccount.google.com",
    "payments.google.com",
    "admin.google.com",
)
DEFAULT_BLOCKED_GOOGLE_PATHS = (
    "/password",
    "/recovery",
    "/recover",
    "/signin/challenge",
    "/signin/recovery",
)
PRIVATE_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}


@dataclass(frozen=True)
class BrowserDecision:
    allowed: bool
    reason: str
    canonical_url: str | None = None


@dataclass(frozen=True)
class BrowserPolicy:
    """Conservative URL policy; it is a guardrail, not a network sandbox."""

    allowed_domains: tuple[str, ...]
    blocked_hosts: tuple[str, ...] = DEFAULT_BLOCKED_HOSTS
    blocked_google_paths: tuple[str, ...] = DEFAULT_BLOCKED_GOOGLE_PATHS
    https_only: bool = True

    def __post_init__(self) -> None:
        domains = tuple(self._normalize_domain(value) for value in self.allowed_domains if value.strip())
        if not domains:
            raise ValueError("at least one allowed domain is required")
        object.__setattr__(self, "allowed_domains", domains)
        object.__setattr__(self, "blocked_hosts", tuple(self._normalize_domain(value) for value in self.blocked_hosts))

    @staticmethod
    def _normalize_domain(value: str) -> str:
        value = value.strip().lower().rstrip(".")
        if "://" in value or "/" in value or not value:
            raise ValueError(f"domain must be a hostname only: {value!r}")
        try:
            return value.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"invalid domain: {value!r}") from exc

    @staticmethod
    def _private_or_local(host: str) -> bool:
        if host in PRIVATE_HOSTNAMES or host.endswith(".localhost") or host.endswith(".internal"):
            return True
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False
        return address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified

    @staticmethod
    def _host_matches(host: str, domain: str) -> bool:
        return host == domain or host.endswith("." + domain)

    def decide(self, url: str, purpose: str = "navigate") -> BrowserDecision:
        if purpose not in {"navigate", "login_handoff"}:
            return BrowserDecision(False, "downloads and uploads require an explicit future policy")
        try:
            parsed = urlsplit(url)
        except ValueError:
            return BrowserDecision(False, "malformed URL")
        if parsed.scheme.lower() not in ({"https"} if self.https_only else {"http", "https"}):
            return BrowserDecision(False, "only HTTPS navigation is allowed")
        if parsed.username is not None or parsed.password is not None:
            return BrowserDecision(False, "credentials in URLs are blocked")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return BrowserDecision(False, "URL has no hostname")
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return BrowserDecision(False, "invalid hostname")
        if self._private_or_local(host):
            return BrowserDecision(False, "localhost, private, link-local, metadata, and reserved hosts are blocked")
        if any(self._host_matches(host, blocked) for blocked in self.blocked_hosts):
            return BrowserDecision(False, "sensitive Google service is blocked")
        path = parsed.path or "/"
        if host == "accounts.google.com" and any(path.lower().startswith(rule) for rule in self.blocked_google_paths):
            return BrowserDecision(False, "Google recovery, password, and challenge paths are blocked")
        if not any(self._host_matches(host, allowed) for allowed in self.allowed_domains):
            return BrowserDecision(False, "hostname is not in the explicit allowlist")
        canonical = urlunsplit((parsed.scheme.lower(), host, path, parsed.query, ""))
        return BrowserDecision(True, "allowed by explicit browser policy", canonical)


@dataclass
class BrowserSessionManifest:
    session_id: str
    identity_provider: str
    identity_id: str | None
    account_id: str | None
    persistent_profile: bool
    allowed_domains: tuple[str, ...]
    created_at: float
    expires_at: float
    status: str = "created"
    profile_dir: str = ""
    browser_pid: int | None = None
    browser_pgid: int | None = None
    login_handoff_required: bool = True
    login_completed_by_manual_signal: bool = False
    cleanup_at: float | None = None
    metadata_version: int = 1
    login_state: str = "not_started"
    verification_state: str = "not_detected"
    current_url: str | None = None
    current_page: str | None = None
    current_action: str = "idle"


class BrowserSessionManager:
    """Manage an ephemeral browser profile without handling passwords or cookies."""

    def __init__(self, root: Path | None = None):
        configured = os.environ.get("AGENTGUARD_BROWSER_ROOT")
        self.root = (root or Path(configured) if configured else root or Path.home() / ".agentguard" / "browser-sessions").expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._processes: dict[str, subprocess.Popen] = {}

    def create(
        self,
        ttl: float,
        allowed_domains: tuple[str, ...],
        identity_provider: str = "operator-attached",
        identity_id: str | None = None,
        account_id: str | None = None,
        persistent_profile: bool = False,
    ) -> BrowserSessionManifest:
        if ttl <= 0:
            raise ValueError("ttl must be greater than zero")
        policy = BrowserPolicy(allowed_domains)
        session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        directory = self._directory(session_id)
        directory.mkdir(parents=True, exist_ok=False)
        if persistent_profile:
            if not account_id or "/" in account_id or "\\" in account_id:
                raise ValueError("persistent profiles require a safe account_id")
            profile = self.root / "profiles" / account_id
            profile.mkdir(parents=True, exist_ok=True)
        else:
            profile = directory / "profile"
            profile.mkdir()
        manifest = BrowserSessionManifest(
            session_id=session_id,
            identity_provider=identity_provider,
            identity_id=identity_id,
            account_id=account_id,
            persistent_profile=persistent_profile,
            allowed_domains=policy.allowed_domains,
            created_at=time.time(),
            expires_at=time.time() + ttl,
            profile_dir=str(profile),
        )
        self._write(manifest)
        self._log(manifest, "browser.session_created", {"ttl_seconds": ttl, "allowed_domains": list(policy.allowed_domains), "identity_provider": identity_provider, "identity_id": identity_id, "account_id": account_id, "persistent_profile": persistent_profile})
        return manifest

    def request_navigation(self, session_id: str, url: str, purpose: str = "navigate") -> BrowserDecision:
        manifest = self.get(session_id)
        if time.time() >= manifest.expires_at:
            self.cleanup(session_id, reason="ttl_expired")
            return BrowserDecision(False, "browser session expired")
        decision = BrowserPolicy(manifest.allowed_domains).decide(url, purpose=purpose)
        self._log(manifest, "browser.navigation.allowed" if decision.allowed else "browser.navigation.blocked", {"url": decision.canonical_url or url, "purpose": purpose, "reason": decision.reason})
        return decision

    def login_handoff(self, session_id: str, domain: str) -> None:
        manifest = self.get(session_id)
        decision = BrowserPolicy(manifest.allowed_domains).decide("https://" + domain + "/", purpose="login_handoff")
        if not decision.allowed:
            raise ValueError(f"login handoff blocked: {decision.reason}")
        manifest.login_state = "login_required"
        manifest.current_action = "login_handoff_required"
        self._write(manifest)
        self._log(manifest, "browser.login_handoff_required", {"domain": domain, "operator_action": "complete login manually in the isolated browser window"})

    def mark_manual_login_complete(self, session_id: str, domain: str) -> None:
        manifest = self.get(session_id)
        decision = BrowserPolicy(manifest.allowed_domains).decide("https://" + domain + "/", purpose="login_handoff")
        if not decision.allowed:
            raise ValueError(f"login completion blocked: {decision.reason}")
        manifest.login_completed_by_manual_signal = True
        manifest.login_state = "active"
        manifest.verification_state = "operator_asserted_unverified"
        manifest.current_action = "login_completed_signal"
        self._write(manifest)
        self._log(manifest, "browser.login_manual_signal", {"domain": domain, "verified": False})

    def launch(self, session_id: str, start_url: str, browser_bin: str | None = None) -> int:
        manifest = self.get(session_id)
        decision = self.request_navigation(session_id, start_url)
        if not decision.allowed:
            raise ValueError(f"start URL blocked: {decision.reason}")
        executable = browser_bin or os.environ.get("AGENTGUARD_BROWSER_BIN") or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
        if not executable:
            raise FileNotFoundError("no Chromium-compatible browser found; set AGENTGUARD_BROWSER_BIN")
        command = [executable, f"--user-data-dir={manifest.profile_dir}", "--no-first-run", "--no-default-browser-check", "--disable-sync", decision.canonical_url or start_url]
        proc = subprocess.Popen(command, start_new_session=os.name != "nt", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pgid = os.getpgid(proc.pid) if os.name != "nt" else None
        manifest.status = "running"
        manifest.browser_pid = proc.pid
        manifest.browser_pgid = pgid
        self._processes[session_id] = proc
        self._write(manifest)
        manifest.current_url = decision.canonical_url
        manifest.current_action = "browser_launched"
        self._write(manifest)
        self._log(manifest, "browser.launch_requested", {"pid": proc.pid, "pgid": pgid, "start_url": decision.canonical_url})
        return proc.pid

    def record_browser_state(self, session_id: str, url: str, page: str | None = None, action: str = "observed") -> BrowserDecision:
        manifest = self.get(session_id)
        decision = self.request_navigation(session_id, url)
        if not decision.allowed:
            return decision
        if page is not None and (len(page) > 256 or "\n" in page or "\r" in page):
            raise ValueError("page label must be a short single-line value")
        if len(action) > 256 or "\n" in action or "\r" in action:
            raise ValueError("action must be a short single-line value")
        manifest.current_url = decision.canonical_url
        manifest.current_page = page
        manifest.current_action = action
        self._write(manifest)
        self._log(manifest, "browser.state_updated", {"url": decision.canonical_url, "page": page, "action": action})
        return decision

    def record_login_state(self, session_id: str, state: str, domain: str) -> None:
        allowed = {"not_started", "login_required", "authenticating", "active", "failed", "revoked"}
        if state not in allowed:
            raise ValueError("unsupported login state")
        manifest = self.get(session_id)
        decision = BrowserPolicy(manifest.allowed_domains).decide("https://" + domain + "/", purpose="login_handoff")
        if not decision.allowed:
            raise ValueError(f"login state blocked: {decision.reason}")
        manifest.login_state = state
        manifest.current_action = "login_state_updated"
        self._write(manifest)
        self._log(manifest, "browser.login_state", {"domain": domain, "state": state})

    def record_provider_session(self, session_id: str, metadata: dict[str, object]) -> None:
        """Persist provider-session metadata without accepting raw credentials."""
        manifest = self.get(session_id)
        safe = {str(key): value for key, value in metadata.items()}
        forbidden = {"password", "cookie", "cookies", "token", "secret", "client_secret"}
        if any(any(word in key.lower() for word in forbidden) for key in safe):
            raise ValueError("provider session metadata cannot contain secret fields")
        (self._directory(session_id) / "provider-session.json").write_text(
            json.dumps(safe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        self._log(
            manifest,
            "browser.provider_session_recorded",
            {"provider": safe.get("provider"), "session_id": safe.get("session_id"), "state": safe.get("state")},
        )

    def get_provider_session(self, session_id: str) -> dict[str, object]:
        self.get(session_id)
        path = self._directory(session_id) / "provider-session.json"
        if not path.exists():
            raise FileNotFoundError(f"provider session not found for browser session: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _revoke_provider_session(self, session_id: str) -> None:
        path = self._directory(session_id) / "provider-session.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        data["state"] = "revoked"
        data["authenticated"] = False
        data["updated_at"] = time.time()
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def record_verification_state(self, session_id: str, state: str, domain: str) -> None:
        allowed = {"not_detected", "email_required", "phone_required", "otp_required", "mfa_required", "captcha_detected", "provider_blocked", "completed"}
        if state not in allowed:
            raise ValueError("unsupported verification state")
        manifest = self.get(session_id)
        decision = BrowserPolicy(manifest.allowed_domains).decide("https://" + domain + "/", purpose="login_handoff")
        if not decision.allowed:
            raise ValueError(f"verification state blocked: {decision.reason}")
        manifest.verification_state = state
        manifest.current_action = "verification_state_detected"
        self._write(manifest)
        self._log(manifest, "browser.verification_state", {"domain": domain, "state": state})

    def wait_until_expired(self, session_id: str, poll_seconds: float = 0.25) -> None:
        manifest = self.get(session_id)
        while time.time() < manifest.expires_at:
            time.sleep(min(poll_seconds, max(0.01, manifest.expires_at - time.time())))
        self.cleanup(session_id, reason="ttl_expired")

    def cleanup(self, session_id: str, reason: str = "user_cleanup") -> None:
        manifest = self.get(session_id)
        proc = self._processes.pop(session_id, None)
        if manifest.browser_pid:
            self._stop_process(manifest.browser_pid, manifest.browser_pgid)
        if proc is not None:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        profile = Path(manifest.profile_dir).resolve()
        profile_deleted = False
        if not manifest.persistent_profile and profile.parent == self._directory(session_id).resolve() and profile.name == "profile" and profile.exists():
            shutil.rmtree(profile)
            profile_deleted = True
        self._revoke_provider_session(session_id)
        manifest.status = "cleaned"
        manifest.cleanup_at = time.time()
        manifest.browser_pid = None
        manifest.browser_pgid = None
        manifest.current_action = "session_cleaned"
        self._write(manifest)
        self._log(manifest, "browser.session_cleanup", {"reason": reason, "profile_deleted": profile_deleted, "persistent_profile_retained": manifest.persistent_profile})

    def get(self, session_id: str) -> BrowserSessionManifest:
        if not session_id or "/" in session_id or "\\" in session_id or session_id in {".", ".."}:
            raise ValueError("invalid browser session id")
        path = self._directory(session_id) / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"browser session not found: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("account_id", None)
        data.setdefault("persistent_profile", False)
        return BrowserSessionManifest(**data)

    def _directory(self, session_id: str) -> Path:
        return self.root / session_id

    def _write(self, manifest: BrowserSessionManifest) -> None:
        path = self._directory(manifest.session_id) / "manifest.json"
        path.write_text(json.dumps(asdict(manifest), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _log(self, manifest: BrowserSessionManifest, kind: str, payload: dict) -> None:
        EventLog(self._directory(manifest.session_id) / "events.jsonl", manifest.session_id, Redactor()).emit(kind, payload)

    @staticmethod
    def _stop_process(pid: int, pgid: int | None) -> None:
        try:
            if os.name != "nt" and pgid and pgid not in {os.getpgrp(), 1}:
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.2)
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
            else:
                os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
