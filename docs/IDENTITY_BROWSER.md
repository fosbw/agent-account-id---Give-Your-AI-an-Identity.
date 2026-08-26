# Agent Account Google ID — Identity and Browser Runtime

## Purpose

The identity and browser layers give an existing Agent an independent Account record, identity reference, browser profile, persistent session, task timer, Live State, and controls. The user brings the Agent, model access, Agent Key, workspace, and runtime. The Tool adds the operating layer around that Agent.

The Account Runtime does not silently turn the user's personal account into an Agent Account. Providers declare which account, identity, browser, login, verification, recovery, rotation, and revocation operations they officially expose. Unsupported operations are reported as unavailable.

## Account Runtime data model

`AgentAccount` contains a generated account ID, opaque account handle, Agent ID, provider name, display name, lifecycle state, timestamps, identity reference, verification state, session state, and browser-profile reference. It does not contain passwords, cookies, OAuth tokens, recovery codes, or private keys.

`ProviderCapabilities` records whether a provider supports account creation, identity initialization, credential initialization, browser sessions, persistent sessions, verification, recovery, rotation, and revocation. `GoogleProvider` reports third-party account provisioning as unavailable when the provider does not expose that operation.

`AccountVault` stores opaque references and flat safe metadata only. It rejects credential-like fields, including `password`, `cookie`, `access_token`, `refresh_token`, `secret`, `recovery_code`, and `private_key`.

## Account lifecycle

The runtime models the following lifecycle:

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

Task expiry ends the current Agent task and browser session. It does not delete the persistent Agent Account record or persistent profile. Revocation and account destruction are separate explicit operations.

## Browser session data model

`BrowserSessionManifest` contains the session ID, provider, identity reference, Account ID, persistence flag, allowlisted domains, profile path, TTL timestamps, browser PID/PGID, login state, verification state, current URL, current page label, current action, and lifecycle state.

The manifest never contains browser cookies, passwords, access tokens, refresh tokens, recovery codes, private keys, or raw page contents.

## Automatic Agent context

When an Account or identity reference and an approved domain allowlist are present, `agent-account-google-id run` can create the browser context before starting the Agent. It records the Account and browser session in the Agent metadata and passes only non-secret `AGENTGUARD_*` identifiers, the profile path, and the approved domain list to the child process.

The Agent never receives raw credentials from this package. Provider-managed secret material must remain in an external provider-approved boundary.

## Persistent browser profile

A persistent profile is owned by an Agent Account, not by the user's personal browser. Profiles must not be shared between Agents or concurrent tasks.

Example:

```bash
agent-account-google-id browser create \
  --ttl 3600 \
  --account-id <account-id> \
  --persistent-profile \
  --identity-provider google \
  --identity-id <identity-id> \
  --allow-domain approved.example
```

At task expiry, the runtime stops the active browser and temporary task context. The persistent profile remains for a later task unless the Account is explicitly revoked or destroyed.

## Browser policy

A URL is allowed only when it uses HTTPS, contains no embedded credentials, resolves to a public hostname, and matches an explicit exact-or-subdomain allowlist. Localhost, private/link-local/reserved/multicast/metadata targets, sensitive Google services, recovery paths, password paths, payment paths, and account-administration paths are blocked by default.

The policy is a guardrail, not an operating-system sandbox or egress firewall. Strong isolation requires a user-controlled container or VM with OS-level network controls.

## Login and verification state

The browser runtime records explicit state without inventing provider requirements:

```text
login_state:
  not_started
  login_required
  active
  reauthentication_required
  blocked

verification_state:
  not_detected
  email_required
  phone_required
  otp_required
  mfa_required
  captcha_detected
  provider_blocked
  completed
```

A verification state is recorded only when the provider or website actually shows it. The runtime does not bypass CAPTCHA, MFA, anti-bot controls, rate limits, or provider restrictions.

## Live Browser State

The local Live View can expose safe state such as:

```text
Agent: ResearchAgent
Status: ACTIVE
Account: opaque handle only
Browser: running
Current URL: https://approved.example/task
Current Page: Task page
Current Action: Reading
Timer: 18:42
Verification: not_detected
```

The `browser state` command updates the current URL, short page label, and current action after policy validation:

```bash
agent-account-google-id browser state <browser-session-id> \
  --url https://approved.example/task \
  --page "Task page" \
  --action "Reading"
```

The Live View never shows passwords, cookies, access tokens, refresh tokens, recovery material, private keys, or raw page secrets.

## Controls

The user can observe and control the run:

```bash
agent-account-google-id watch <session-id> --follow
agent-account-google-id browser watch <browser-session-id> --follow
agent-account-google-id pause <session-id>
agent-account-google-id resume <session-id>
agent-account-google-id stop <session-id> --reason user_requested
agent-account-google-id browser cleanup <browser-session-id>
```

The Kill path is outside the Agent. It stops the Agent process group, tracked browser process, active actions, and new actions. It records the reason. Account revocation is separate from task cleanup.

## Lifecycle events

| Event | Meaning |
|---|---|
| `account.requested` | The Agent requested an Account or account session. |
| `account.capabilities_discovered` | The provider declared available operations. |
| `account.provisioning_started` | Account provisioning started where supported. |
| `account.provisioning_unavailable` | The provider does not expose the requested operation. |
| `identity.attached` | An identity reference was attached. |
| `browser.session_created` | A browser manifest and profile were created. |
| `browser.navigation.allowed` | A URL passed the local policy. |
| `browser.navigation.blocked` | A URL was rejected by policy. |
| `browser.launch_requested` | A Chromium-compatible process was started. |
| `browser.state_updated` | Safe current browser state changed. |
| `browser.verification_state` | A real provider verification state was recorded. |
| `browser.session_cleanup` | The active browser session was stopped and temporary data was cleaned. |
| `account.revoked` | Account revocation was requested. |

All events pass through the redactor. The local event stream is append-only and is not a remote video stream.
