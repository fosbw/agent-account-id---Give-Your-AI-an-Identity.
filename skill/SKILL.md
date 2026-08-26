---
name: agent-account-google-id
version: 0.3.0
description: Give an existing AI Agent an Account Runtime, isolated browser, persistent session, capabilities, TTL, Live State, Pause/Resume, and Kill controls.
---

# Agent Account Google ID — Give Your AI an Identity

Use this Skill when the user wants an existing Agent to work with an Agent Account, a real browser, a persistent session, and a strict time limit. The user brings the Agent, model access, Agent Key, workspace, and runtime. The Tool adds the identity/account/session layer.

## The normal user experience

The user writes one normal request in the Agent chat:

```text
Open the approved service, use the Agent Account, and work for one hour.
```

The Agent calls this Tool. Do not make the user control every click. Request the task, duration, approved site domains, and capabilities. The Tool creates or reuses the Agent Account record, creates or reuses the Agent browser profile, starts the session, and sends only opaque references to the Agent.

## Required behavior

Before starting, check the task TTL, Agent identity, Account Handle, workspace, site allowlist, and capabilities. Never put a Password, Cookie, access token, refresh token, recovery code, private key, or vault secret into the model context, tool output, event log, Live View, command line, or GitHub.

Do not replace an Agent Account with the user's personal account. If a provider does not expose an operation, report the provider state clearly instead of asking for the user's personal account as a fallback.

## Account Runtime

Create a local Account record when the provider or local runtime supports it:

```bash
agent-account-google-id account create \
  --agent-id research-agent \
  --display-name "Research Agent"
```

Discover provider capabilities:

```bash
agent-account-google-id account capabilities
agent-account-google-id account capabilities --provider google
agent-account-google-id account sites
```

Inspect or revoke a non-secret Account record:

```bash
agent-account-google-id account show <account-id>
agent-account-google-id account revoke <account-id>
```

The model receives an opaque handle such as `agent_account://provider/agent_123`, not raw credentials. Account provisioning, identity initialization, browser initialization, verification, recovery, rotation, revocation, and unsupported-operation reporting are separate lifecycle states.

## Google provider behavior

Use the official Google identity flow only when the operator has a valid Installed-App OAuth Client and a provider-authorized identity:

```bash
agent-account-google-id google-auth \
  --client-id <installed-app-client-id> \
  --identity-dir ~/.agentguard/identities
```

The current Google adapter requests identity scopes and stores safe metadata. It does not create a Google account, request Gmail or Drive access, store tokens, import browser state, or modify recovery settings. When the provider does not expose account provisioning, the correct result is `Provider does not expose this operation`.

## Browser and persistent profile

Create a browser session with an explicit allowlist:

```bash
agent-account-google-id browser create \
  --ttl 3600 \
  --account-id <account-id> \
  --persistent-profile \
  --identity-provider google \
  --identity-id <identity-id> \
  --allow-domain approved.example
```

The persistent profile belongs to the Agent Account, not to the user's personal browser. The task timer ends the current task and browser session. It does not delete the persistent Account record or profile.

Check a URL before navigation:

```bash
agent-account-google-id browser check-url <browser-session-id> https://approved.example/task
```

Launch only in an environment owned and configured by the operator:

```bash
agent-account-google-id browser launch <browser-session-id> \
  --url https://approved.example/task
```

## Live Browser State

Record safe state for Live View:

```bash
agent-account-google-id browser state <browser-session-id> \
  --url https://approved.example/task \
  --page "Task page" \
  --action "Reading the task"
```

The safe state may include the current URL, page label, action, browser status, Agent status, and timer. It must never include credentials or session material.

Record a real verification state only when the provider actually shows it:

```bash
agent-account-google-id browser verification \
  <browser-session-id> approved.example phone_required
```

Do not invent a phone, email, OTP, MFA, or CAPTCHA request. Do not bypass CAPTCHA, MFA, anti-bot systems, rate limits, or provider restrictions. If a genuine challenge blocks progress, report only the real state and request the minimum required human action.

## Run the Agent automatically

When the Account and identity references already exist, the user can provide only the task and duration while the Agent calls the Tool:

```bash
agent-account-google-id run \
  --ttl 3600 \
  --account-id <account-id> \
  --persistent-profile \
  --identity-id <identity-id> \
  --allow-domain approved.example \
  --browser-start-url https://approved.example/task \
  --workspace <path> \
  -- codex
```

The Tool passes only non-secret `AGENTGUARD_*` session metadata to the Agent and cleans temporary task data when the task exits or expires.

## Capabilities

Use explicit capabilities per Agent and site. Do not grant wildcard access:

```text
web.read
web.search
browser.navigate
site.read
site.search
```

The requested action must pass both the capability check and the browser policy. Read [`SUPPORTED_SITES.md`](../SUPPORTED_SITES.md) before adding a site integration.

## Observe and control

```bash
agent-account-google-id watch <session-id> --follow
agent-account-google-id browser watch <browser-session-id> --follow
agent-account-google-id list
agent-account-google-id pause <session-id>
agent-account-google-id resume <session-id>
agent-account-google-id stop <session-id> --reason user_requested
agent-account-google-id browser cleanup <browser-session-id>
```

The Kill path is outside the Agent. It stops the Agent process group, browser process, active actions, and new actions. It records the reason. Persistent Account data is revoked or destroyed only by an explicit Account lifecycle operation.

## Claude Code and Codex

For Claude Code, configure the user's own hook to call:

```bash
python3 adapters/claude_hook.py --event PreToolUse
```

For Codex:

```bash
python3 adapters/codex_run.py \
  --ttl <seconds> \
  --workspace <path> \
  -- codex
```

## Never do

Never ask for or accept the user's personal Gmail, Password, Cookies, Browser Profile, access tokens, recovery codes, or private keys as a replacement for an Agent Account. Never expose raw credentials to the Agent. Never create a fake login result. Never bypass CAPTCHA, MFA, anti-bot controls, rate limits, or provider restrictions. Never claim that a provider-specific website login exists until its official adapter is configured and tested.
