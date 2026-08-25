---
name: agentguard
version: 0.1.0
description: Supervise the current user-owned coding agent with a wall-clock timer, local event stream, policy guardrails, redaction, pause/resume, and emergency stop. Use when the user asks to run an agent under a time limit, watch its actions, constrain its workspace, or stop it safely.
---

# AgentGuard

Use AgentGuard as a **local supervisor** around the current user-owned agent. The agent, model, account, API keys, workspace, and tokens belong to the user and are not supplied by this skill.

## Required behavior

Before starting a supervised run, confirm the requested duration and workspace. Default to the current repository and a short duration if the user did not specify either. Never request, print, store, or transmit passwords, cookies, refresh tokens, API keys, or Google account data.

Start a run with:

```bash
python -m agentguard run --ttl <seconds> --workspace <path> -- <agent-command> <args>
```

Use `--allow-network` only when the user explicitly requests network-capable work. This flag enables the local command guardrails for network commands; it is not a replacement for an OS-level sandbox or a real egress firewall.

## Observe and control

The command prints a `AGENTGUARD_SESSION_ID`. Use it to inspect and control the session:

```bash
python -m agentguard watch <session-id> --follow
python -m agentguard list
python -m agentguard pause <session-id>
python -m agentguard resume <session-id>
python -m agentguard stop <session-id> --reason user_requested
```

When showing output to a user, prefer the redacted event stream. Explain that the observer is local and read-only; control actions are separate explicit commands.

## Claude Code hooks

For a Claude Code hook, invoke the repository adapter with the current `AGENTGUARD_SESSION_ID`:

```bash
python adapters/claude_hook.py --event PreToolUse
```

The adapter reads the hook JSON from stdin, emits a redacted event, and can return a deny decision for blocked payloads. Keep hook configuration in the user's own Claude Code settings. Do not add account, browser, identity, cookie, or login hooks.

## Codex

Run Codex through the thin adapter:

```bash
python adapters/codex_run.py --ttl <seconds> --workspace <path> -- codex
```

The adapter does not authenticate Codex or create an account. It only supervises the locally installed command.

## Safety boundaries

Treat command matching as a convenience guardrail, not a complete security boundary. For strong isolation, run the agent inside a container or VM owned by the user. Never promise that AgentGuard can prevent every shell bypass. The process supervisor uses a dedicated process group and attempts to terminate descendants on stop or expiry.

The Google identity, browser, account, credential, and login portion is intentionally absent from this package. Do not invent an implementation for it. The user adds that part separately if they have an authorized design.
