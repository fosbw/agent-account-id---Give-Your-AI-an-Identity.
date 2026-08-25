# AgentGuard build report

## Implemented

The repository now contains a dependency-free Python MVP with a local CLI. It can supervise any locally installed agent command, including Claude Code or Codex, with a TTL timer, a dedicated POSIX process group, best-effort group termination, pause/resume on POSIX, a redacted JSONL event log, a local `watch` command, workspace and sensitive-path checks, command guardrails, and a Claude Code hook adapter.

The Codex adapter is a thin process wrapper. It does not authenticate Codex or create a provider account. The bundled `skill/SKILL.md` describes how an agent can invoke AgentGuard from natural-language requests while preserving the user's own account and keys.

## Verification performed

| Check | Result |
|---|---|
| Unit tests | 4 passed |
| Python compilation | Passed |
| TTL smoke run | Passed; process group stopped and `session.expired` recorded |
| Redaction smoke run | Passed; the test key was not persisted in the event log |
| Claude hook smoke run | Passed; blocked command returned `PreToolUse` deny JSON |
| Codex adapter smoke run | Passed with a local Python stand-in command |
| `watch` and `list` smoke run | Passed |
| `git diff --check` | Passed |
| Executable identity/browser scan | Clean; no identity or browser integration in `agentguard/` or `adapters/` |

## Deliberately excluded

The Google identity, Google account, browser profile, cookies, refresh tokens, login automation, credential broker, shared-account flow, and provider-account implementation are absent. No placeholder adapter was added. The user requested to add that portion personally later.

## Known limitations

Command matching is a guardrail, not a complete sandbox. A shell script, interpreter, encoding, alias, or detached privileged process can evade it. Strong isolation requires a user-owned container or VM. The MVP's viewer is local text/JSONL; it does not expose a remote viewer or livestream.

The user must configure Claude Code hooks in their own settings and must run the locally installed Codex command. Provider authentication and provider policy remain outside this repository.
