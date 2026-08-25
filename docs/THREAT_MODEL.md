# Threat model

## Scope

Agent Account Google ID supervises a user-owned AI agent and can create a temporary local browser profile linked to a non-secret identity reference. The repository is not a hosted browser, identity provider, credential broker, or account-sharing service.

## Assets

The main assets are the user's workspace, model/API credentials already present in the agent environment, provider identity sessions, browser profile data, event logs, and the ability to stop the agent before a deadline.

## Trust boundaries

| Boundary | Assumption | Control |
|---|---|---|
| User and agent | The user intentionally supplies the agent and environment. | Explicit command invocation, TTL, workspace policy, hook deny decisions. |
| Agent and supervisor | Agent output and metadata may be malicious or malformed. | Process group, redaction, bounded metadata, fail-closed URL decisions. |
| Browser and provider | Provider login remains provider-controlled. | Manual handoff, no password/cookie/token APIs, explicit domain allowlist. |
| Policy and network | Local checks are not a firewall. | Document container/VM and OS-level egress enforcement for untrusted work. |
| Logs and observers | Logs can contain sensitive text before redaction bugs are found. | Event-boundary redaction, local-only default, no remote viewer in MVP. |

## Threats and mitigations

| Threat | Mitigation | Residual risk |
|---|---|---|
| Agent reads secrets from the environment | Redaction protects persistence; documentation recommends a minimal environment. | The child can still see inherited environment variables unless the user removes them. |
| Agent writes outside the project | Canonical workspace checks for supported payloads. | Shell scripts and interpreters can bypass payload-level checks. |
| Destructive command | Small deny guardrails, hook decisions, process-group stop, and TTL. | String matching is bypassable; use a VM/container for untrusted agents. |
| Child survives stop | POSIX process group, TERM then KILL, and best-effort descendant cleanup. | Privileged or detached processes may survive. |
| Log leaks a token | Redactor runs before JSONL write and display; identity schemas reject credential fields. | Unknown secret formats may not match; never put secrets in arguments. |
| Browser reaches internal infrastructure | URL policy rejects localhost, private, link-local, metadata, reserved, multicast, and embedded-credential URLs. | The policy does not enforce browser egress; use a firewall or proxy. |
| Agent accesses sensitive Google services | Gmail, Drive, payments, admin, recovery, password, and challenge targets are blocked. | New provider endpoints may require policy updates; keep allowlists narrow. |
| Shared identity or account takeover | No account creation, account pool, cookie import, password handling, or recovery automation. | A user can still misconfigure deployment outside this repository. |
| Browser persists after TTL | Tracked PID/PGID, explicit cleanup, profile deletion, and default wait-until-expiry launch. | Privileged or detached descendants may survive; verify at OS level. |
| False claim that login was verified | Manual signal is marked `verified: false`; no login proof is emitted. | Provider-specific verification remains future work. |
| Remote observer leaks sessions | MVP is local JSONL only. | A future remote viewer needs separate auth, authorization, retention, redaction, and consent. |

## Security invariants

- Never print raw credentials intentionally.
- Never accept or persist passwords, cookies, refresh tokens, recovery codes, private keys, or arbitrary browser state.
- Never send logs or session data to a remote service in the MVP.
- Never implement automated account creation, CAPTCHA/MFA bypass, cookie import, or a shared consumer-account pool.
- Never kill the supervisor's own process group.
- Never claim that command matching or browser URL checks are a complete security boundary.
- Never mark a manual login signal as cryptographic proof; it remains `verified: false`.

## Security testing

Tests cover HTTPS and allowlist enforcement, embedded credentials, private/link-local/metadata targets, sensitive Google services and paths, identity secret rejection, profile deletion, TTL expiry, event retention, and session-ID traversal rejection. These tests do not certify a full sandbox, browser isolation, provider compliance, or protection against a privileged process.

## Future review gate

A provider-specific identity or remote-browser implementation must document ownership, provider authorization, scopes, revocation, retention, user consent, operator authentication, egress enforcement, and emergency-stop behavior before it is added.
