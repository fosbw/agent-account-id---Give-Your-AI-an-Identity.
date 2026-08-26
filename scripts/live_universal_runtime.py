from __future__ import annotations

import json
import shutil
from pathlib import Path

from agentguard.browser import BrowserSessionManager
from agentguard.browser_auth import AgentBrowserAutomation
from agentguard.web_runtime import UniversalWebRuntime, WebActionRequest


ROOT = Path("/tmp/agent-account-universal-live")
SESSION_NAME = "agent-account-universal-live"


def main() -> None:
    shutil.rmtree(ROOT, ignore_errors=True)
    manager = BrowserSessionManager(ROOT / "browser")
    manifest = manager.create(
        ttl=120,
        allowed_domains=("example.com",),
        identity_provider="live-web-runtime-test",
        identity_id="identity-live-test",
        account_id="acct-live-test",
        persistent_profile=True,
    )
    browser = AgentBrowserAutomation(SESSION_NAME, timeout_seconds=30)
    runtime = UniversalWebRuntime(manager, browser)
    try:
        navigated = runtime.execute(
            manifest.session_id,
            WebActionRequest("navigate", url="https://example.com/"),
        )
        read = runtime.execute(manifest.session_id, WebActionRequest("read"))
        print(json.dumps({"navigate": navigated.to_dict(), "read": read.to_dict()}, sort_keys=True))
    finally:
        browser.close()


if __name__ == "__main__":
    main()
