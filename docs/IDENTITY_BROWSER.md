# Identity and browser session boundary

## Purpose

The identity layer gives an AI agent a **reference** to an operator-authorized identity and a temporary browser profile. It does not make the agent the legal owner of a Google account, create accounts, or prove that a login succeeded. Account ownership, provider approval, normal MFA/CAPTCHA handling, and acceptable-use compliance remain outside the process.

## Data model

`IdentityRef` contains only a generated local ID, provider name, provider subject, optional email metadata, verification metadata supplied by the operator/provider, an authorization basis, and a timestamp. `IdentityStore` writes this metadata to a local JSON file. It rejects credential-like fields such as `password`, `cookie`, `access_token`, `refresh_token`, `secret`, and `private_key`.

`BrowserSessionManifest` contains the session ID, identity reference, allowlisted domains, profile path, TTL timestamps, browser PID/PGID, and lifecycle state. It never contains browser cookies, passwords, tokens, recovery codes, or page contents.

## Browser policy

A URL is allowed only when it uses HTTPS, has no embedded credentials, resolves to a public hostname, and matches an explicit exact-or-subdomain allowlist. Localhost, private/link-local/reserved/multicast/metadata targets, and sensitive Google services are blocked. Gmail, Drive, payments, admin, account-management, recovery, password, and challenge paths are intentionally excluded.

The policy is evaluated by the CLI before a launch or a recorded navigation event. It is not a browser extension or an egress firewall. A determined child process or a browser feature may still reach another endpoint unless the deployment adds OS-level network enforcement.

## Manual login handoff

The safe flow is:

1. The operator creates a session with a short TTL and explicit domains.
2. The operator launches the isolated profile.
3. The tool emits `browser.login_handoff_required` and pauses the workflow conceptually at the consent boundary.
4. The authorized operator completes the provider's own login, MFA, or CAPTCHA UI manually.
5. The operator may record `browser.login_manual_signal`. The event is not cryptographic proof and is marked `verified: false`.
6. The browser and profile are stopped and removed at explicit cleanup or TTL expiry.

The agent is never given a password or recovery code by this package. A provider-specific integration may be added only after a separate authorization and threat-model review.

## Lifecycle events

| Event | Meaning |
|---|---|
| `browser.session_created` | A new ephemeral manifest and profile directory were created. |
| `browser.navigation.allowed` | A URL passed the local policy decision. |
| `browser.navigation.blocked` | A URL was rejected by the local policy. |
| `browser.login_handoff_required` | The operator must use the normal provider UI. |
| `browser.login_manual_signal` | The operator asserted that manual login finished; not verified. |
| `browser.launch_requested` | A Chromium-compatible process was launched with the profile. |
| `browser.session_cleanup` | The browser process was stopped and the profile was deleted. |

All events pass through the existing redactor. The event stream is local and append-only; it is not a remote live video stream. A future remote observer would require authentication, authorization, redaction, retention limits, and explicit consent.
