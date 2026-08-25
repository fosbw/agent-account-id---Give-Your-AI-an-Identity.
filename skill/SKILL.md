---
name: agent-account-google-id
version: 0.2.0
description: Give a user-owned AI agent a bounded session, a non-secret operator-authorized identity reference, an ephemeral browser profile, local event visibility, policy checks, pause/resume, and an emergency stop. Use for explicitly supervised agent work.
---

# Agent Account Google ID — Give Your AI an Identity

Use this skill as a **local control plane** around the current user-owned agent. The agent, model access, API keys, workspace, and execution environment belong to the user. The identity reference must be provisioned and authorized outside this skill.

## Required behavior

Before starting, confirm the requested duration, workspace, identity reference, and explicit browser domain allowlist. Use a short duration when the user did not specify one. Never request, print, store, or transmit passwords, cookies, refresh tokens, API keys, recovery codes, or private keys.

Start a supervised agent run with:

```bash
python -m agentguard run --ttl <seconds> --workspace <path> -- <agent-command> <args>
```

Use `--allow-network` only when the user explicitly requests network-capable work. This flag enables local command guardrails; it is not a real egress firewall.

## Observe and control

The command prints `AGENTGUARD_SESSION_ID`. Use it to inspect and control the session:

```bash
python -m agentguard watch <session-id> --follow
python -m agentguard list
python -m agentguard pause <session-id>
python -m agentguard resume <session-id>
python -m agentguard stop <session-id> --reason user_requested
```

When showing output, prefer the redacted event stream. Explain that the observer is local and read-only; control actions are separate explicit commands.

## Identity reference

If the user has an operator-authorized provider identity, attach metadata only:

```bash
python -m agentguard identity attach \
  --provider google \
  --subject <provider-subject-id> \
  --authorization-basis test_account
```

Store and pass only the generated `identity_id`. Do not ask for or accept the account password, cookies, OAuth tokens, recovery codes, or private keys. This command does not create an account or prove that a login succeeded.

## Automatic agent + browser context

When the user has already configured a non-secret identity reference and approved domains, use one supervised run so the user only specifies the task and duration:

```bash
python -m agentguard run \
  --ttl <seconds> \
  --identity-id <identity-id> \
  --allow-domain <approved-domain> \
  --browser-start-url https://approved-domain.example/ \
  --workspace <path> \
  -- <agent-command> <args>
```

The command creates the temporary browser context before the Agent starts, passes only `AGENTGUARD_*` session metadata to the Agent, and cleans up when the Agent exits or the TTL expires. Do not put credentials in any argument or environment variable.

## Browser session

Create a short-lived isolated profile with explicit domains:

```bash
python -m agentguard browser create \
  --ttl <seconds> \
  --allow-domain <approved-domain> \
  --identity-provider google \
  --identity-id <identity-id>
```

Before any navigation, check the URL:

```bash
python -m agentguard browser check-url <browser-session-id> https://approved-domain.example/path
```

Use the normal provider UI for login, MFA, or CAPTCHA. Record a handoff only when the authorized operator has performed it manually:

```bash
python -m agentguard browser login-handoff <browser-session-id> approved-domain.example
python -m agentguard browser login-complete <browser-session-id> approved-domain.example
```

The completion event is an operator signal and is marked unverified. Never automate account creation, CAPTCHA/MFA bypass, password entry, cookie import, recovery changes, Gmail/Drive/payment access, or arbitrary-site login. The automatic run path removes repeated user steps, but it does not create an identity or manufacture provider authorization.

Launch and clean up a local Chromium-compatible browser only in an environment owned by the user:

```bash
python -m agentguard browser launch <browser-session-id> --url https://approved-domain.example/
python -m agentguard browser cleanup <browser-session-id>
```

The launcher uses an ephemeral profile and waits for TTL by default. `--detach` requires an external supervisor to perform cleanup.

## Claude Code and Codex

For Claude Code, configure the user's own hooks to call:

```bash
python adapters/claude_hook.py --event PreToolUse
```

For Codex, run:

```bash
python adapters/codex_run.py --ttl <seconds> --workspace <path> -- codex
```

Do not alter provider authentication or account settings. See `docs/INTEGRATION.md` and `SUPPORTED_AGENTS.md` for the adapter boundary.

## Safety boundary

Command matching and browser URL decisions are guardrails, not complete sandbox or network isolation. For untrusted work, use a user-controlled container or VM with an OS-level egress firewall. A remote live video viewer is not included; the current event observer is local, redacted, append-only, and text-based.
