# Claude Code and Codex integration

## Claude Code

Claude Code exposes lifecycle hooks, including pre-tool and post-tool events. The adapter in `adapters/claude_hook.py` accepts the hook JSON from standard input, records a redacted event, checks the supported payload fields against local guardrails, and emits a `PreToolUse` deny response when a rule matches.

A user's Claude Code settings can call it for a supervised session:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Read|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python adapters/claude_hook.py --event PreToolUse"
          }
        ]
      }
    ]
  }
}
```

The hook is intentionally a no-op when `AGENTGUARD_SESSION_ID` is absent. The user must set that variable for the process they intentionally supervise. Use an absolute path or an installed package command when the repository is not the working directory.

## Codex

Codex can be wrapped as a local process:

```bash
python adapters/codex_run.py --ttl 1800 --workspace . -- codex
```

The wrapper does not authenticate Codex, create a user, import cookies, or alter provider settings. It supervises the command the user already installed and authenticated.

## Chat invocation

Copy `skill/SKILL.md` into the user's supported skills directory or plugin mechanism. The skill teaches the agent to ask for a duration and workspace, then invoke `python -m agentguard run ...`. It does not contain provider credentials or identity workflows.

## Viewer model

The MVP viewer is local and text-based:

```bash
python -m agentguard watch <session-id> --follow
```

This avoids turning a local session log into a remote account-sharing service. A remote read-only viewer, if added later, must be designed separately with authentication, authorization, redaction, retention, and explicit user consent.
