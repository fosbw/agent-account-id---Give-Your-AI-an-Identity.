# Agent Account Google ID — Give Your AI an Identity

**Agent Account Google ID** is a local-first control plane around a user-owned AI agent such as Claude Code or Codex CLI. The user brings the agent, model access, API keys, workspace, and execution environment. The project adds a bounded session, an isolated browser-profile lifecycle, an operator-authorized identity reference, a redacted live event stream, pause/stop controls, policy checks, and cleanup.

The Python package and command remain named `agentguard` for compatibility with the first MVP. The GitHub repository name is intentionally unchanged.

> Give the agent a clock, a controlled identity reference, a visible trail, and an emergency stop—without becoming a password broker or a shared-account service.

## What is included

| Capability | Current behavior |
|---|---|
| Agent session timer | Ends the supervised agent process group when the TTL expires. |
| Live observer | `agentguard watch` tails a local redacted JSONL stream; it is read-only. |
| Pause, stop, kill | POSIX pause/resume plus process-group stop and best-effort descendant cleanup. |
| Workspace policy | Canonical path checks and sensitive-path guardrails. |
| Command guardrails | Blocks a small set of destructive and network-capable patterns; it is not a sandbox. |
| Secret redaction | Redacts common API keys, bearer tokens, private keys, passwords, and credential-like fields from events. |
| Identity reference | Attaches safe provider/subject metadata only. No password, cookie, OAuth token, recovery code, or private key is accepted or persisted. |
| Browser session | Creates an ephemeral Chromium profile manifest with a TTL and explicit HTTPS domain allowlist. |
| Browser policy | Blocks credentials in URLs, localhost/private/link-local/metadata targets, sensitive Google services, and recovery/password/challenge paths. |
| Login handoff | Records that an authorized operator must complete login manually in the isolated browser window. The completion command is only a manual signal; it does not verify or extract credentials. |
| Browser cleanup | Stops the tracked browser process and deletes the ephemeral profile. The non-secret manifest and event trail remain for audit. |
| Claude Code adapter | Reads hook JSON, records a redacted event, and can return a `PreToolUse` deny decision. |
| Codex adapter | Runs the locally installed Codex CLI under the same supervisor. |
| Chat skill | `skill/SKILL.md` teaches an agent how to invoke the local commands. |

## Quick start: supervise an agent

From the repository root:

```bash
python -m agentguard run --ttl 1800 --workspace . -- codex
```

The command prints a session ID. In another terminal:

```bash
python -m agentguard list
python -m agentguard watch <session-id> --follow
python -m agentguard pause <session-id>
python -m agentguard resume <session-id>
python -m agentguard stop <session-id> --reason user_requested
```

Claude Code hook adapter example:

```bash
AGENTGUARD_SESSION_ID=<session-id> \
  python adapters/claude_hook.py --event PreToolUse
```

Codex wrapper example:

```bash
python adapters/codex_run.py --ttl 1800 --workspace . -- codex
```

## Quick start: attach a safe identity reference

The following command records metadata for an identity that was provisioned and authorized outside this package. It does **not** create a Google account or log in to any website:

```bash
python -m agentguard identity attach \
  --provider google \
  --subject provider-subject-id \
  --email agent@example.com \
  --email-verified \
  --authorization-basis test_account
```

Only the returned non-secret `identity_id` should be used in a browser manifest. Never place a password, cookie, refresh token, access token, recovery code, or private key in a command line or metadata file.

## Quick start: controlled browser session

Create an ephemeral profile with an allowlist:

```bash
python -m agentguard browser create \
  --ttl 1800 \
  --allow-domain example.com \
  --allow-domain login.example.com \
  --identity-provider google \
  --identity-id <identity-id>
```

Check a target before navigation:

```bash
python -m agentguard browser check-url <browser-session-id> https://example.com/task
python -m agentguard browser check-url <browser-session-id> https://mail.google.com/
```

Launch a local Chromium-compatible browser. The default command waits until TTL and then cleans the profile; use `--detach` only when an external supervisor will call cleanup:

```bash
python -m agentguard browser launch <browser-session-id> --url https://example.com/task
```

Login is an explicit operator handoff, not automated credential entry:

```bash
python -m agentguard browser login-handoff <browser-session-id> example.com
# The authorized operator completes the provider's normal login/MFA/CAPTCHA flow.
python -m agentguard browser login-complete <browser-session-id> example.com
```

The browser policy is a decision layer. It is **not** an OS firewall, a Chromium extension, a proxy, or a guarantee that every navigation inside a browser will be intercepted. For untrusted agents, combine it with a container or VM, a real egress firewall, and provider-approved account controls.

## Security boundaries

This project is designed for an identity owned or explicitly authorized by the operator or provider. It does not create, distribute, rent, rotate, or share consumer accounts. It does not import cookies, harvest passwords, bypass MFA or CAPTCHA, alter recovery settings, access Gmail/Drive/payments/admin pages, or provide unrestricted “log in anywhere” automation.

The existing command policy is a **guardrail**, not a complete sandbox. Regex and substring checks can be bypassed by scripts, aliases, encoding, interpreters, or child processes. The browser allowlist is likewise a policy decision point, not a complete network isolation boundary. Strong isolation requires a user-controlled container/VM and an OS-level egress policy.

The current browser login completion event is a user/operator assertion with `verified: false`; it is deliberately not proof of authentication. Any future provider adapter must document authorization, scope, retention, revocation, and acceptable-use requirements before it is enabled.

## Supported agents

The current first-class adapters are Claude Code hooks and the Codex process wrapper. Gemini CLI, GitHub Copilot CLI, MCP-compatible agents, and future browser-capable runtimes are documented as integration targets in [`SUPPORTED_AGENTS.md`](SUPPORTED_AGENTS.md), not as completed integrations.

## Development

The project has no runtime dependencies beyond Python 3.10+.

```bash
python -m pytest -q
python -m compileall -q agentguard adapters
python -m agentguard --help
```

## Layout

```text
agentguard/       Supervisor, browser policy, identity references, events, redaction, and guardrails
adapters/         Claude Code hook and Codex process adapters
skill/            Chat-invocable skill instructions
tests/            Unit tests
docs/             Threat model, browser/identity boundary, and integration notes
DESIGN_REVIEW.md  Architecture review and decisions
```

## Status

This branch implements the **identity-session safety layer** around the AgentGuard foundation. It does not claim to provision a Google account, provide a hosted browser, verify a login, or make arbitrary websites accept an agent identity. Those capabilities depend on provider authorization and an explicit deployment environment that are not present in this repository.
