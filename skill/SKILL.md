---
name: agent-account-google-id
version: 0.2.0
description: Give a user-owned AI agent a controlled identity session, browser profile, time limit, live events, policy checks, pause/resume, and emergency stop. Use when the user wants the Agent Account Google ID tool to run a task.
---

# Agent Account Google ID — Give Your AI an Identity

بص، استخدم الـ Skill دي لما المستخدم عايز يدي الـ Agent هوية وجلسة ووقت محدد. الـ Agent والنموذج والـ API Key والـ Workspace والبيئة بتوع المستخدم. المستخدم يقول المهمة والمدة، والـ Agent يستدعي **Agent Account Google ID — Give Your AI an Identity**.

القائمة العملية للمواقع والـ Agents والمتطلبات موجودة في `SUPPORTED_SITES.md`. قبل تشغيل موقع، لازم يكون عنده OAuth/OIDC/SSO أو API رسمي وموجود في الـ allowlist.

## Required behavior

Before starting, confirm the requested duration, workspace, identity reference, and explicit browser domain allowlist. Use a short duration when the user did not specify one. Never request, print, store, or transmit passwords, cookies, refresh tokens, API keys, recovery codes, or private keys.

Start a supervised agent run with:

```bash
agent-account-google-id run --ttl <seconds> --workspace <path> -- <agent-command> <args>
```

Use `--allow-network` only when the user explicitly requests network-capable work. This flag enables local command guardrails; it is not a real egress firewall.

## Observe and control

The command prints `AGENTGUARD_SESSION_ID`. Use it to inspect and control the session:

```bash
agent-account-google-id watch <session-id> --follow
agent-account-google-id list
agent-account-google-id pause <session-id>
agent-account-google-id resume <session-id>
agent-account-google-id stop <session-id> --reason user_requested
```

When showing output, prefer the redacted event stream. Explain that the observer is local and read-only; control actions are separate explicit commands.

## Identity reference

If the user has an operator-authorized provider identity, attach metadata only:

```bash
agent-account-google-id identity attach \
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

The command creates the temporary browser context before the Agent starts, records the browser session in the Agent session metadata, passes only `AGENTGUARD_*` session metadata to the Agent, and cleans up when the Agent exits or the TTL expires. Use `agent-account-google-id browser watch <browser-session-id> --follow` for the local browser event stream. Do not put credentials in any argument or environment variable.

## Browser session

Create a short-lived isolated profile with explicit domains:

```bash
agent-account-google-id browser create \
  --ttl <seconds> \
  --allow-domain <approved-domain> \
  --identity-provider google \
  --identity-id <identity-id>
```

Before any navigation, check the URL:

```bash
agent-account-google-id browser check-url <browser-session-id> https://approved-domain.example/path
```

Use the normal provider UI for login, MFA, or CAPTCHA. Record a handoff only when the authorized operator has performed it manually:

```bash
agent-account-google-id browser login-handoff <browser-session-id> approved-domain.example
agent-account-google-id browser login-complete <browser-session-id> approved-domain.example
```

The completion event is an operator signal and is marked unverified. لا تجعل الـ Agent ينشئ حسابات أو يتجاوز CAPTCHA/MFA أو يطلب Password أو يستورد Cookie أو يغير Recovery أو يدخل Gmail/Drive/Payment أو يدخل أي موقع من غير allowlist وتفويض رسمي. The automatic run path removes repeated user steps, but it does not create an identity or manufacture provider authorization.

Launch and clean up a local Chromium-compatible browser only in an environment owned by the user:

```bash
agent-account-google-id browser launch <browser-session-id> --url https://approved-domain.example/
agent-account-google-id browser cleanup <browser-session-id>
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
