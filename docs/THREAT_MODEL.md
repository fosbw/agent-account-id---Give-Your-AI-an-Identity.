# AgentGuard threat model

## Assets

The main assets are the user's source tree, local environment variables, agent output, process state, session logs, and any temporary workspace. AgentGuard must minimize what it stores and redact secrets before persistence.

## Trust boundaries

1. The user starts AgentGuard and chooses the command, workspace, and duration.
2. AgentGuard starts the user-owned agent as a child process.
3. The child process can attempt shell commands, file operations, network calls, and child processes.
4. The local observer reads only AgentGuard's event log; it is not an authentication system or a remote access service.
5. Claude Code hooks can report tool payloads to AgentGuard, but the hook process is not a kernel-level enforcement boundary.

## Threats and mitigations

| Threat | Mitigation | Residual risk |
|---|---|---|
| Agent reads secrets from environment | Redact logs; document that the child still has inherited environment unless the user removes it | User must launch with a minimal environment for strong protection |
| Agent writes outside project | Canonical workspace checks for supported payloads | Shell scripts and interpreters can bypass payload-level checks |
| Destructive command | Small deny guardrails and explicit policy events | String matching is bypassable; use a VM/container for untrusted agents |
| Child survives stop | POSIX process group, TERM then KILL, best-effort descendant cleanup | Privileged/detached processes may survive |
| Log leaks a token | Redactor runs before JSONL write and display | Unknown secret formats may not match |
| Session metadata tampering | Validate session IDs and never kill own process group | Same-user local attacker can modify files |
| Path traversal in session ID | Reject separators and dot names | OS permissions remain important |
| False impression of isolation | README and threat model explicitly call guardrails non-sandbox | Users may still misuse the tool |

## Security invariants

- Never print raw credentials intentionally.
- Never send logs or session data to a remote service in the MVP.
- Never implement login automation, cookie import, Google identity, or shared-account handling in this repository.
- Never kill the supervisor's own process group.
- Never claim that command matching is a complete security boundary.
