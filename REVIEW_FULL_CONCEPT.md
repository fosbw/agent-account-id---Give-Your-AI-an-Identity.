# Agent Account Google ID — Give Your AI an Identity

## What this file is

This file describes the full product concept and the expected user experience. It is part of the product documentation and acceptance criteria. It does not contain passwords, cookies, access tokens, recovery codes, or executable third-party account-creation logic.

The product name is:

> **Agent Account Google ID — Give Your AI an Identity**

## The idea in one sentence

This is a Tool/Skill installed beside an Agent the user already owns, such as Claude Code or Codex. It gives the Agent its own identity, Agent Account, browser profile, persistent session, real browser, and controlled Internet access so the Agent can perform real web tasks while the user provides the task and time limit and watches the run.

## The problem

An Agent can reason, write commands, and use tools, but it may stop when a task needs a real identity, a real browser session, or a signed-in external service. This product adds the identity and operating layer around the Agent. It does not replace the Agent, the model, the user's API key, the workspace, or the user's environment.

The user's Agent remains the user's Agent. The product adds the account lifecycle, browser lifecycle, capabilities, timer, Live State, controls, policy checks, audit trail, and cleanup.

## The parties

| Party | Role |
|---|---|
| User | Installs the Tool, provides the task and time limit, watches the run, and can pause, stop, or kill it. |
| Agent | Calls the Tool from chat, requests an Account Session, uses the granted capabilities, and performs the task. |
| Agent Account ID Tool | Manages the Account Runtime, Browser Runtime, TTL, policies, Live State, controls, events, and cleanup. |
| Agent Identity | A separate identity intended for the Agent, not the user's personal browser or personal account. |
| Provider | Declares which account, identity, browser, login, verification, recovery, rotation, and revocation operations it officially exposes. |
| Website | A target service that accepts an officially supported OAuth/OIDC/SSO/API or provider-specific login path. |

## The user experience

### Install

The user installs the Tool/Skill inside Claude Code, Codex, or another Agent that supports Tools, Skills, or MCP. The user does not replace the Agent or the model.

### Ask for a task

The user writes one normal instruction in the Agent chat:

```text
Use Agent Account Google ID for one hour, open the approved service, search for the requested information, and complete the task.
```

The user does not want to write a separate command for every click. The Agent calls the Tool and requests a session with a duration and capability set.

### Start a session

The Tool checks the Agent identity, provider capability record, site allowlist, and requested capabilities. It creates or reuses an Agent Account record, starts or reuses the Agent's browser profile, records the start and expiry time, and starts the Live State and Activity Feed.

### Do the task

The Agent uses a real browser and the real Internet inside the configured environment. The Agent can search, read, navigate, and use an approved service according to the capabilities granted to that Agent and site.

The user watches the session. The user does not need to control every click.

### End the task

When the task TTL expires, the Tool stops the task and the current browser session. The persistent Agent Account record and persistent profile are not deleted merely because the task timer expired. Temporary task data is cleaned according to the lifecycle policy. Explicit account revocation is a separate operation.

## Core Account Runtime

The core architecture is:

```text
Agent Key
    -> Agent Identity
    -> Account Provisioning Layer
    -> Agent-owned Account
    -> Credential Vault
    -> Browser Profile
    -> Persistent Session
    -> Real Browser
    -> Real Internet
    -> Approved Website
```

Account Provisioning is a first-class capability in the architecture. It is not replaced by the user's personal account. Each Provider must declare its real capability state.

```text
AccountProvisioner
    - can_create_account()
    - create_account()
    - initialize_identity()
    - initialize_credentials()
    - initialize_browser_session()
    - verify_state()
    - recover_session()
    - rotate_credentials()
    - revoke_account()
```

A provider can report states such as:

```text
Provider A:
  account_creation = supported
  browser_session = supported

Provider B:
  account_creation = unavailable
  browser_session = supported

Provider C:
  account_creation = requires_human_verification
```

If a provider does not expose an operation, the Tool reports:

```text
Provider does not expose this operation.
```

It does not silently replace an Agent Account with the user's personal account.

## Agent-owned identity

The intended Agent Account is separate from the user's personal account. In a provider environment that officially supports managed Agent users, the account can have an email identity, provider account identifier, browser profile, session state, and provider-managed credential state.

The model receives only an opaque account handle such as:

```text
agent_account://provider/agent_123
```

The model does not receive raw passwords, cookies, access tokens, refresh tokens, private keys, or recovery material. Provider-managed secrets remain in the provider's approved secret boundary and are never copied into the model context.

## Credential Vault boundary

The rule is:

```text
THE MODEL NEVER RECEIVES RAW CREDENTIALS.
```

The intended call path is:

```text
Agent
    -> Account Handle
    -> Credential Manager / Provider Vault
    -> Browser or Provider operation
```

It is not:

```text
Agent
    -> Password
    -> Browser
```

Tool output must be checked before it reaches the model. If a provider or browser operation returns secret material, the runtime must block the raw value and replace it with an opaque reference or a safe status. Redaction after the secret already reached the model is not enough.

## Real browser

The Agent uses a real Chromium-compatible browser and real Internet inside an environment owned and configured by the operator. This is not a fake browser, simulated website, mock Internet, or HTTP-only placeholder.

Every Agent receives a separate profile:

```text
profiles/
    agent_001/
    agent_002/
    agent_003/
```

Agent A must not use Agent B's profile. The Agent must not use the user's personal browser profile.

## Persistent sessions

An Agent Account and its browser profile can persist between tasks when the provider and runtime support it. Finishing one task does not delete the account or persistent profile.

A later task can follow this path:

```text
Agent
    -> Existing Agent Identity
    -> Existing Agent Account
    -> Existing Browser Profile
    -> Existing Session
    -> Continue
```

If the provider says the session is expired or invalid, the Account Runtime enters reauthentication or recovery state. It does not ask for the user's personal account as a silent fallback.

## Real web tasks

The Agent can perform real web tasks according to its capabilities:

```text
Open YouTube and search for the latest Microsoft news.
Open an approved news service and read the latest headlines.
Open an approved site and read the latest articles.
Follow a channel when the site capability allows it.
```

The execution path is:

```text
Agent
    -> Capability Check
    -> Browser Action
    -> Approved Website
    -> Real Result
    -> Agent
```

## Verification states

The Tool must report the real state shown by the provider or website. It must not invent a requirement.

If the website actually shows `Enter phone number`, the Tool can report:

```text
The website requires a phone number to continue creating or verifying the Agent Account.
```

If the website does not show a phone challenge, the Tool must not ask for a phone number. The same rule applies to email verification and OTP.

The Agent Account's provider email is used for Agent Account verification when the provider supports it. The Tool does not silently substitute the user's personal Gmail.

## CAPTCHA, MFA, and anti-bot controls

The Tool does not bypass CAPTCHA, MFA, phone verification, email verification, anti-bot systems, rate limits, or provider restrictions.

When a real challenge appears, the runtime:

1. Detects the actual provider state.
2. Reports only the challenge that is actually present.
3. Requests the minimum required action when a human step is genuinely required.
4. Does not invent requirements.
5. Continues the lifecycle after the provider reports completion.

The normal experience remains autonomous. Human intervention is exceptional and based on the real provider state.

## Agent capabilities

Capabilities are explicit and can be added or removed per Agent and per site:

```text
web.read
web.search
youtube.read
youtube.follow
microsoft.read
browser.navigate
```

The runtime does not grant wildcard capabilities by default. Every action must pass the capability check and the browser policy.

## Timer

The user chooses the task TTL:

```text
TTL = 30 minutes
```

When the task TTL ends:

```text
Agent Task
    -> Browser Session Stop
    -> Process Stop
    -> Temporary Task Cleanup
```

The timer ends the task. It does not delete the persistent Agent Account. Account destruction is a separate explicit lifecycle operation.

## Kill Switch

The user can issue:

```text
KILL AGENT
```

The Tool then stops the Agent, browser session, child processes, active actions, and new action requests, and records the reason. The Kill path is outside the Agent's control.

## Pause and Resume

`PAUSE` stops activity without deleting the Account or session record. `RESUME` continues only if the session is still valid and the provider has not revoked it.

## Live Agent View

Live View is more than a text Activity Feed. It should expose safe Browser State such as:

```text
Agent: ResearchAgent
Status: ACTIVE
Browser: Approved service
Current URL: https://approved.example/
Current Page: Search results
Current Action: Reading an article
Account: Agent Account handle only
Timer: 18:42
```

It can include browser screenshot or snapshot updates, current URL, current page label, current action, session status, Agent status, and timer. It must never expose passwords, cookies, refresh tokens, recovery material, or private keys.

## Activity Feed

The user can see safe events such as:

```text
Agent opened the approved service.
Agent searched for Microsoft news.
Agent opened an article.
Agent read the article.
Agent completed the task.
```

The feed must not show raw credentials or provider session material.

## Product component map

```text
User Chat Command
        |
        v
User-owned Agent: Claude Code / Codex / compatible Agent
        |
        v
Agent Account Google ID Skill / Tool / MCP Contract
        |
        +--> Agent Identity and Account Provisioner
        |
        +--> Credential Vault Boundary
        |
        +--> Session Controller: TTL, Pause, Stop, Kill
        |
        +--> Browser Runtime: real browser + isolated profile
        |
        +--> Website Capability and Login Adapter
        |
        +--> Policy Engine: domains, areas, actions
        |
        +--> Live Observer: URL, page, action, screenshot/state
        |
        +--> Audit and Cleanup: timeline, expiry, revocation
```

## Session lifecycle

```text
CREATE
  -> PROVISION
  -> INITIALIZE
  -> LOGIN / VERIFICATION
  -> SESSION ACTIVE
  -> USE
  -> PAUSE / RESUME
  -> EXPIRE TASK
  -> REAUTHENTICATE
  -> REVOKE
  -> DESTROY LOCAL SESSION DATA
```

Expected session states include `requested`, `identity_attached`, `account_provisioning`, `browser_starting`, `login_in_progress`, `verification_required`, `active`, `paused`, `task_running`, `stop_requested`, `expired`, `reauthentication_required`, `cleaning`, `completed`, and `failed`.

## Expected events

| Event | Meaning |
|---|---|
| `account.requested` | The Agent requested an Agent Account or account session. |
| `account.capabilities_discovered` | The provider declared its available operations. |
| `account.provisioning_started` | Account provisioning started where supported. |
| `account.provisioning_unavailable` | The provider does not expose the requested operation. |
| `identity.attached` | An Agent identity reference was attached. |
| `browser.started` | The isolated browser started. |
| `browser.state_updated` | Safe browser state changed. |
| `login.started` | A provider login path started. |
| `login.completed` | The provider reported a completed login state. |
| `verification.required` | A real provider challenge is present. |
| `task.started` | The requested task started. |
| `task.progress` | Safe task progress was recorded. |
| `task.completed` | The task completed. |
| `session.paused` | The user paused the session. |
| `session.stopped` | The user or policy stopped the session. |
| `session.expired` | The task TTL ended. |
| `session.cleaned` | Temporary session data was cleaned. |
| `account.revoked` | Account or provider revocation was requested. |

## Acceptance criteria

The product concept is aligned when a reviewer can understand that:

1. The product is a Tool/Skill for an existing Agent, not a website or replacement model.
2. The user brings the Agent, model access, Agent Key, workspace, and environment.
3. The Agent receives an independent Agent Account and identity when a provider officially supports it.
4. The Agent uses a real browser and real Internet inside the configured runtime.
5. The user gives the task and duration instead of controlling every click.
6. The Tool provides Live View, Timer, Pause, Resume, Stop, Cancel, Kill, Audit, and Cleanup.
7. Gmail, Drive, recovery, password, payment, and account administration areas are outside the default task capability.
8. Each Agent has an isolated profile and a persistent session when supported.
9. The timer ends the task without automatically deleting the persistent Agent Account.
10. Provider capabilities are discovered and unsupported operations are reported clearly.
11. Real verification states are reported only when the provider actually shows them.
12. Raw credentials never enter the model context, tool output, logs, or Live View.

## Implementation status

The repository implements the control-plane and Account Runtime foundations: non-secret Account records, provider capability discovery, metadata-only vault references, identity references, browser profiles, persistent local profile lifecycle, browser policy, session control, Live State, verification-state recording, Claude/Codex adapters, and tests.

Provider-specific account creation and external website login are implemented only when the provider officially exposes the operation and a dedicated adapter is configured. The Google adapter reports unavailable operations instead of asking for the user's personal account or pretending that a local record is a Google account.
