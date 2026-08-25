from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running this file directly from a repository checkout.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentguard.events import EventLog
from agentguard.policy import Policy
from agentguard.redaction import Redactor
from agentguard.supervisor import SessionPaths


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude Code hook adapter for AgentGuard")
    parser.add_argument("--event", default="claude.hook")
    parser.add_argument("--sessions-dir", type=Path, default=None)
    args = parser.parse_args()
    session_id = os.environ.get("AGENTGUARD_SESSION_ID")
    if not session_id:
        # A hook outside an AgentGuard session is intentionally a no-op.
        return 0
    root = args.sessions_dir or Path.home() / ".agentguard" / "sessions"
    paths = SessionPaths(root, session_id)
    if not paths.metadata.exists():
        return 0
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": raw}
    workspace = Path(json.loads(paths.metadata.read_text(encoding="utf-8")).get("workspace", Path.cwd()))
    allowed, reason = Policy(workspace).check_tool_payload(str(payload.get("tool_name", "unknown")), payload.get("tool_input", payload))
    EventLog(paths.events, session_id, Redactor()).emit(args.event, {"allowed": allowed, "reason": reason, "input": payload})
    if not allowed:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
