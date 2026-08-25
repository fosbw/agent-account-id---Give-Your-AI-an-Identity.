from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .events import EventLog
from .policy import Policy
from .redaction import Redactor
from .supervisor import SessionPaths, Supervisor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentguard", description="Local session supervisor for AI coding agents")
    parser.add_argument("--sessions-dir", type=Path, default=None, help="session storage directory")
    sub = parser.add_subparsers(dest="action", required=True)

    run = sub.add_parser("run", help="run an agent under supervision")
    run.add_argument("--ttl", type=float, required=True, help="wall-clock duration in seconds")
    run.add_argument("--workspace", type=Path, default=Path.cwd())
    run.add_argument("--sessions-dir", type=Path, default=argparse.SUPPRESS)
    run.add_argument("--allow-network", action="store_true", help="allow network-capable command guardrails")
    run.add_argument("command", nargs=argparse.REMAINDER, help="command after --")

    for name in ("stop", "pause", "resume"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--sessions-dir", type=Path, default=argparse.SUPPRESS)
        cmd.add_argument("session_id")
        if name == "stop":
            cmd.add_argument("--reason", default="user_stop")

    watch = sub.add_parser("watch", help="follow a session JSONL event stream")
    watch.add_argument("--sessions-dir", type=Path, default=argparse.SUPPRESS)
    watch.add_argument("session_id")
    watch.add_argument("--follow", action="store_true")
    watch.add_argument("--json", action="store_true")

    ls = sub.add_parser("list", help="list local sessions")
    ls.add_argument("--sessions-dir", type=Path, default=argparse.SUPPRESS)
    ls.add_argument("--json", action="store_true")

    hook = sub.add_parser("hook", help="ingest a Claude Code hook payload from stdin")
    hook.add_argument("--sessions-dir", type=Path, default=argparse.SUPPRESS)
    hook.add_argument("--session-id", required=True)
    hook.add_argument("--event", default="claude.hook")

    check = sub.add_parser("policy-check", help="check a command or path against local guardrails")
    check.add_argument("--sessions-dir", type=Path, default=argparse.SUPPRESS)
    check.add_argument("--workspace", type=Path, default=Path.cwd())
    check.add_argument("--allow-network", action="store_true")
    check.add_argument("--command")
    check.add_argument("--path")
    return parser


def supervisor_from(args) -> Supervisor:
    return Supervisor(args.sessions_dir)


def cmd_run(args) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("run requires a command after --")
    supervisor = supervisor_from(args)
    session_id = supervisor.new_session(command, args.workspace, args.ttl, args.allow_network)
    print(f"AGENTGUARD_SESSION_ID={session_id}", flush=True)
    return supervisor.run(session_id, command, args.workspace, args.ttl, args.allow_network)


def cmd_watch(args) -> int:
    supervisor = supervisor_from(args)
    paths = SessionPaths(supervisor.root, args.session_id)
    if not paths.events.exists():
        raise SystemExit(f"session not found: {args.session_id}")
    redactor = Redactor()
    position = 0
    while True:
        with paths.events.open("r", encoding="utf-8") as fh:
            fh.seek(position)
            while True:
                line = fh.readline()
                if not line:
                    break
                position = fh.tell()
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if args.json:
                    print(json.dumps(redactor.redact_object(row), ensure_ascii=False), flush=True)
                else:
                    payload = row.get("payload", {})
                    text = payload.get("text") if isinstance(payload, dict) else None
                    detail = text or json.dumps(payload, ensure_ascii=False)
                    print(f"[{row.get('kind')}] {detail}", flush=True)
        if not args.follow:
            return 0
        status = None
        try:
            status = json.loads(paths.metadata.read_text(encoding="utf-8")).get("status")
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        if status in {"completed", "failed", "expired"}:
            return 0
        time.sleep(0.25)


def cmd_list(args) -> int:
    supervisor = supervisor_from(args)
    rows = []
    for directory in sorted(supervisor.root.iterdir()) if supervisor.root.exists() else []:
        if not directory.is_dir() or not (directory / "session.json").exists():
            continue
        try:
            rows.append(json.loads((directory / "session.json").read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{row.get('session_id')}\t{row.get('status')}\t{row.get('workspace')}\t{row.get('command')}")
    return 0


def cmd_hook(args) -> int:
    supervisor = supervisor_from(args)
    paths = SessionPaths(supervisor.root, args.session_id)
    if not paths.metadata.exists():
        raise SystemExit(f"session not found: {args.session_id}")
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": raw}
    EventLog(paths.events, args.session_id, Redactor()).emit(args.event, payload)
    print(json.dumps({"ok": True, "event": args.event}))
    return 0


def cmd_policy_check(args) -> int:
    policy = Policy(args.workspace, allow_network=args.allow_network)
    if args.command is not None:
        allowed, reason = policy.check_command(args.command)
        print(json.dumps({"allowed": allowed, "reason": reason}))
        return 0 if allowed else 2
    if args.path is not None:
        allowed = policy.path_allowed(args.path) and not policy.sensitive_path(args.path)
        reason = "allowed" if allowed else "path blocked by workspace or sensitive-path policy"
        print(json.dumps({"allowed": allowed, "reason": reason}))
        return 0 if allowed else 2
    raise SystemExit("policy-check requires --command or --path")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "run":
        return cmd_run(args)
    if args.action == "watch":
        return cmd_watch(args)
    if args.action == "list":
        return cmd_list(args)
    if args.action == "hook":
        return cmd_hook(args)
    if args.action == "policy-check":
        return cmd_policy_check(args)
    supervisor = supervisor_from(args)
    if args.action == "stop":
        supervisor.stop(args.session_id, args.reason)
    elif args.action == "pause":
        supervisor.pause(args.session_id)
    elif args.action == "resume":
        supervisor.resume(args.session_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
