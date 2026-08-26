# Agent Account Google ID — Supported Sites, Agents, and Requirements

## What this tool is for

This is a Tool/Skill for an Agent that the user already owns, such as Claude Code or Codex. The user brings the Agent, model access, API key, workspace, and runtime. **Agent Account Google ID — Give Your AI an Identity** adds the Agent Account record, identity reference, browser profile, persistent session, time limit, live state, controls, policies, and cleanup.

The user can write one normal instruction to the Agent:

```text
Open the approved Microsoft workspace, use the Agent Account, and work for one hour.
```

The Agent calls the tool. The tool checks the Agent identity and capabilities, creates or reuses the Agent Account record, starts the browser session, starts the timer, and exposes only opaque references to the Agent.

## The site list

The current matrix contains **8 named service entries**. They are integration targets with explicit provider conditions. A named site is not automatically a working login adapter just because it has a Google sign-in button.

| # | Service | Official path that may be used | Current status |
|---:|---|---|---|
| 1 | Google Workspace / Google Cloud | Google OAuth, Workspace SSO, Service Account, or Workload Identity where supported | Conditional; identity OAuth is present, third-party account provisioning is not claimed. |
| 2 | Microsoft Entra External ID | OIDC or Google federation configured by the tenant | Conditional; it requires tenant configuration and is not a universal Microsoft login. |
| 3 | Notion | Notion OAuth integration or Notion API | Conditional; requires an approved integration and scopes. |
| 4 | Slack | Slack OAuth app or Workspace SSO | Conditional; requires Workspace or app authorization. |
| 5 | GitLab | GitLab OAuth, OIDC, group SSO, or API | Conditional; depends on the instance or group configuration. |
| 6 | Atlassian Cloud | OAuth, SAML/SSO, or an official API | Conditional; depends on organization identity settings. |
| 7 | Linear | Linear OAuth integration or API | Conditional; requires an approved integration. |
| 8 | GitHub | GitHub OAuth App, GitHub App, or Enterprise SSO | Conditional; GitHub is not advertised as a universal Google-login target. |

The number of services documented is **8**. The number of third-party websites with a fully automated login adapter in the current repository is **0**. The current repository provides the Account Runtime, browser lifecycle, provider capability model, policy layer, and integration contracts; it does not pretend that a provider-specific website login is already implemented when it is not.

## What counts as a supported login path

A service is eligible for an adapter when it officially exposes OAuth, OpenID Connect, SSO, or an API that the Agent can use. The adapter must declare its scopes, lifecycle, verification behavior, revocation method, retention, and acceptable-use requirements.

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

For an external site, you need an official OAuth/OIDC/SSO/API path, a provider-specific adapter, explicit domain approval, known scopes, and revocation behavior. Never put passwords, cookies, access tokens, refresh tokens, recovery codes, or private keys in GitHub, chat, command-line arguments, or Agent output.

## The one-command workflow

```text
User: Open the approved service, use the Agent Account, and work for one hour.

Agent: Calls Agent Account Google ID and requests a session with a one-hour TTL.

Tool: Checks identity and capabilities, creates or reuses the Account record, starts the browser profile, and starts Live Events.

Agent: Performs only the actions granted by the site capability and browser policy.

User: Watches the activity and can Pause, Resume, Stop, Cancel, or Kill the run.

Tool: At expiry, stops the task and temporary session data. The persistent Agent Account record is kept unless explicitly revoked.
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
```

The CLI exposes the lifecycle and control surfaces. It does not claim to provision a third-party consumer account when the provider has not exposed that operation.

## Product boundary

The user does not hand over a personal account by default. An Agent Account is separate from the user's personal browser profile. Provider adapters must report unsupported operations instead of silently delegating to the user's personal account.

The runtime protects the model from raw credential material. The Agent receives an opaque handle, while provider-managed secrets remain outside the model context. The tool does not bypass CAPTCHA, MFA, anti-bot systems, rate limits, or provider restrictions.
