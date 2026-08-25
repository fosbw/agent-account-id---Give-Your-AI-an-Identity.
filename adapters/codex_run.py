from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentguard.supervisor import Supervisor


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Codex CLI under AgentGuard supervision")
    parser.add_argument("--ttl", type=float, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="usually: codex ...")
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        command = ["codex"]
    supervisor = Supervisor()
    session_id = supervisor.new_session(command, args.workspace, args.ttl, args.allow_network)
    print(f"AGENTGUARD_SESSION_ID={session_id}", flush=True)
    return supervisor.run(session_id, command, args.workspace, args.ttl, args.allow_network)


if __name__ == "__main__":
    raise SystemExit(main())
