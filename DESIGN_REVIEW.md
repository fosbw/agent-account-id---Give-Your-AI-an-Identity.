# AgentGuard design review

## Review status

Gemini review completed successfully using `gemini-3.6-flash` on 2026-08-25. The ChatGPT review was attempted with the available GPT model, but the configured endpoint returned `insufficient_quota` (HTTP 429); no ChatGPT recommendation was used as evidence.

## Decision

Build a narrow local-first MVP as a **process supervisor + event bus + policy guardrail + live JSONL observer**. Do not build a custom kernel sandbox, credential broker, browser-login layer, or shared Google identity.

## Architecture decisions

1. Spawn the wrapped agent in a dedicated process group. Timer expiry, stop, and cancel target the whole group, then perform best-effort descendant cleanup.
2. Use canonical workspace checks and environment boundaries. Shell command matching is only a guardrail and must never be described as a complete security boundary.
3. Keep event records in JSONL so the stream is append-only, inspectable, and dependency-free. Redact known secret patterns before writing records.
4. Use one supervisor abstraction for Claude Code and Codex. Claude Code can optionally emit hook events; Codex is supervised as a normal local process.
5. Keep the viewer local and text-based in the MVP. `agentguard watch` tails a session event file; no remote viewer or browser-login system is included.
6. Keep provider identity, Google account, browser profile, cookies, refresh tokens, and login automation completely absent from this repository. The user explicitly adds that part separately.
7. Treat command policy, output redaction, and workspace checks as safety guardrails. Users must still run agents in an OS/container sandbox for strong isolation.

## Main risks recorded

- Regex-only Shell blocking can be bypassed by encoded commands or scripts.
- Killing only the parent process can leave child processes running; process-group cleanup is required.
- Raw byte redaction can corrupt UTF-8; redaction is applied to decoded line/chunk boundaries and a conservative carry buffer.
- Claude Code and Codex expose different event surfaces; the MVP uses a shared process wrapper and optional Claude hook ingestion rather than pretending their internals are identical.

## Three-week scope

Week 1: supervisor, TTL, process-group stop, JSONL event bus, redaction, workspace checks.

Week 2: policy engine, `watch`, pause/resume where supported, Claude hook adapter, Codex command wrapper.

Week 3: skill instructions, tests, threat model, examples, packaging documentation, and repository cleanup.
