import json
import os
import stat
import time
from pathlib import Path

import pytest

from agentguard.browser import BrowserPolicy, BrowserSessionManager


def test_browser_policy_requires_https_and_allowlist():
    policy = BrowserPolicy(("example.com",))
    assert policy.decide("https://example.com/path").allowed
    assert policy.decide("http://example.com/path").allowed is False
    assert policy.decide("https://not-example.com/path").allowed is False
    assert policy.decide("https://user:password@example.com/").allowed is False


def test_browser_policy_blocks_private_and_metadata_targets():
    policy = BrowserPolicy(("example.com", "127.0.0.1"))
    for url in (
        "https://127.0.0.1/",
        "https://10.0.0.1/",
        "https://192.168.1.1/",
        "https://169.254.169.254/latest/meta-data/",
        "https://localhost/",
        "https://service.internal/",
    ):
        assert policy.decide(url).allowed is False


def test_browser_policy_blocks_sensitive_google_services_and_paths():
    policy = BrowserPolicy(("google.com", "example.com"))
    for url in (
        "https://mail.google.com/",
        "https://drive.google.com/",
        "https://myaccount.google.com/",
        "https://payments.google.com/",
        "https://admin.google.com/",
        "https://accounts.google.com/password",
        "https://accounts.google.com/signin/recovery?continue=https://example.com",
    ):
        assert policy.decide(url).allowed is False
    assert policy.decide("https://accounts.google.com/").allowed


def test_browser_session_isolated_profile_and_cleanup(tmp_path: Path):
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(30, ("example.com",), identity_provider="operator-attached")
    profile = Path(manifest.profile_dir)
    assert profile.exists()
    assert manifest.session_id in manifest.profile_dir
    assert "password" not in (tmp_path / "browser" / manifest.session_id / "manifest.json").read_text()

    allowed = manager.request_navigation(manifest.session_id, "https://example.com/task?q=1#fragment")
    assert allowed.allowed
    assert allowed.canonical_url == "https://example.com/task?q=1"
    assert not manager.request_navigation(manifest.session_id, "https://localhost/").allowed

    manager.login_handoff(manifest.session_id, "example.com")
    manager.mark_manual_login_complete(manifest.session_id, "example.com")
    manager.cleanup(manifest.session_id, reason="test_cleanup")

    cleaned = manager.get(manifest.session_id)
    assert cleaned.status == "cleaned"
    assert cleaned.login_completed_by_manual_signal
    assert not profile.exists()
    events = (tmp_path / "browser" / manifest.session_id / "events.jsonl").read_text()
    rows = [json.loads(line) for line in events.splitlines()]
    kinds = [row["kind"] for row in rows]
    assert "browser.login_handoff_required" in kinds
    assert "browser.session_cleanup" in kinds


def test_launch_tracks_process_and_cleanup_stops_it(tmp_path: Path):
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(30, ("example.com",))
    fake_browser = tmp_path / "fake-browser"
    fake_browser.write_text("#!/bin/sh\nsleep 30\n")
    fake_browser.chmod(fake_browser.stat().st_mode | stat.S_IXUSR)
    pid = manager.launch(manifest.session_id, "https://example.com/", browser_bin=str(fake_browser))
    assert pid > 0
    running = manager.get(manifest.session_id)
    assert running.browser_pid == pid
    manager.cleanup(manifest.session_id, reason="test_process_cleanup")
    assert manager.get(manifest.session_id).status == "cleaned"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    else:
        os.kill(pid, 9)
        pytest.fail("tracked browser process still exists after cleanup")


def test_expired_session_rejects_navigation_and_cleans_profile(tmp_path: Path):
    manager = BrowserSessionManager(tmp_path / "browser")
    manifest = manager.create(0.01, ("example.com",))
    time.sleep(0.03)
    decision = manager.request_navigation(manifest.session_id, "https://example.com/")
    assert decision.allowed is False
    assert "expired" in decision.reason
    assert manager.get(manifest.session_id).status == "cleaned"
    assert not Path(manifest.profile_dir).exists()


def test_invalid_domains_and_session_ids_are_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        BrowserPolicy(("https://example.com",))
    manager = BrowserSessionManager(tmp_path / "browser")
    with pytest.raises(ValueError):
        manager.get("../outside")
