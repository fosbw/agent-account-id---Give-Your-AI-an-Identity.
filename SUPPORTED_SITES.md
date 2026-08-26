# Agent Account Google ID — Supported Sites, Agents, and Requirements

## What this tool is for

This is a Tool/Skill for an Agent that the user already owns, such as Claude Code or Codex. The user brings the Agent, model access, API key, workspace, and runtime. **Agent Account Google ID — Give Your AI an Identity** adds the Agent Account record, identity reference, browser profile, persistent session, time limit, live state, controls, policies, and cleanup.

The user can write one normal instruction to the Agent:

```text
Open the approved Microsoft workspace, use the Agent Account, and work for one hour.
```

The Agent calls the tool. The tool checks the Agent identity and capabilities, creates or reuses the Agent Account record, starts the browser session, starts the timer, and exposes only opaque references to the Agent.

## The site list

The current matrix contains **11 named service entries**.
 They are integration targets with explicit provider conditions. A named site is not automatically a working login adapter just because it has a Google sign-in button.

| # | Service | Official path that may be used | Current status |
|---:|---|---|---|
| 1 | Google Workspace / Google Cloud | Google OAuth, Workspace SSO, Service Account, or Workload Identity where supported | Conditional; identity OAuth is present, third-party account provisioning is not claimed. |
| 2 | Microsoft Entra External ID | OIDC or Google federation configured by the tenant | Conditional; it requires tenant configuration and is not a universal Microsoft login. |
| 3 | Notion | Notion OAuth integration or Notion API | Conditional; requires an approved integration and scopes. |
| 4 | Slack | Slack OAuth app or Workspace SSO | Conditional; requires Workspace or app authorization. |
| 5 | GitLab | GitLab OAuth, OIDC, group SSO, or API | Conditional; depends on the instance or group configuration. |
| 6 | Atlassian Cloud | OAuth, SAML/SSO, or an official API | Conditional; depends on organization identity settings. |
| 7 | Linear | Linear OAuth integration or API | Conditional; requires an approved integration. |
| 8 | GitHub | GitHub OAuth App, GitHub App, or Enterprise SSO | **Implemented for authorized API actions** through `GitHubProviderAdapter`; browser login remains provider-specific. |
| 9 | Public login demo (`the-internet.herokuapp.com`) | Site-published demo credentials through the scoped Browser Authentication Runtime | **Implemented as a public test integration only** through `DemoLoginAdapter`; not a production provider or universal login bridge. |
| 10 | Expand Testing practice (`practice.expandtesting.com`) | Real browser signup and login in the public automation-testing environment | **Implemented as the first real browser provisioning test provider** through `ExpandTestingProvider`; creates an external test account, stores credentials behind the internal Vault boundary, verifies `/secure`, and records a process-bound session recovery limitation. |
| 11 | AutomationExercise (`automationexercise.com`) | Real browser signup, login, authenticated home-page read, and same-profile/session recovery | **Implemented as the second real browser provisioning test provider** through `AutomationExerciseProvider`; uses normal multi-field signup controls and proves a new-process authenticated action without credential injection. |

The number of services documented is **11**. The number of production third-party providers with a real implemented adapter in the current repository is **1: GitHub API authentication and read actions**. The repository includes **1 public test-site Browser Authentication adapter** and **2 real public test-site browser provisioning adapters**. GitHub is implemented through its official REST API and caller-owned OAuth/App token boundary; the Demo is intentionally limited to form discovery, login, verification, safe session metadata, and persistent-profile lifecycle testing; Expand Testing and AutomationExercise are intentionally limited to public test-account creation, login, authenticated-page verification, and provider-specific session behavior.

The Universal Web Runtime is a cross-provider mechanics layer, not an additional site count. It supports safe session-bound navigation, page reading, clicking, ordinary field filling, selection, and submission wherever the explicit Browser Session allowlist permits the target. It does not infer provider login selectors, create arbitrary accounts, or turn a Google sign-in button into a universal credential bridge.

The Agent Web Identity facade is the product surface above that mechanics layer. It presents one Agent's safe identity graph, accounts, profiles, sessions, permissions, activity, and memory references to an external planner while enforcing account/session ownership and keeping credentials outside Agent output.

## What counts as a supported login path

A service is eligible for an adapter when it officially exposes OAuth, OpenID Connect, SSO, or an API that the Agent can use. The adapter must declare its scopes, lifecycle, verification behavior, revocation method, retention, and acceptable-use requirements. The core capability contract uses `CREATE_ACCOUNT`, `INITIALIZE_ACCOUNT`, `AUTHENTICATE`, `PERSIST_SESSION`, `REFRESH_SESSION`, `REVOKE_SESSION`, `ROTATE_CREDENTIAL`, and `VERIFY_STATE`; each provider reports its own supported, unavailable, or provider-managed state for every operation.

A site that only opens in Chrome is not automatically supported. A Google sign-in button alone does not create a universal credential or session bridge. If a service requires a provider-specific account, the matching provider adapter must be used.

## Agents

| Agent or environment | Current status | How it connects |
|---|---|---|
| Claude Code | First-class | Claude hook adapter for session events and policy decisions. |
| Codex CLI | First-class | Codex process wrapper under the Supervisor. |
| Gemini CLI | Generic command path | Can run as a local command; specialized adapter is a future integration. |
| GitHub Copilot CLI | Generic command path | Can run as a local command; specialized hooks/MCP adapter is a future integration. |
| MCP-compatible Agent | Integration target | Use an MCP contract for Account Runtime and Browser Runtime operations. |
| Any local Agent command | Supervisor-compatible | Can run under TTL, but identity and browser integration must be explicit. |

## Where it runs

The current implementation is local-first. It runs where the project, the Agent, and the browser are installed.

| Environment | Status |
|---|---|
| Linux | Best-supported path for process groups, pause/resume, Chromium, and the local runtime. |
| macOS | Suitable for the session and browser lifecycle; process details depend on the local environment. |
| WSL | Suitable when Python, the Agent, and Chromium are available in the same environment. |
| Native Windows | Supervisor operation is possible; POSIX pause/resume and process-group behavior differ. |
| Docker or VM | Recommended when stronger OS isolation and network egress controls are needed. |
| CI/CD | Suitable for non-interactive tests; requires an approved external secret manager for any provider integration. |
| Cloud browser | Not hosted by this repository; requires a separate browser runtime with authentication and live-view controls. |
| Phone | No direct phone-to-sandbox browser bridge is included. |

## Requirements

You need Python 3.10 or newer, Git, a supported Agent or local command, a workspace, and a Chromium-compatible browser for browser sessions. You also need an explicit HTTPS domain allowlist and an Agent Account or identity reference for an identity-connected run.

For Google OAuth, you need an Installed-App OAuth Client and a Google identity that is already owned and authorized by the operator or organization. The current flow requests identity scopes only and does not create a Google account or request Gmail, Drive, recovery, payment, or administration access.

For a production external site, you need an official OAuth/OIDC/SSO/API path, a provider-specific adapter, explicit domain approval, known scopes, and revocation behavior. The public Demo integration is a test-only exception with site-published credentials held inside the process-bound Vault. The Expand Testing integration is also test-only: the tool generates a provider-valid username and password, creates the external practice account through Chrome, then authenticates and reads the protected page. Its session cookies are process-bound and are not treated as persistent authentication after a complete process restart. The AutomationExercise integration is test-only: the tool generates a provider-valid signup identity, creates the account through Chrome, logs out, logs in through the generic Browser Authentication Runtime, reads the authenticated home page, and verifies recovery with the same Profile/session state in a new browser process.
 Never put passwords, cookies, access tokens, refresh tokens, recovery codes, or private keys in GitHub, chat, command-line arguments, or Agent output.

## The one-command workflow

```text
User: Open the approved service, use the Agent Account, and work for one hour.

Agent: Calls Agent Account Google ID and requests a session with a one-hour TTL.

Tool: Checks identity and capabilities, creates or reuses the Account record, starts the browser profile, and starts Live Events.

Agent: Performs only the actions granted by the site capability and browser policy.

User: Watches the activity and can Pause, Resume, Stop, Cancel, or Kill the run.

Tool: At expiry, stops the task and temporary session data. The persistent Agent Account record is kept unless explicitly revoked.
```

## GitHub Provider: the first real provider

GitHub is the first real provider adapter in the project. It links an existing authorized GitHub App installation or caller-owned GitHub token, validates the provider session through the official API, and supports safe read actions such as the authenticated identity and installation repositories. It does not create a GitHub account, import a browser cookie, or pretend that an API token is a universal browser login.

Configure the provider outside the repository:

```bash
export AGENT_ACCOUNT_GITHUB_INSTALLATION_ID=12345
export AGENT_ACCOUNT_GITHUB_INSTALLATION_TOKEN='provided-by-your-approved-secret-manager'
printf '%s' 'agent-key-from-agent-runtime' | agent-account-google-id github run \\
  --agent-id github-agent \\
  --display-name "GitHub Agent" \\
  --agent-key-stdin \\
  --ttl 3600 \\
  --action get_authenticated_user
```

The command prints safe Account, Identity, Browser, and Provider Session metadata only. It never prints the GitHub token. The current CLI intentionally supports read-only provider actions; write actions require a separate explicit confirmation path.

## Real browser account provisioning test

```bash
printf '%s' 'agent-key-from-agent-runtime' | agent-account-google-id browser provision \\
  --runtime-dir ./expandtesting-runtime \\
  --organization-id acme-test \\
  --agent-id research-agent \\
  --display-name "Research Agent Test" \\
  --stable-agent-id live-acceptance-unique-id \\
  --ttl 300 \\
  --browser-session-name expandtesting-provision-session \\
  --agent-key-stdin
```

This command creates an external account in the public practice environment through Chrome, stores the generated credential bundle behind the process-bound Vault, logs in with the account created by the command, verifies `/secure`, and returns safe metadata only. Account records and persistent profiles survive cleanup. The provider reports reauthentication required after process restart because its authentication cookie is process-bound.

## Agent Web Identity and Universal Web Runtime

The facade is intentionally planner-compatible: an external Claude Code, Codex, Gemini, or other planner supplies an action request, while this Tool enforces identity ownership, explicit permissions, the browser allowlist, safe output, and activity recording.

```bash
agent-account-google-id web-identity permissions \
  --runtime-dir ./automationexercise-runtime \
  <identity-id> \
  --grant web.navigate \
  --grant web.read \
  --grant web.interact

agent-account-google-id web-identity show \
  --runtime-dir ./automationexercise-runtime \
  <identity-id>

agent-account-google-id web-identity action \
  --runtime-dir ./automationexercise-runtime \
  --identity-id <identity-id> \
  --account-handle agent_account://automationexercise/<account-id> \
  --session-id <browser-session-id> \
  --browser-session-name agent-web-identity-session \
  --operation read
```

The facade returns opaque identity/account/session handles and redacted web results only. It accepts separate `web.navigate`, `web.read`, and `web.interact` permissions. Passwords, cookies, tokens, raw Provider Session data, and screenshot OCR are not facade outputs. Known credential-entry and authentication states block screenshot capture; this conservative policy does not claim perfect pixel-level detection for arbitrary images.

### Chat Verification Handoff

When a real provider challenge is detected, the Agent-facing chat bridge emits a safe `verification_required` event containing only the challenge type and a message telling the user to complete verification in the provider browser. No event is emitted when there is no pending challenge. The user can reply `Done`, which becomes a resume signal; verification codes are never accepted, stored, forwarded, or placed in the chat context, and authentication must be rechecked by the provider adapter.

```bash
agent-account-google-id browser verification-resume \\
  <browser-session-id> example.com
```

## Current CLI examples

```bash
python3 -m pip install -e .
agent-account-google-id account capabilities
agent-account-google-id account sites
agent-account-google-id account create --agent-id research-agent --display-name "Research Agent"
agent-account-google-id browser create --ttl 3600 --allow-domain example.com --persistent-profile --account-id <account-id>
agent-account-google-id browser state <browser-session-id> --url https://example.com/ --page "Home" --action "Reading"
agent-account-google-id browser verification <browser-session-id> example.com phone_required
agent-account-google-id browser verification-resume <browser-session-id> example.com
agent-account-google-id browser authenticate <browser-session-id> \\
  --account-handle agent_account://demo-site/acct-demo \\
  --target the-internet.herokuapp.com \\
  --browser-session-name demo-auth-session \\
  --install-demo-credentials
```

The CLI exposes the lifecycle and control surfaces. It does not claim to provision a third-party consumer account when the provider has not exposed that operation. The `browser provision --provider` selector currently supports only the two named public practice adapters and does not imply universal signup automation.

## Product boundary

The user does not hand over a personal account by default. An Agent Account is separate from the user's personal browser profile. Provider adapters must report unsupported operations instead of silently delegating to the user's personal account.

The runtime protects the model from raw credential material. The Agent receives an opaque handle, while provider-managed secrets remain outside the model context. The tool does not bypass CAPTCHA, MFA, anti-bot systems, rate limits, or provider restrictions.
