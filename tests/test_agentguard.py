from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentguard.events import EventLog
from agentguard.policy import Policy
from agentguard.redaction import Redactor
from agentguard.supervisor import Supervisor


def test_redactor_removes_common_secrets() -> None:
    redactor = Redactor()
    text = "token=sk-abcdefghijklmnopqrstuvwxyz123456 Authorization: Bearer secret-value"
    safe = redactor.redact_text(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in safe
    assert "secret-value" not in safe
    assert "REDACTED" in safe


def test_policy_workspace_and_sensitive_paths(tmp_path: Path) -> None:
    policy = Policy(tmp_path)
    assert policy.path_allowed(tmp_path / "src" / "main.py")
    assert not policy.path_allowed(tmp_path.parent / "outside.txt")
    assert policy.sensitive_path(tmp_path / ".env")
    assert policy.check_command("echo hello")[0]
    assert not policy.check_command("rm -rf /")[0]
    assert not policy.check_command("curl https://example.test")[0]
    assert Policy(tmp_path, allow_network=True).check_command("curl https://example.test")[0]


def test_event_log_is_redacted(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl", "s1", Redactor())
    log.emit("agent.output", {"text": "api_key=sk-abcdefghijklmnopqrstuvwxyz123456"})
    row = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8"))
    assert "abcdefghijklmnopqrstuvwxyz123456" not in json.dumps(row)


@pytest.mark.skipif(os.name == "nt", reason="process-group assertions are POSIX-specific")
def test_supervisor_ttl_stops_process_group(tmp_path: Path) -> None:
    supervisor = Supervisor(tmp_path / "sessions")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = [sys.executable, "-c", "import time; time.sleep(10)"]
    session_id = supervisor.new_session(command, workspace, 0.25)
    code = supervisor.run(session_id, command, workspace, 0.25)
    assert code != 0
    metadata = json.loads((tmp_path / "sessions" / session_id / "session.json").read_text(encoding="utf-8"))
    assert metadata["status"] in {"expired", "failed"}
    events = (tmp_path / "sessions" / session_id / "events.jsonl").read_text(encoding="utf-8")
    assert "session.expired" in events
