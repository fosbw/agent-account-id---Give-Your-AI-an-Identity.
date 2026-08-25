# AgentGuard

**AgentGuard** is a local-first supervisor for user-owned AI coding agents such as Claude Code and Codex. It adds a wall-clock session timer, a redacted local event stream, process-group stop, workspace checks, command guardrails, and cleanup without replacing the user's model, account, API key, or agent.

> Run your agent with a clock, a trail, and an emergency stop.

## What is included

| Capability | MVP behavior |
|---|---|
| Timer | Ends the supervised process group when the TTL expires |
| Live observer | `agentguard watch` tails a local redacted JSONL event stream |
| Kill switch | Stops the process group and attempts descendant cleanup |
| Pause/resume | POSIX `SIGSTOP`/`SIGCONT`; Windows reports that stop is required |
| Workspace policy | Canonical path checks and sensitive-path guardrails |
| Command guardrails | Blocks a small set of destructive/network-capable patterns |
| Secret redaction | Removes common API keys, bearer tokens, private keys, and passwords from logs |
| Claude Code adapter | Reads hook JSON, records an event, and can return a `PreToolUse` deny decision |
| Codex adapter | Runs the locally installed Codex CLI under the same supervisor |
| Chat skill | `skill/SKILL.md` teaches an agent how to invoke the local commands |

## Quick start

From the repository root:

```bash
python -m agentguard run --ttl 1800 --workspace . -- codex
```

The command prints a session ID. In another terminal:

```bash
python -m agentguard list
python -m agentguard watch <session-id> --follow
python -m agentguard stop <session-id> --reason user_requested
```

Claude Code hook adapter example:

```bash
AGENTGUARD_SESSION_ID=<session-id> \
  python adapters/claude_hook.py --event PreToolUse
```

The hook reads JSON from stdin. Add it to the user's own Claude Code settings only for sessions the user intentionally supervises.

Codex wrapper example:

```bash
python adapters/codex_run.py --ttl 1800 --workspace . -- codex
```

Run guardrail checks directly:

```bash
python -m agentguard policy-check --workspace . --command 'rm -rf /'
python -m agentguard policy-check --workspace . --path .env
```

## Important security boundary

The command policy is a **guardrail**, not a complete sandbox. Regex or substring checks can be bypassed by scripts, encoding, aliases, interpreters, or child processes. For untrusted work, run the agent inside a container or VM and use AgentGuard as the timer, observer, and process supervisor around that stronger boundary.

The process supervisor creates a dedicated process group on POSIX and uses best-effort tree termination. No local process supervisor can guarantee cleanup of a malicious privileged process.

## Explicitly excluded

This repository intentionally contains no Google identity, browser profile, cookies, refresh tokens, login automation, shared account, credential broker, or provider-account implementation. The user requested that this portion remain empty and add it separately. Nothing in this MVP creates or manages an identity.

## Development

The project has no runtime dependencies beyond Python 3.10+.

```bash
python -m pytest -q
python -m agentguard --help
```

## Layout

```text
agentguard/       Core supervisor, event log, redaction, and policy layer
adapters/         Claude Code hook and Codex process adapters
skill/            Chat-invocable skill instructions
tests/            Unit tests
docs/             Threat model and implementation notes
DESIGN_REVIEW.md  Architecture review and decisions
```

## Status

This is an MVP foundation. It is intentionally conservative: local event visibility and lifecycle control are implemented first, while provider identity and browser login remain out of scope.
