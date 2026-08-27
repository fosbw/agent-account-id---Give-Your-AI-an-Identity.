from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from agentguard.accounts import AccountError, AgentAccount
from agentguard.agent_identity import AgentIdentityStore
from agentguard.agent_web_identity import AgentWebIdentity
from agentguard.browser import BrowserSessionManager
from agentguard.runtime import AccountStore, AgentIdentity
from agentguard.web_runtime import UniversalWebRuntime, WebActionRequest


class ConcurrentFakeBrowser:
    def __init__(self, agent_index: int) -> None:
        self.agent_index = agent_index
        self.page = f"Agent {agent_index} dashboard password=hidden-{agent_index} token=secret-{agent_index}"
        self.url = "https://example.test/"

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


def make_agent(tmp_path: Path, shared_browser_root: Path, index: int) -> tuple[AgentWebIdentity, str, str, str]:
    root = tmp_path / f"agent-{index}"
    identity = AgentIdentity(
        f"identity-{index}", f"agent-{index}", "example", f"fingerprint-{index}", 1.0
    )
    identities = AgentIdentityStore(root / "agent-identities")
    aggregate = identities.create(identity.identity_id, identity.agent_id, identity.provider, identity.key_fingerprint)
    account = AgentAccount(
        account_id=f"acct-{index}",
        handle=f"agent_account://example/acct-{index}",
        display_name=f"Agent {index}",
        agent_id=identity.agent_id,
        provider="example",
        identity_id=identity.identity_id,
        state="active",
        created_at=1.0,
        updated_at=1.0,
        session_state="active",
    )
    aggregate.register_account(account.handle, f"/profiles/acct-{index}", f"secret-ref-{index}")
    aggregate.set_permissions(("web.read", "web.navigate", "web.interact"))
    identities.save(aggregate)
    accounts = AccountStore(root / "account-records")
    accounts.save(account)
    browser = BrowserSessionManager(shared_browser_root)
    manifest = browser.create(
        120,
        ("example.test",),
        identity_provider="example",
        identity_id=identity.identity_id,
        account_id=account.account_id,
        persistent_profile=True,
    )
    facade = AgentWebIdentity.from_runtime(
        identity,
        root,
        browser,
        UniversalWebRuntime(browser, ConcurrentFakeBrowser(index)),
    )
    return facade, account.handle, manifest.session_id, manifest.profile_dir


def test_concurrent_agents_isolate_actions_and_metadata(tmp_path: Path) -> None:
    count = 16
    barrier = Barrier(count)
    shared_browser_root = tmp_path / "shared-browser"

    def worker(index: int) -> dict[str, object]:
        facade, handle, session_id, profile_dir = make_agent(tmp_path, shared_browser_root, index)
        barrier.wait(timeout=10)
        results = [facade.execute(handle, session_id, WebActionRequest("read")) for _ in range(4)]
        safe_text = str(results[-1]["result"])
        metadata = facade.metadata()
        return {
            "index": index,
            "identity": metadata["identity_handle"],
            "handle": handle,
            "session": session_id,
            "profile": profile_dir,
            "safe_text": safe_text,
            "activity_count": len(metadata["activity"]),
        }

    with ThreadPoolExecutor(max_workers=count) as executor:
        rows = list(executor.map(worker, range(count)))

    assert len({row["identity"] for row in rows}) == count
    assert len({row["handle"] for row in rows}) == count
    assert len({row["session"] for row in rows}) == count
    assert len({row["profile"] for row in rows}) == count
    for row in rows:
        assert row["activity_count"] == 4
        assert f"hidden-{row['index']}" not in str(row["safe_text"])
        assert f"secret-{row['index']}" not in str(row["safe_text"])


def test_cross_agent_access_is_rejected_after_parallel_setup(tmp_path: Path) -> None:
    shared_browser_root = tmp_path / "shared-browser"
    first = make_agent(tmp_path, shared_browser_root, 1)
    second = make_agent(tmp_path, shared_browser_root, 2)
    facade_a, handle_a, session_a, _ = first
    _facade_b, handle_b, session_b, _ = second

    with pytest.raises(AccountError, match="not authorized"):
        facade_a.execute(handle_b, session_b, WebActionRequest("read"))
    with pytest.raises(AccountError, match="not authorized"):
        facade_a._authorize_session(handle_a, session_b)
    with pytest.raises((AccountError, FileNotFoundError)):
        facade_a._authorize_session(handle_b, session_a)


def test_concurrent_restart_restores_all_profiles(tmp_path: Path) -> None:
    count = 12
    shared_browser_root = tmp_path / "shared-browser"
    rows = [make_agent(tmp_path, shared_browser_root, index) for index in range(count)]

    def restore(row: tuple[AgentWebIdentity, str, str, str]) -> tuple[str, str, str]:
        _facade, handle, session_id, profile_dir = row
        restored_manager = BrowserSessionManager(shared_browser_root)
        manifest = restored_manager.get(session_id)
        return handle, manifest.session_id, manifest.profile_dir

    with ThreadPoolExecutor(max_workers=count) as executor:
        restored = list(executor.map(restore, rows))

    assert len({item[0] for item in restored}) == count
    assert len({item[1] for item in restored}) == count
    assert {item[2] for item in restored} == {item[3] for item in rows}
    assert all(Path(profile_dir).is_dir() for _handle, _session, profile_dir in restored)
