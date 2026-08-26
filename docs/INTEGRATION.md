# Agent Account Google ID — Integration Guide

## What the Tool adds

The user already owns the Agent. The user provides the Agent, model access, Agent Key, workspace, and runtime. This Tool adds the Account Runtime, identity reference, browser profile, persistent session, capabilities, TTL, Live State, Pause/Resume, Stop, Kill, policy checks, audit events, and cleanup.

The normal user request is one chat instruction:

```text
Open the approved service, use the Agent Account, and work for one hour.
```

The Agent calls the Tool. The user does not need to control every browser click.

## Install and product command

```bash
python3 -m pip install -e .
agent-account-google-id --help
```

The `agentguard` command remains only as a compatibility alias for older scripts. The product-facing name is **Agent Account Google ID — Give Your AI an Identity**.

## Claude Code

Claude Code exposes lifecycle hooks, including pre-tool and post-tool events. The adapter in `adapters/claude_hook.py` accepts hook JSON from standard input, records a redacted event, checks supported payload fields against local guardrails, and can emit a `PreToolUse` deny response.

A user's Claude Code settings can call the adapter:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Read|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/adapters/claude_hook.py --event PreToolUse"
          }
        ]
      }
    ]
  }
}
```

The hook is intentionally inactive when `AGENTGUARD_SESSION_ID` is absent. The user must set that variable for the process they intentionally supervise.

## Codex

Codex can be wrapped as a local process:

```bash
python3 adapters/codex_run.py --ttl 3600 --workspace . -- codex
```

The wrapper supervises the Codex process the user already installed. It does not replace the Agent or model.

## Account Runtime

Create a persistent local Agent Account record:

```bash
agent-account-google-id account create \
  --agent-id research-agent \
  --display-name "Research Agent"
```

Inspect, revoke, and discover provider capabilities:

```bash
agent-account-google-id account show <account-id>
agent-account-google-id account revoke <account-id>
agent-account-google-id account capabilities
agent-account-google-id account capabilities --provider google
agent-account-google-id account sites
```

The record contains safe metadata, an opaque account handle, lifecycle state, identity reference, provider state, and browser-profile reference. It does not contain a password, cookie, access token, refresh token, recovery code, or private key.

The Account Runtime models `CREATE`, `PROVISION`, `INITIALIZE`, `LOGIN`, `VERIFICATION`, `SESSION ACTIVE`, `USE`, `PAUSE`, `RESUME`, `EXPIRE`, `REAUTHENTICATE`, `REVOKE`, and local session-data cleanup. Each provider declares which operations it officially exposes.

## Google identity metadata

For an identity that has already been provisioned and authorized through an official Google flow:

```bash
agent-account-google-id google-auth \
  --client-id <installed-app-client-id> \
  --identity-dir ~/.agentguard/identities
```

The flow uses an installed-app OAuth flow with PKCE and identity scopes. It persists only safe subject/email metadata. It does not create a Google account, request Gmail/Drive/admin scopes, persist access or refresh tokens, import browser state, or alter recovery settings.

When Google does not expose a requested account operation, the provider result is:

```text
Provider does not expose this operation.
```

It does not silently fall back to the user's personal account.

## Persistent browser session

Create an isolated browser session attached to an Account record:

```bash
agent-account-google-id browser create \
  --ttl 3600 \
  --account-id <account-id> \
  --persistent-profile \
  --identity-provider google \
  --identity-id <identity-id> \
  --allow-domain approved.example
```

Launch the browser only in an environment owned and configured by the operator:

```bash
agent-account-google-id browser launch <browser-session-id> \
  --url https://approved.example/task
```

The persistent profile belongs to the Agent Account. Task TTL ends the current task and browser process; it does not delete the persistent Account record or profile.

## Browser State and verification

Record safe Browser State for Live View:

```bash
agent-account-google-id browser state <browser-session-id> \
  --url https://approved.example/task \
  --page "Task page" \
  --action "Reading the task"
```

Record a verification state only when the provider actually shows it:

```bash
agent-account-google-id browser verification \
  <browser-session-id> approved.example phone_required
```

Supported states include `email_required`, `phone_required`, `otp_required`, `mfa_required`, `captcha_detected`, `provider_blocked`, and `completed`. The Tool does not invent challenges or bypass CAPTCHA, MFA, anti-bot systems, rate limits, or provider restrictions.

## Automatic Agent run

When the Account and identity references already exist, the Agent can start one supervised run:

```bash
agent-account-google-id run \
  --ttl 3600 \
  --account-id <account-id> \
  --persistent-profile \
  --identity-id <identity-id> \
  --allow-domain approved.example \
  --browser-start-url https://approved.example/task \
  --workspace . \
  -- codex
```

The Agent receives only `AGENTGUARD_*` session identifiers, Account identifiers, the browser profile path, and the approved domain list. It does not receive raw credentials.

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

The Kill path is outside the Agent. It stops the Agent process group, tracked browser process, active actions, and new actions, then records the reason.

## Site and capability integration

Read [`SUPPORTED_SITES.md`](../SUPPORTED_SITES.md) before adding a site. A site adapter must declare its official login path, domains, capabilities, verification behavior, provider requirements, revocation behavior, and retention.

Use explicit capabilities such as:

```text
web.read
web.search
browser.navigate
site.read
site.search
```

Do not grant wildcard capabilities by default. The requested action must pass both the capability check and the browser policy.

## Live viewer model

The current viewer is local and text-based. It can show safe event records, current URL, page label, action, browser status, Agent status, session state, and timer. It does not show passwords, cookies, access tokens, refresh tokens, recovery material, or private keys.

A future remote screenshot or video viewer requires a separate deployment with authentication, authorization, redaction, retention, and explicit operator controls.

## Security boundary

The command and browser policies are guardrails, not a complete OS sandbox or egress firewall. For untrusted Agents, use a user-controlled container or VM with OS-level network policy and an external secret manager.

Raw credentials must never be committed, printed, passed to the Agent, written to logs, or placed in model context. Provider-managed secrets remain outside this local process. If a provider does not expose an operation, the adapter reports it as unavailable instead of asking for the user's personal account.
