from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .accounts import AccountVault, GoogleProvider, LocalManagedAccountProvisioner
from .browser import BrowserSessionManager
from .browser_auth import AgentBrowserAutomation, BrowserAuthenticationRuntime, DemoCredentialProvider, DemoLoginAdapter, LoginRequest
from .expandtesting_provider import ExpandTestingProvider
from .automationexercise_provider import AutomationExerciseProvider
from .provisioning import AccountProvisioningRuntime, ProvisioningRequest
from .capabilities import CapabilityRegistry
from .events import EventLog
from .google_oauth import GoogleOAuthClient, GoogleOAuthConfig
from .github_provider import GitHubProviderAdapter, GitHubProviderConfig
from .identity import GoogleIdentityMetadataAdapter, IdentityStore, OperatorAttachedIdentityAdapter
from .runtime import AccountRuntime, AgentIdentity
from .agent_identity import AgentIdentityStore
from .agent_web_identity import AgentWebIdentity
from .web_runtime import UniversalWebRuntime, WebActionRequest
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
    run.add_argument("--account-id", default=None, help="persistent Agent Account record; never a password or token")
    run.add_argument("--persistent-profile", action="store_true", help="reuse the account's persistent browser profile")
    run.add_argument("--identity-dir", type=Path, default=None)
    run.add_argument("--account-dir", type=Path, default=None)
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

    google_auth = sub.add_parser("google-auth", help="obtain user-consented Google identity metadata using PKCE")
    google_auth.add_argument("--client-id", required=True, help="Google installed-app OAuth client ID")
    google_auth.add_argument("--identity-dir", type=Path, default=None)
    google_auth.add_argument("--no-browser", action="store_true", help="print the authorization URL instead of opening it")
    google_auth.add_argument("--timeout", type=int, default=300)

    account = sub.add_parser("account", help="manage non-secret Agent Account records and provider capabilities")
    account_sub = account.add_subparsers(dest="account_action", required=True)
    account_create = account_sub.add_parser("create", help="create a persistent local account record")
    account_create.add_argument("--account-dir", type=Path, default=None)
    account_create.add_argument("--agent-id", required=True)
    account_create.add_argument("--display-name", required=True)
    account_show = account_sub.add_parser("show", help="show safe account metadata")
    account_show.add_argument("--account-dir", type=Path, default=None)
    account_show.add_argument("account_id")
    account_revoke = account_sub.add_parser("revoke", help="revoke a local account record")
    account_revoke.add_argument("--account-dir", type=Path, default=None)
    account_revoke.add_argument("account_id")
    account_caps = account_sub.add_parser("capabilities", help="list provider capabilities")
    account_caps.add_argument("--provider", choices=("google", "github", "local"), default=None)
    account_sites = account_sub.add_parser("sites", help="list supported site capability records")
    account_sites.add_argument("--site-id", default=None)
    account_vault = account_sub.add_parser("vault-reference", help="store a non-secret opaque account handle reference")
    account_vault.add_argument("--account-dir", type=Path, default=None)
    account_vault.add_argument("handle")

    github = sub.add_parser("github", help="run an authorized GitHub Provider action")
    github_sub = github.add_subparsers(dest="github_action", required=True)
    github_caps = github_sub.add_parser("capabilities", help="show GitHub Provider capability matrix")
    github_caps.add_argument("--api-base", default=None)
    github_run = github_sub.add_parser("run", help="run a read-only GitHub Provider action")
    github_run.add_argument("--agent-id", required=True)
    github_run.add_argument("--display-name", required=True)
    github_run.add_argument("--agent-key-stdin", action="store_true", help="read Agent Key from stdin; never pass it as an argument")
    github_run.add_argument("--installation-id", default=None)
    github_run.add_argument("--token-env", default="AGENT_ACCOUNT_GITHUB_INSTALLATION_TOKEN")
    github_run.add_argument("--account-dir", type=Path, default=None)
    github_run.add_argument("--browser-dir", type=Path, default=None)
    github_run.add_argument("--ttl", type=float, required=True)
    github_run.add_argument("--action", choices=("get_authenticated_user", "list_installation_repositories"), default="get_authenticated_user")

    web_identity = sub.add_parser("web-identity", help="use one Agent's safe web identity facade")
    web_identity_sub = web_identity.add_subparsers(dest="web_identity_action", required=True)
    web_identity_show = web_identity_sub.add_parser("show", help="show safe Agent Web Identity metadata")
    web_identity_show.add_argument("--runtime-dir", type=Path, required=True)
    web_identity_show.add_argument("identity_id")
    web_identity_permissions = web_identity_sub.add_parser("permissions", help="set explicit safe web permissions for an Agent identity")
    web_identity_permissions.add_argument("--runtime-dir", type=Path, required=True)
    web_identity_permissions.add_argument("identity_id")
    web_identity_permissions.add_argument("--grant", action="append", required=True, dest="permissions")
    web_identity_exec = web_identity_sub.add_parser("action", help="execute one planner-supplied safe web action")
    web_identity_exec.add_argument("--runtime-dir", type=Path, required=True)
    web_identity_exec.add_argument("--browser-dir", type=Path, default=None)
    web_identity_exec.add_argument("--identity-id", required=True)
    web_identity_exec.add_argument("--account-handle", required=True)
    web_identity_exec.add_argument("--session-id", required=True)
    web_identity_exec.add_argument("--browser-session-name", required=True)
    web_identity_exec.add_argument("--operation", choices=("navigate", "read", "click", "fill", "select", "submit"), required=True)
    web_identity_exec.add_argument("--url", default=None)
    web_identity_exec.add_argument("--selector", default=None)
    web_identity_exec.add_argument("--value", default=None)

    browser = sub.add_parser("browser", help="manage an isolated, operator-authorized browser session")
    browser_sub = browser.add_subparsers(dest="browser_action", required=True)

    create = browser_sub.add_parser("create", help="create an ephemeral browser session manifest")
    create.add_argument("--browser-dir", type=Path, default=None)
    create.add_argument("--ttl", type=float, required=True)
    create.add_argument("--allow-domain", action="append", dest="allowed_domains", required=True)
    create.add_argument("--identity-provider", default="operator-attached")
    create.add_argument("--identity-id", default=None, help="non-secret identity reference created with identity attach")
    create.add_argument("--account-id", default=None, help="persistent Agent Account record")
    create.add_argument("--persistent-profile", action="store_true", help="reuse the account's persistent browser profile")

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

    browser_state = browser_sub.add_parser("state", help="record non-secret current browser state")
    browser_state.add_argument("--browser-dir", type=Path, default=None)
    browser_state.add_argument("session_id")
    browser_state.add_argument("--url", required=True)
    browser_state.add_argument("--page", default=None)
    browser_state.add_argument("--action", dest="browser_action_label", default="observed")

    browser_provision = browser_sub.add_parser("provision", help="create and authenticate a real public test account in an isolated browser")
    browser_provision.add_argument("--runtime-dir", type=Path, default=None)
    browser_provision.add_argument("--browser-dir", type=Path, default=None)
    browser_provision.add_argument("--vault-dir", type=Path, default=None)
    browser_provision.add_argument("--organization-id", required=True)
    browser_provision.add_argument("--agent-id", required=True)
    browser_provision.add_argument("--display-name", required=True)
    browser_provision.add_argument("--stable-agent-id", default=None)
    browser_provision.add_argument("--provider", choices=("expandtesting", "automationexercise"), default="expandtesting")
    browser_provision.add_argument("--ttl", type=float, required=True)
    browser_provision.add_argument("--browser-session-name", required=True)
    browser_provision.add_argument("--agent-key-stdin", action="store_true", help="read Agent Key from stdin; never pass it as an argument")

    browser_auth = browser_sub.add_parser("authenticate", help="authenticate an Agent Account inside an isolated browser session")
    browser_auth.add_argument("--browser-dir", type=Path, default=None)
    browser_auth.add_argument("--vault-dir", type=Path, default=None)
    browser_auth.add_argument("session_id")
    browser_auth.add_argument("--account-handle", required=True)
    browser_auth.add_argument("--target", choices=("the-internet.herokuapp.com",), required=True)
    browser_auth.add_argument("--login-url", default="https://the-internet.herokuapp.com/login")
    browser_auth.add_argument("--browser-session-name", required=True)
    browser_auth.add_argument("--install-demo-credentials", action="store_true", help="install the site's public Demo credentials into the internal test vault")

    browser_verification = browser_sub.add_parser("verification", help="record a real provider verification state")
    browser_verification.add_argument("--browser-dir", type=Path, default=None)
    browser_verification.add_argument("session_id")
    browser_verification.add_argument("domain")
    browser_verification.add_argument("state", choices=("not_detected", "email_required", "phone_required", "otp_required", "mfa_required", "captcha_detected", "provider_blocked", "completed"))

    browser_verification_resume = browser_sub.add_parser("verification-resume", help="request safe resume after user completes provider verification")
    browser_verification_resume.add_argument("--browser-dir", type=Path, default=None)
    browser_verification_resume.add_argument("session_id")
    browser_verification_resume.add_argument("domain")

    browser_watch = browser_sub.add_parser("watch", help="follow local browser events")
    browser_watch.add_argument("--browser-dir", type=Path, default=None)
    browser_watch.add_argument("session_id")
    browser_watch.add_argument("--follow", action="store_true")
    browser_watch.add_argument("--json", action="store_true")
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
    requested_browser = bool(args.identity_id or args.allowed_domains or args.browser_start_url or args.account_id or args.persistent_profile)
    account_manager = None
    account = None
    if requested_browser:
        if not args.allowed_domains:
            raise SystemExit("automatic browser context requires at least one --allow-domain")
        if not args.identity_id and not args.account_id:
            raise SystemExit("automatic browser context requires --identity-id or --account-id")
        if args.identity_id:
            try:
                identity_store_from(args).get(args.identity_id)
            except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
                raise SystemExit(f"identity reference is not attached: {args.identity_id}") from exc
        if args.persistent_profile and not args.account_id:
            raise SystemExit("--persistent-profile requires --account-id")
        if args.account_id:
            account_manager = LocalManagedAccountProvisioner(args.account_dir or Path.home() / ".agentguard" / "accounts")
            account = account_manager.get(args.account_id)
        browser_manager = BrowserSessionManager(args.browser_dir)
        browser_manifest = browser_manager.create(
            args.ttl,
            tuple(args.allowed_domains),
            identity_provider="google",
            identity_id=args.identity_id,
            account_id=args.account_id,
            persistent_profile=args.persistent_profile,
        )
        if account_manager is not None and account is not None:
            account_manager.initialize_browser_session(account, Path(browser_manifest.profile_dir))
    try:
        context = None
        if browser_manifest is not None:
            context = {
                "identity_id": args.identity_id,
                "account_id": args.account_id,
                "browser_session_id": browser_manifest.session_id,
                "browser_profile": browser_manifest.profile_dir,
                "browser_allowed_domains": ",".join(browser_manifest.allowed_domains),
            }
        session_id = supervisor.new_session(command, args.workspace, args.ttl, args.allow_network, context=context)
        print(f"AGENTGUARD_SESSION_ID={session_id}", flush=True)
        extra_env = None
        if browser_manifest is not None and browser_manager is not None:
            extra_env = {
                "AGENTGUARD_IDENTITY_ID": args.identity_id,
                "AGENTGUARD_ACCOUNT_ID": args.account_id or "",
                "AGENTGUARD_ACCOUNT_HANDLE": f"agent_account://local/{args.account_id}" if args.account_id else "",
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


def cmd_google_auth(args) -> int:
    client = GoogleOAuthClient(GoogleOAuthConfig(client_id=args.client_id, timeout_seconds=args.timeout))
    authorization = client.authorize(open_browser=not args.no_browser)
    safe = authorization.safe_metadata()
    identity = GoogleIdentityMetadataAdapter().attach(
        {
            "provider": "google",
            "subject": safe.get("subject"),
            "email": safe.get("email"),
            "email_verified": safe.get("email_verified"),
            "authorization_basis": "provider_authorized",
        }
    )
    store = identity_store_from(args)
    store.save(identity)
    print(json.dumps({"identity": identity.safe_metadata(), "token_persisted": False, "scopes": list(GoogleOAuthConfig(client_id=args.client_id).scopes)}, ensure_ascii=False, indent=2))
    return 0


def account_manager_from(args) -> LocalManagedAccountProvisioner:
    root = getattr(args, "account_dir", None) or Path.home() / ".agentguard" / "accounts"
    return LocalManagedAccountProvisioner(root, AccountVault(root / "vault"))


def cmd_account(args) -> int:
    if args.account_action == "sites":
        registry = CapabilityRegistry()
        rows = registry.list_sites() if not args.site_id else [registry.get_site(args.site_id)]
        print(json.dumps([row.safe_metadata() for row in rows], ensure_ascii=False, indent=2))
        return 0
    if args.account_action == "capabilities":
        providers = [args.provider] if args.provider else ["google", "github", "local"]
        rows = []
        for provider in providers:
            if provider == "google":
                descriptor = GoogleProvider().capabilities()
            elif provider == "github":
                descriptor = GitHubProviderAdapter(GitHubProviderConfig.from_environment()).capabilities()
            else:
                descriptor = LocalManagedAccountProvisioner(Path.home() / ".agentguard" / "accounts").capabilities()
            rows.append(descriptor.safe_metadata())
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    manager = account_manager_from(args)
    if args.account_action == "create":
        account = manager.create_account(args.agent_id, args.display_name)
        print(json.dumps(account.safe_metadata(), ensure_ascii=False, indent=2))
        return 0
    if args.account_action == "show":
        print(json.dumps(manager.get(args.account_id).safe_metadata(), ensure_ascii=False, indent=2))
        return 0
    if args.account_action == "revoke":
        account = manager.revoke_account(manager.get(args.account_id))
        print(json.dumps(account.safe_metadata(), ensure_ascii=False, indent=2))
        return 0
    if args.account_action == "vault-reference":
        reference_id = manager.vault.put_reference(args.handle)
        print(json.dumps({"reference_id": reference_id, "handle": args.handle}, ensure_ascii=False, indent=2))
        return 0
    raise SystemExit("unknown account action")


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


def cmd_github(args) -> int:
    if args.github_action == "capabilities":
        config = GitHubProviderConfig(api_base=args.api_base or "https://api.github.com")
        print(json.dumps({"provider": "github", "config": config.safe_metadata(), "capabilities": GitHubProviderAdapter(config).capabilities().safe_metadata()}, indent=2))
        return 0
    if args.github_action != "run":
        raise SystemExit("unknown github action")
    if not args.agent_key_stdin:
        raise SystemExit("github run requires --agent-key-stdin so the Agent Key is not placed in shell history")
    agent_key = sys.stdin.read().strip()
    if not agent_key:
        raise SystemExit("Agent Key stdin was empty")
    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(f"GitHub token is not configured in {args.token_env}")
    config = GitHubProviderConfig(
        api_base="https://api.github.com",
        installation_id=args.installation_id or os.environ.get("AGENT_ACCOUNT_GITHUB_INSTALLATION_ID"),
        token=token,
    )
    adapter = GitHubProviderAdapter(config)
    runtime = AccountRuntime(
        args.account_dir or Path.home() / ".agent-account-google-id" / "github-runtime",
        adapter=adapter,
        browser=BrowserSessionManager(args.browser_dir),
    )
    path = runtime.start(
        agent_key=agent_key,
        agent_id=args.agent_id,
        display_name=args.display_name,
        ttl=args.ttl,
        allowed_domains=("github.com",),
        action=args.action,
    )
    print(json.dumps(path.safe_metadata(), ensure_ascii=False, indent=2))
    return 0


def cmd_web_identity(args) -> int:
    root = args.runtime_dir.expanduser().resolve()
    identities = AgentIdentityStore(root / "agent-identities")
    aggregate = identities.get(args.identity_id)
    identity = AgentIdentity(
        identity_id=aggregate.identity_id,
        agent_id=aggregate.agent_id,
        provider=aggregate.provider,
        key_fingerprint=aggregate.key_fingerprint,
        created_at=aggregate.created_at,
    )
    if args.web_identity_action in {"show", "permissions"}:
        manager = BrowserSessionManager(root / "browser-sessions")
        facade = AgentWebIdentity.from_runtime(
            identity,
            root,
            manager,
            UniversalWebRuntime(manager, AgentBrowserAutomation("metadata-only")),
        )
        if args.web_identity_action == "permissions":
            print(json.dumps(facade.set_permissions(args.permissions), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(facade.metadata(), ensure_ascii=False, indent=2))
        return 0
    if args.web_identity_action == "action":
        manager = BrowserSessionManager(args.browser_dir or root / "browser-sessions")
        browser = AgentBrowserAutomation(args.browser_session_name)
        try:
            facade = AgentWebIdentity.from_runtime(
                identity,
                root,
                manager,
                UniversalWebRuntime(manager, browser),
            )
            request = WebActionRequest(args.operation, url=args.url, selector=args.selector, value=args.value)
            print(json.dumps(facade.execute(args.account_handle, args.session_id, request), ensure_ascii=False, indent=2))
            return 0
        finally:
            browser.close()
    raise SystemExit("unknown web-identity action")


def cmd_browser_watch(args) -> int:
    manager = browser_from(args)
    manifest = manager.get(args.session_id)
    events_path = manager.root / args.session_id / "events.jsonl"
    redactor = Redactor()
    position = 0
    while True:
        if events_path.exists():
            with events_path.open("r", encoding="utf-8") as fh:
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
                        print(f"[{row.get('kind')}] {json.dumps(payload, ensure_ascii=False)}", flush=True)
        if not args.follow or manifest.status == "cleaned":
            return 0
        try:
            manifest = manager.get(args.session_id)
        except FileNotFoundError:
            return 0
        time.sleep(0.25)


def cmd_browser_provision(args) -> int:
    if not args.agent_key_stdin:
        raise SystemExit("browser provision requires --agent-key-stdin")
    agent_key = sys.stdin.read().strip()
    if not agent_key:
        raise SystemExit("Agent Key stdin was empty")
    runtime_dir = args.runtime_dir or Path.home() / ".agent-account-google-id" / "expandtesting-runtime"
    manager = BrowserSessionManager(args.browser_dir or runtime_dir / "browser-sessions")
    vault = AccountVault(args.vault_dir or runtime_dir / "credential-vault")
    provider = ExpandTestingProvider() if args.provider == "expandtesting" else AutomationExerciseProvider()
    request = ProvisioningRequest(
        organization_id=args.organization_id,
        agent_id=args.agent_id,
        provider=args.provider,
        display_name=args.display_name,
        stable_agent_id=args.stable_agent_id,
    )
    runtime = AccountProvisioningRuntime(runtime_dir, provider, browser=manager, vault=vault)
    path = runtime.provision(
        agent_key,
        request,
        args.ttl,
        args.browser_session_name,
        lambda name: AgentBrowserAutomation(name),
    )
    print(json.dumps(path.safe_metadata(), ensure_ascii=False, indent=2))
    return 0


def cmd_browser_authenticate(args) -> int:
    manager = browser_from(args)
    manifest = manager.get(args.session_id)
    if manifest.account_id is None:
        raise SystemExit("browser authentication requires an Agent Account-bound session")
    vault = AccountVault(args.vault_dir or manager.root / "vault")
    if args.install_demo_credentials:
        DemoCredentialProvider.install(args.account_handle, vault)
    browser = AgentBrowserAutomation(args.browser_session_name)
    request = LoginRequest(
        account_handle=args.account_handle,
        target=args.target,
        login_url=args.login_url,
        session_id=args.session_id,
        profile_dir=Path(manifest.profile_dir),
    )
    try:
        state = BrowserAuthenticationRuntime(manager, vault).login(request, DemoLoginAdapter(), browser)
        print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
        return 0
    finally:
        # Closing the daemon keeps the persistent profile on disk while
        # preventing a stale Chromium profile lock after this CLI invocation.
        browser.close()


def cmd_browser(args) -> int:
    manager = browser_from(args)
    if args.browser_action == "create":
        if args.persistent_profile and not args.account_id:
            raise SystemExit("--persistent-profile requires --account-id")
        manifest = manager.create(
            args.ttl,
            tuple(args.allowed_domains),
            args.identity_provider,
            args.identity_id,
            args.account_id,
            args.persistent_profile,
        )
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
    if args.browser_action == "provision":
        return cmd_browser_provision(args)
    if args.browser_action == "authenticate":
        return cmd_browser_authenticate(args)
    if args.browser_action == "state":
        decision = manager.record_browser_state(args.session_id, args.url, args.page, args.browser_action_label)
        print(json.dumps(asdict(decision), ensure_ascii=False, indent=2))
        return 0 if decision.allowed else 2
    if args.browser_action == "verification":
        manager.record_verification_state(args.session_id, args.state, args.domain)
        print(json.dumps({"ok": True, "event": "browser.verification_state", "domain": args.domain, "state": args.state}, ensure_ascii=False))
        return 0
    if args.browser_action == "verification-resume":
        print(json.dumps(manager.resume_after_verification(args.session_id, args.domain), ensure_ascii=False, indent=2))
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
    if args.action == "account":
        return cmd_account(args)
    if args.action == "github":
        return cmd_github(args)
    if args.action == "web-identity":
        return cmd_web_identity(args)
    if args.action == "google-auth":
        return cmd_google_auth(args)
    if args.action == "browser":
        if args.browser_action == "watch":
            return cmd_browser_watch(args)
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
