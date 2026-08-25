from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .browser import BrowserSessionManager
from .events import EventLog
from .identity import GoogleIdentityMetadataAdapter, IdentityStore, OperatorAttachedIdentityAdapter
from .policy import Policy
from .redaction import Redactor
from .supervisor import SessionPaths, Supervisor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentguard", description="Controlled sessions for user-owned AI agents")
    parser.add_argument("--sessions-dir", type=Path, default=None, help="agent session storage directory")
    sub = parser.add_subparsers(dest="action", required=True)

    run = sub.add_parser("run", help="run an agent under supervision")
    run.add_argument("--ttl", type=float, required=True, help="wall-clock duration in seconds")
    run.add_argument("--workspace", type=Path, default=Path.cwd())
    run.add_argument("--sessions-dir", type=Path, default=argparse.SUPPRESS)
    run.add_argument("--allow-network", action="store_true", help="allow network-capable command guardrails")
    run.add_argument("--identity-id", default=None, help="non-secret identity reference for an automatic browser session")
    run.add_argument("--identity-dir", type=Path, default=None)
    run.add_argument("--allow-domain", action="append", dest="allowed_domains", default=None, help="approved browser domain; repeat for more domains")
    run.add_argument("--browser-start-url", default=None, help="approved HTTPS URL to open with the session")
    run.add_argument("--browser-bin", default=None, help="Chromium-compatible executable")
    run.add_argument("--browser-dir", type=Path, default=None)
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

    ls = sub.add_parser("list", help="list local agent sessions")
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

    identity = sub.add_parser("identity", help="manage non-secret identity references")
    identity_sub = identity.add_subparsers(dest="identity_action", required=True)
    attach = identity_sub.add_parser("attach", help="attach provider-authorized identity metadata")
    attach.add_argument("--identity-dir", type=Path, default=None)
    attach.add_argument("--provider", choices=("google", "operator-attached"), required=True)
    attach.add_argument("--subject", required=True)
    attach.add_argument("--email")
    attach.add_argument("--email-verified", action="store_true")
    attach.add_argument("--authorization-basis", choices=("operator_authorized", "provider_authorized", "test_account"), default="operator_authorized")
    identity_show = identity_sub.add_parser("show", help="show safe identity metadata")
    identity_show.add_argument("--identity-dir", type=Path, default=None)
    identity_show.add_argument("identity_id")
    identity_revoke = identity_sub.add_parser("revoke", help="revoke local identity metadata")
    identity_revoke.add_argument("--identity-dir", type=Path, default=None)
    identity_revoke.add_argument("identity_id")

    browser = sub.add_parser("browser", help="manage an isolated, operator-authorized browser session")
    browser_sub = browser.add_subparsers(dest="browser_action", required=True)

    create = browser_sub.add_parser("create", help="create an ephemeral browser session manifest")
    create.add_argument("--browser-dir", type=Path, default=None)
    create.add_argument("--ttl", type=float, required=True)
    create.add_argument("--allow-domain", action="append", dest="allowed_domains", required=True)
    create.add_argument("--identity-provider", default="operator-attached")
    create.add_argument("--identity-id", default=None, help="non-secret identity reference created with identity attach")

    launch = browser_sub.add_parser("launch", help="launch a browser profile after URL policy approval")
    launch.add_argument("--browser-dir", type=Path, default=None)
    launch.add_argument("session_id")
    launch.add_argument("--url", required=True)
    launch.add_argument("--browser-bin", default=None)
    launch.add_argument("--detach", action="store_true", help="return without waiting for TTL cleanup")

    navigate = browser_sub.add_parser("check-url", help="evaluate a URL against the session allowlist")
    navigate.add_argument("--browser-dir", type=Path, default=None)
    navigate.add_argument("session_id")
    navigate.add_argument("url")
    navigate.add_argument("--purpose", choices=("navigate", "login_handoff"), default="navigate")

    handoff = browser_sub.add_parser("login-handoff", help="record that an operator must log in manually")
    handoff.add_argument("--browser-dir", type=Path, default=None)
    handoff.add_argument("session_id")
    handoff.add_argument("domain")

    complete = browser_sub.add_parser("login-complete", help="record an operator's manual login signal")
    complete.add_argument("--browser-dir", type=Path, default=None)
    complete.add_argument("session_id")
    complete.add_argument("domain")

    cleanup = browser_sub.add_parser("cleanup", help="stop the browser and delete its ephemeral profile")
    cleanup.add_argument("--browser-dir", type=Path, default=None)
    cleanup.add_argument("session_id")
    cleanup.add_argument("--reason", default="user_cleanup")

    show = browser_sub.add_parser("show", help="show non-secret browser session metadata")
    show.add_argument("--browser-dir", type=Path, default=None)
    show.add_argument("session_id")
    return parser


def supervisor_from(args) -> Supervisor:
    return Supervisor(args.sessions_dir)


def browser_from(args) -> BrowserSessionManager:
    return BrowserSessionManager(args.browser_dir)


def identity_store_from(args) -> IdentityStore:
    root = args.identity_dir or Path.home() / ".agentguard" / "identities"
    return IdentityStore(root)


def cmd_run(args) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("run requires a command after --")
    supervisor = supervisor_from(args)
    browser_manager = None
    browser_manifest = None
    requested_browser = bool(args.identity_id or args.allowed_domains or args.browser_start_url)
    if requested_browser:
        if not args.identity_id or not args.allowed_domains:
            raise SystemExit("automatic browser context requires --identity-id and at least one --allow-domain")
        try:
            identity_store_from(args).get(args.identity_id)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            raise SystemExit(f"identity reference is not attached: {args.identity_id}") from exc
        browser_manager = BrowserSessionManager(args.browser_dir)
        browser_manifest = browser_manager.create(args.ttl, tuple(args.allowed_domains), identity_provider="google", identity_id=args.identity_id)
    try:
        session_id = supervisor.new_session(command, args.workspace, args.ttl, args.allow_network)
        print(f"AGENTGUARD_SESSION_ID={session_id}", flush=True)
        extra_env = None
        if browser_manifest is not None and browser_manager is not None:
            extra_env = {
                "AGENTGUARD_IDENTITY_ID": args.identity_id,
                "AGENTGUARD_BROWSER_SESSION_ID": browser_manifest.session_id,
                "AGENTGUARD_BROWSER_PROFILE": browser_manifest.profile_dir,
                "AGENTGUARD_BROWSER_ALLOWED_DOMAINS": ",".join(browser_manifest.allowed_domains),
            }
            if args.browser_start_url:
                browser_manager.launch(browser_manifest.session_id, args.browser_start_url, args.browser_bin)
        return supervisor.run(session_id, command, args.workspace, args.ttl, args.allow_network, extra_env=extra_env)
    finally:
        if browser_manager is not None and browser_manifest is not None:
            browser_manager.cleanup(browser_manifest.session_id, reason="agent_session_finished")


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


def cmd_identity(args) -> int:
    store = identity_store_from(args)
    if args.identity_action == "attach":
        metadata = {
            "provider": args.provider,
            "subject": args.subject,
            "email": args.email,
            "email_verified": args.email_verified,
            "authorization_basis": args.authorization_basis,
        }
        adapter = GoogleIdentityMetadataAdapter() if args.provider == "google" else OperatorAttachedIdentityAdapter()
        identity = adapter.attach(metadata)
        store.save(identity)
        print(json.dumps(identity.safe_metadata(), ensure_ascii=False, indent=2))
        return 0
    if args.identity_action == "show":
        print(json.dumps(store.get(args.identity_id).safe_metadata(), ensure_ascii=False, indent=2))
        return 0
    if args.identity_action == "revoke":
        store.revoke(args.identity_id)
        print(json.dumps({"ok": True, "identity_id": args.identity_id, "revoked": True}))
        return 0
    raise SystemExit("unknown identity action")


def cmd_browser(args) -> int:
    manager = browser_from(args)
    if args.browser_action == "create":
        manifest = manager.create(args.ttl, tuple(args.allowed_domains), args.identity_provider, args.identity_id)
        print(json.dumps(asdict(manifest), ensure_ascii=False, indent=2))
        return 0
    if args.browser_action == "launch":
        pid = manager.launch(args.session_id, args.url, args.browser_bin)
        print(json.dumps({"session_id": args.session_id, "browser_pid": pid, "detached": args.detach}))
        if not args.detach:
            manager.wait_until_expired(args.session_id)
        return 0
    if args.browser_action == "check-url":
        decision = manager.request_navigation(args.session_id, args.url, args.purpose)
        print(json.dumps(asdict(decision), ensure_ascii=False))
        return 0 if decision.allowed else 2
    if args.browser_action == "login-handoff":
        manager.login_handoff(args.session_id, args.domain)
        print(json.dumps({"ok": True, "event": "browser.login_handoff_required", "domain": args.domain}))
        return 0
    if args.browser_action == "login-complete":
        manager.mark_manual_login_complete(args.session_id, args.domain)
        print(json.dumps({"ok": True, "event": "browser.login_manual_signal", "domain": args.domain, "verified": False}))
        return 0
    if args.browser_action == "cleanup":
        manager.cleanup(args.session_id, args.reason)
        print(json.dumps({"ok": True, "session_id": args.session_id, "status": "cleaned"}))
        return 0
    if args.browser_action == "show":
        print(json.dumps(asdict(manager.get(args.session_id)), ensure_ascii=False, indent=2))
        return 0
    raise SystemExit("unknown browser action")


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
    if args.action == "identity":
        return cmd_identity(args)
    if args.action == "browser":
        return cmd_browser(args)
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
