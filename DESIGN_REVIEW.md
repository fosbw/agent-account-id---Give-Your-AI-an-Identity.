# Design review and decisions

## Product direction

The repository name remains **Agent Account Google ID — Give Your AI an Identity**. The product wraps a user-owned agent such as Claude Code or Codex and adds a bounded execution session, local observation, emergency controls, policy guardrails, an operator-authorized identity reference, and an ephemeral browser-profile lifecycle.

## Review result

A new review prompt covered the expanded browser/identity scope, provider authorization, per-session isolation, explicit URL allowlists, manual MFA/CAPTCHA handoff, lifecycle cleanup, Claude/Codex/MCP adapters, and the prohibition on credential theft or shared-account behavior.

The ChatGPT-compatible endpoint was attempted and returned `429 insufficient_quota`. Gemini was attempted with a fallback model and returned `503 model unavailable`. The prompt contained no credentials or user secrets. The implementation therefore follows the previously recorded architecture review and the repository threat model rather than claiming a successful fresh model review.

## Decisions

| Decision | Rationale |
|---|---|
| Keep a process supervisor and event bus rather than build a custom operating system sandbox. | A supervisor can provide TTL, stop, pause, and audit behavior while a container/VM supplies stronger isolation when required. |
| Use process groups for lifecycle control. | Stops are more reliable than targeting only the agent's PID, while still remaining best effort. |
| Keep identity data metadata-only. | Passwords, cookies, tokens, recovery codes, and private keys must not enter the package or its logs. |
| Require explicit HTTPS browser allowlists. | Default-deny navigation reduces accidental exposure and makes consent reviewable. |
| Block sensitive Google services and account-recovery paths. | The browser identity is not a general account-administration channel. |
| Keep provider login inside a scoped adapter. | Approved adapters may authenticate automatically through the internal Vault boundary; MFA, CAPTCHA, OTP, and anti-bot challenges remain provider states and are never bypassed. |
| Mark provider verification explicitly. | The runtime records completed, provider-blocked, MFA, OTP, CAPTCHA, email, or phone states without inventing verification or implying stronger proof. |
| Keep the viewer local and text-based. | Remote live video introduces authentication, retention, privacy, and deployment risks not solved by this CLI. |
| Treat URL/command checks as guardrails. | Subprocesses and browsers can bypass Python checks; stronger environments need an OS firewall and VM/container. |
| Make the normal run path automatic. | `agentguard run` can create a validated browser context before the Agent, pass only `AGENTGUARD_*` session metadata, and clean it after exit/TTL; no repeated user commands are needed for lifecycle control. |
| Add provider-specific integrations only after authorization review. | Google account creation, shared account pools, cookie import, and unrestricted arbitrary-site login are outside the safe MVP; each adapter must declare its supported target and capabilities. |

## Current implementation boundary

The branch implements the identity-session framework, the generic Browser Authentication Runtime, and a narrowly scoped public Demo LoginAdapter. It does not provision a Google account or make arbitrary websites accept an agent identity. Provider login adapters require an authorized target, explicit allowlist, provider capability declaration, and a separate deployment/security review.
