from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
IDENTITY_SCOPES = ("openid", "email", "profile")


class GoogleOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class GoogleOAuthConfig:
    client_id: str
    scopes: tuple[str, ...] = IDENTITY_SCOPES
    host: str = "127.0.0.1"
    timeout_seconds: int = 300
    user_agent: str = "agent-account-google-id/0.2.0"

    def __post_init__(self) -> None:
        if not self.client_id.strip():
            raise ValueError("Google OAuth client_id is required")
        if set(self.scopes) - set(IDENTITY_SCOPES):
            raise ValueError("only openid/email/profile identity scopes are supported")
        if self.host not in {"127.0.0.1", "::1"}:
            raise ValueError("OAuth callback must bind to loopback")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 900:
            raise ValueError("timeout_seconds must be between 1 and 900")


@dataclass(frozen=True)
class GoogleAuthorization:
    """Short-lived in-memory result; the access token must never be persisted."""

    access_token: str
    token_type: str
    expires_in: int | None
    scope: str
    userinfo: dict

    def safe_metadata(self) -> dict:
        return {
            "provider": "google",
            "subject": self.userinfo.get("sub"),
            "email": self.userinfo.get("email"),
            "email_verified": self.userinfo.get("email_verified"),
            "scopes": self.scope.split(),
            "expires_in": self.expires_in,
        }


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    server_version = "AgentAccountGoogleIDOAuth/0.2"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/oauth2/callback":
            self.send_error(404)
            return
        query = urllib.parse.parse_qs(parsed.query)
        self.server.oauth_result = {key: values[0] for key, values in query.items()}  # type: ignore[attr-defined]
        body = b"Authorization received. You can close this window."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


class GoogleOAuthClient:
    """User-consented Google identity metadata adapter.

    It uses an installed-app loopback callback and PKCE. It deliberately does
    not create accounts, request Gmail/Drive/admin scopes, import browser state,
    automate passwords, or persist access/refresh tokens.
    """

    def __init__(self, config: GoogleOAuthConfig):
        self.config = config

    @staticmethod
    def _pkce_pair() -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return verifier, challenge

    def authorization_url(self, redirect_uri: str, state: str, challenge: str) -> str:
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "access_type": "online",
            "prompt": "consent",
        }
        return GOOGLE_AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params)

    def authorize(self, open_browser: bool = True) -> GoogleAuthorization:
        verifier, challenge = self._pkce_pair()
        state = secrets.token_urlsafe(32)
        server = http.server.HTTPServer((self.config.host, 0), _CallbackHandler)
        port = server.server_address[1]
        redirect_uri = f"http://{self.config.host}:{port}/oauth2/callback"
        url = self.authorization_url(redirect_uri, state, challenge)
        if open_browser:
            import webbrowser

            webbrowser.open(url)
        else:
            print(url)

        server.timeout = 1.0
        deadline = time.monotonic() + self.config.timeout_seconds
        try:
            while time.monotonic() < deadline and not hasattr(server, "oauth_result"):
                server.handle_request()
        finally:
            server.server_close()
        result = getattr(server, "oauth_result", None)
        if not result:
            raise GoogleOAuthError("Google authorization timed out")
        if result.get("error"):
            detail = result.get("error_description") or result["error"]
            raise GoogleOAuthError(f"Google authorization denied: {detail}")
        if not secrets.compare_digest(result.get("state", ""), state):
            raise GoogleOAuthError("OAuth state validation failed")
        code = result.get("code")
        if not code:
            raise GoogleOAuthError("Google callback did not contain an authorization code")
        token = self._exchange_code(code, redirect_uri, verifier)
        access_token = token.get("access_token")
        if not access_token:
            raise GoogleOAuthError("Google token response did not contain an access token")
        try:
            userinfo = self._userinfo(access_token)
            return GoogleAuthorization(
                access_token=access_token,
                token_type=token.get("token_type", "Bearer"),
                expires_in=token.get("expires_in"),
                scope=token.get("scope", " ".join(self.config.scopes)),
                userinfo=userinfo,
            )
        finally:
            access_token = ""

    def _exchange_code(self, code: str, redirect_uri: str, verifier: str) -> dict:
        form = urllib.parse.urlencode(
            {
                "client_id": self.config.client_id,
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            GOOGLE_TOKEN_ENDPOINT,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": self.config.user_agent},
            method="POST",
        )
        return self._json_request(request)

    def _userinfo(self, access_token: str) -> dict:
        request = urllib.request.Request(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}", "User-Agent": self.config.user_agent},
        )
        return self._json_request(request)

    @staticmethod
    def _json_request(request: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:1000]
            raise GoogleOAuthError(f"Google OAuth request failed ({exc.code}): {body}") from exc
        except urllib.error.URLError as exc:
            raise GoogleOAuthError(f"Google OAuth network error: {exc.reason}") from exc
        try:
            return __import__("json").loads(data)
        except ValueError as exc:
            raise GoogleOAuthError("Google OAuth returned invalid JSON") from exc
