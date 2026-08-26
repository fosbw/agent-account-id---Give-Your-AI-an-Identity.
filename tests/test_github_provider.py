import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from agentguard.accounts import AccountVault
from agentguard.github_provider import GitHubProviderAdapter, GitHubProviderConfig, GitHubProviderError


class _GitHubHandler(BaseHTTPRequestHandler):
    seen_authorization = []

    def do_GET(self):  # noqa: N802
        self.seen_authorization.append(self.headers.get("Authorization"))
        if self.path == "/user":
            self._send(200, {"id": 42, "login": "agent-bot", "html_url": "https://github.com/agent-bot"})
            return
        if self.path == "/installation/repositories":
            self._send(200, {"repositories": [{"id": 7, "name": "demo", "full_name": "agent/demo", "private": True, "html_url": "https://github.com/agent/demo"}]})
            return
        self._send(404, {"message": "not found"})

    def do_POST(self):  # noqa: N802
        self.seen_authorization.append(self.headers.get("Authorization"))
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/repos/agent/demo/issues" and payload.get("title") == "Approved issue":
            self._send(201, {"number": 1, "html_url": "https://github.com/agent/demo/issues/1"})
            return
        self._send(404, {"message": "not found"})

    def log_message(self, *_args):
        return

    def _send(self, status, payload):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


@pytest.fixture
def github_server():
    _GitHubHandler.seen_authorization.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GitHubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_github_provider_authentication_and_web_actions(github_server, tmp_path: Path):
    config = GitHubProviderConfig(
        api_base=f"http://127.0.0.1:{github_server.server_port}",
        installation_id="12345",
        token="synthetic-github-token",
    )
    adapter = GitHubProviderAdapter(config)
    vault = AccountVault(tmp_path / "vault")
    account = adapter.provision_account("agent-key", "github-agent", "GitHub Agent")
    credential_ref = adapter.initialize_credentials(account, vault, "agent-key")
    session = adapter.authenticate(account, credential_ref, vault)

    assert account.account_id == "github-installation-12345"
    assert account.handle == "agent_account://github/12345"
    assert session.authenticated is True
    assert session.provider == "github"
    assert adapter.execute_action(session, "get_authenticated_user", vault)["login"] == "agent-bot"
    repositories = adapter.execute_action(session, "list_installation_repositories", vault)
    assert repositories["repository_count"] == 1
    assert repositories["repositories"][0]["full_name"] == "agent/demo"
    assert all(value == "Bearer synthetic-github-token" for value in _GitHubHandler.seen_authorization)

    with pytest.raises(GitHubProviderError, match="explicit confirmation"):
        adapter.create_issue(session, vault, "agent", "demo", "Approved issue")
    created = adapter.create_issue(session, vault, "agent", "demo", "Approved issue", confirm=True)
    assert created["issue_number"] == 1

    safe = config.safe_metadata()
    assert safe["token_configured"] is True
    assert "synthetic-github-token" not in json.dumps(safe)
    assert "synthetic-github-token" not in json.dumps(session.safe_metadata())


def test_github_provider_requires_existing_installation_and_token(tmp_path: Path):
    no_installation = GitHubProviderAdapter(GitHubProviderConfig(token="token"))
    with pytest.raises(Exception, match="installation ID"):
        no_installation.provision_account("key", "agent", "Agent")

    no_token = GitHubProviderAdapter(GitHubProviderConfig(installation_id="1"))
    account = no_token.provision_account("key", "agent", "Agent")
    with pytest.raises(Exception, match="credentials are unavailable"):
        no_token.initialize_credentials(account, AccountVault(tmp_path / "vault"), "key")
