# Agent Account Google ID build report

## Implemented

The repository now contains a dependency-free Python 3.10+ local control plane around a user-owned AI agent. The original supervisor provides a TTL timer, dedicated POSIX process group, best-effort group termination, POSIX pause/resume, a redacted JSONL event log, local `watch`, workspace/sensitive-path checks, command guardrails, and Claude Code/Codex adapters.

The new identity-session safety layer adds an `IdentityRef`/`IdentityStore` model that stores non-secret provider metadata only. The Google adapter accepts a provider subject and safe verification metadata; it does not create accounts, store tokens, import cookies, or handle passwords.

The new browser layer adds an ephemeral profile manifest, explicit HTTPS domain allowlist, blocking for embedded URL credentials, localhost/private/link-local/metadata/reserved targets, sensitive Google services, and recovery/password/challenge paths. It supports local URL decisions, Chromium-compatible launch, TTL waiting, process cleanup, profile deletion, and a retained non-secret audit trail. The `run` command can now create this context before the Agent starts, validate the attached identity reference, pass only `AGENTGUARD_*` metadata to the child, and clean the browser context when the Agent exits or TTL expires.

The README, Skill, integration guide, supported-agent matrix, and threat model now describe the product as **Agent Account Google ID — Give Your AI an Identity** while preserving the accurate `agentguard` command name and clear security boundaries.

## Verification performed

| Check | Result |
|---|---|
| Unit tests | 13 passed |
| Python compilation | Passed for `agentguard` and `adapters` |
| Existing supervisor TTL/redaction/hook/Codex tests | Passed |
| Browser URL policy tests | Passed: HTTPS, allowlist, credentials-in-URL, private/local/metadata, sensitive Google targets |
| Browser session lifecycle tests | Passed: isolated profile, manual handoff signal, cleanup, TTL expiry |
| Identity metadata tests | Passed: Google reference, secret-field rejection, revoke |
| Automatic Agent context smoke | Passed: identity validation, non-secret environment handoff, automatic profile cleanup |
| `git diff --check` | Passed |
| External design review attempt | ChatGPT returned `429 insufficient_quota`; Gemini returned `503 model unavailable` on this run. No secrets were sent. |

## Deliberately excluded

The repository does not create or distribute Google accounts, operate a shared consumer-account pool, import cookies, retrieve passwords or recovery codes, bypass MFA/CAPTCHA, automate arbitrary-site login, access Gmail/Drive/payments/admin/recovery settings, provide a hosted remote browser, or claim that a manual login signal is verified. The provider identity must be owned/authorized outside this package.

## Known limitations

Command matching is a guardrail, not a complete sandbox. Browser URL decisions are a policy layer, not a browser extension, proxy, or OS egress firewall. A shell script, interpreter, encoding, alias, detached process, or privileged process can bypass Python-level checks. Strong isolation requires a user-owned container or VM plus OS-level egress controls.

The viewer remains local text/JSONL and is not a remote video stream. Browser launch depends on a Chromium-compatible executable in the user's environment. The `browser login-complete` command is an operator assertion with `verified: false`; it does not inspect browser state or contact a provider.

## Deployment note

The current branch is feature work based on `origin/main`. It must be reviewed and explicitly approved before merging into `main`.
