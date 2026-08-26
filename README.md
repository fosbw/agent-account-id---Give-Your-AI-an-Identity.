# Agent Account Google ID — Give Your AI an Identity

This tool is built for people who already use an AI Agent such as Claude Code or Codex. You bring the Agent, the model, the API key, the workspace, and the environment. **Agent Account Google ID — Give Your AI an Identity** adds the missing operating layer: an Agent identity reference, an Agent Account record, a browser profile, a persistent session, a timer, Live State, controls, policies, and cleanup.

The product is not just a timer. The timer, Pause, Resume, Stop, Kill Switch, Live View, Audit, and policies are parts of the core product. The main idea is simple: the Agent gets its own identity and its own browser context instead of using the user's personal browser profile.

## The workflow

The user gives the Agent a normal instruction:

```text
Open the approved Microsoft workspace, use my Agent Account, and work for one hour.
```

The Agent calls this tool. The tool checks the Agent identity, checks the requested capabilities, creates or reuses the Agent Account record, starts an isolated browser session, starts the timer, and sends only opaque session references to the Agent. The user watches the activity and can pause, resume, stop, or kill the run.

A task can use a real browser and real Internet only inside an environment owned and configured by the operator. A provider must officially expose the identity or account operation before an adapter can perform it. The tool never turns a user account into an Agent account by default.

## What is in main

| Capability | Current behavior |
|---|---|
| Agent supervision | Runs a user-owned Agent under a wall-clock TTL and process-group control. |
| Agent Account Runtime | Stores non-secret Agent Account records, handles, lifecycle state, provider capability state, and browser-profile references. |
| Real Account Provisioning | Provides a generic provisioning runtime and one real public test-site adapter (`ExpandTestingProvider`) that creates an external test account in Chrome before authentication. |
| Credential boundary | Accepts provider secrets only through an internal process-bound interface; public metadata, Agent output, logs, and Live State expose opaque references and safe status only. |
| Google identity | Supports the official limited identity OAuth flow and stores identity metadata only. Google account provisioning is reported as unavailable when the provider does not expose that operation. |
| GitHub Provider | Real GitHub App/OAuth token authentication and read actions through the official REST API; browser login remains provider-specific. |
| Expand Testing Provider | Real browser signup, credential placement through the internal Vault boundary, login, authenticated-page verification, and harmless page reading on the public practice environment. |
| AutomationExercise Provider | A second real browser signup/login integration using a multi-field form, normal dropdowns and checkboxes, authenticated home-page action, and same-profile/session recovery. |
| Persistent browser profile | A profile can be attached to an Agent Account and retained between tasks. Timer expiry ends the task/session; it does not delete the account record or persistent profile. |
| Browser policy | Enforces HTTPS, domain allowlists, blocked sensitive Google areas, and private/local/metadata host blocking. |
| Live Browser State | Records current URL, page label, current action, login state, verification state, session status, and timer metadata without secrets. |
| Verification handling | Records real provider states such as email, phone, OTP, MFA, CAPTCHA, or provider-blocked. It does not bypass challenges. |
| Controls | Pause, resume, stop, kill, TTL expiry, and cleanup are outside the Agent's control. |
| Claude Code | Hook adapter for session events and policy decisions. |
| Codex | Process wrapper under the same supervisor. |
| Site and Agent matrix | `SUPPORTED_SITES.md` lists the supported integration paths, environments, Agents, and requirements. |

## Install

From the repository root:

```bash
python3 -m pip install -e .
agent-account-google-id --help
```

The legacy `agentguard` command remains available only for compatibility with older installations. The product name is **Agent Account Google ID — Give Your AI an Identity**.

## Start an Agent session

```bash
agent-account-google-id run \
  --ttl 3600 \
  --workspace . \
  --allow-network \
  -- codex
```

For a session connected to an existing Agent Account and persistent browser profile:

```bash
agent-account-google-id run \
  --ttl 3600 \
  --account-id <account-id> \
  --persistent-profile \
  --identity-id <identity-id> \
  --allow-domain example.com \
  --browser-start-url https://example.com/ \
  --workspace . \
  -- codex
```

The Agent receives opaque `AGENTGUARD_*` session variables and account identifiers. It does not receive raw credentials.

## Create and inspect an Agent Account record

```bash
agent-account-google-id account create \
  --agent-id research-agent \
  --display-name "Research Agent"

agent-account-google-id account capabilities
agent-account-google-id account sites
agent-account-google-id account show <account-id>
agent-account-google-id account revoke <account-id>
```

The local Account Runtime creates a persistent local record and an opaque handle such as `agent_account://local/acct-...`. A local record is not falsely presented as a third-party Google account. Provider adapters report what they can and cannot do.

## Google identity metadata

For an identity that has already been provisioned and authorized through an official Google flow:

```bash
agent-account-google-id google-auth \
  --client-id <installed-app-client-id> \
  --identity-dir ~/.agentguard/identities
```

The flow uses PKCE and identity scopes. It stores safe subject and email metadata only. It does not create a Google account, request Gmail or Drive access, persist OAuth tokens, import browser state, or modify recovery settings.

## Browser session

Create a browser session with an explicit allowlist:

```bash
agent-account-google-id browser create \
  --ttl 3600 \
  --allow-domain example.com \
  --identity-provider google \
  --identity-id <identity-id> \
  --account-id <account-id> \
  --persistent-profile
```

Check a URL before navigation:

```bash
agent-account-google-id browser check-url <browser-session-id> https://example.com/task
```

Launch a local Chromium-compatible browser:

```bash
agent-account-google-id browser launch <browser-session-id> \
  --url https://example.com/task
```

Record safe Browser State for Live View:

```bash
agent-account-google-id browser state <browser-session-id> \
  --url https://example.com/task \
  --page "Task page" \
  --action "Reading the task"
```

Record a real verification state when the provider actually shows one:

```bash
agent-account-google-id browser verification \
  <browser-session-id> example.com phone_required
```

Observe the local redacted event stream:

```bash
agent-account-google-id watch <session-id> --follow
agent-account-google-id browser watch <browser-session-id> --follow
```

## Controls

```bash
agent-account-google-id list
agent-account-google-id pause <session-id>
agent-account-google-id resume <session-id>
agent-account-google-id stop <session-id> --reason user_requested
agent-account-google-id browser cleanup <browser-session-id>
```

The Kill path stops the Agent process group and the tracked browser process. A persistent Agent Account record and persistent profile are not deleted by task TTL. Revocation is a separate account lifecycle operation.

## Browser Authentication Runtime

The Browser Authentication Runtime is the generic layer between an Agent Account handle and a provider-specific login adapter. The Agent sends only `account_handle` and `target`; the runtime obtains the provider credential from the internal Vault boundary, discovers the login form, fills and submits it inside the isolated browser, verifies the resulting page state, records a safe Provider Session, and returns safe authentication metadata. Passwords, cookies, and tokens are not returned to the Agent, written to event logs, or included in Live State.

The first authentication integration is intentionally scoped to the public test site `the-internet.herokuapp.com`. Its site-published demo credentials are supplied to the internal process boundary through `AGENT_ACCOUNT_DEMO_USERNAME` and `AGENT_ACCOUNT_DEMO_PASSWORD`, then installed into the in-memory Vault with `--install-demo-credentials`; they are never accepted as command-line arguments or returned to the Agent. The project CLI path is:

```bash
agent-account-google-id browser authenticate \\
  --browser-dir ./browser \\
  --vault-dir ./vault \\
  <browser-session-id> \\
  --account-handle agent_account://demo-site/acct-demo \\
  --target the-internet.herokuapp.com \\
  --browser-session-name demo-auth-session \\
  --install-demo-credentials
```

A successful result contains `authenticated`, the opaque account handle, provider and session references, the safe current URL/page label, and `verification_state`; it does not contain the demo username or password. Browser cleanup revokes the recorded Provider Session metadata while retaining a persistent profile, and a later browser session for the same account reuses that profile.

## Real Account Provisioning Provider: Expand Testing

`ExpandTestingProvider` is the first real browser provisioning integration. It uses the public Automation Testing Practice environment at `practice.expandtesting.com` as a test-only provider. The provisioning runtime generates a provider-valid Agent username from organization, agent, provider, and stable Agent identifier inputs, generates a password internally, stores the credential bundle through the Vault boundary, opens the real signup form in Chrome, submits it, verifies the site redirect to login, logs in with the account created by the tool, and verifies the protected `/secure` page. It then records a harmless authenticated-page read in safe Browser State.

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

The command returns only safe identity, account, external-account reference, browser, and authentication metadata. The external reference is backed by the real signup and the subsequent real login; a local Account Record alone is never treated as proof. The practice site's authentication uses process-bound session cookies, so the provider capability reports reauthentication required after a complete browser process restart even though the Account Record and persistent Profile remain. This is recorded as a provider limitation rather than hidden or bypassed.

`AutomationExerciseProvider` reuses the same generic provisioning and authentication runtimes against a second real public practice environment. Its adapter-specific responsibilities are limited to the multi-step signup fields, normal dropdown/checkbox controls, provider success markers, logout-before-login proof, and target URLs. The live run created an external account, logged in with the generated Vault credential, read the authenticated home page, then restored the authenticated state in a new browser process using the same Account/Profile without credential injection.

## First real Provider: GitHub

GitHub is the first real provider adapter in this repository. It links an existing authorized GitHub App installation or caller-owned GitHub token through the internal Vault boundary, validates the Provider Session with the official GitHub REST API, and executes safe read actions. It does not create a GitHub account, import browser cookies, or expose the token to the Agent.

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

The command prints safe Account, Identity, Browser, and Provider Session metadata only. The current CLI supports read-only provider actions. Any write action must use a separate explicit-confirmation path.

## Sites and environments

Read [`SUPPORTED_SITES.md`](SUPPORTED_SITES.md) for the current site matrix. It covers Google Workspace/Cloud, Microsoft Entra federation, Notion, Slack, GitLab, Atlassian, Linear, GitHub, supported Agents, Linux/macOS/WSL/Docker/VM/CI environments, and the requirements for adding a provider adapter.

A named service is not automatically a working login adapter. A site must officially expose OAuth, OIDC, SSO, or an API, and the operator must configure the provider and allowlist. A Google sign-in button alone does not make every browser login flow interchangeable.

## Account Provisioner lifecycle

The runtime models this lifecycle:

```text
CREATE
  -> PROVISION
  -> INITIALIZE
  -> LOGIN / VERIFICATION STATE
  -> SESSION ACTIVE
  -> USE
  -> PAUSE / RESUME
  -> EXPIRE TASK
  -> REAUTHENTICATE WHEN PROVIDER REQUIRES IT
  -> REVOKE
  -> DESTROY LOCAL SESSION DATA
```

The provider declares its real capabilities. The Google provider in this repository reports third-party account provisioning as unavailable rather than asking for the user's personal account. `ExpandTestingProvider` declares browser account creation and internal credential initialization as supported only for its public practice environment; its process-bound session recovery is explicitly limited. Provider-managed credential operations remain outside this local process.

## Security boundary

This project is a control plane and guardrail layer. It is not an operating-system sandbox or a full network firewall. Strong isolation requires a user-controlled container or VM, an OS-level egress policy, a provider-approved identity, and an external secret manager.

Raw credentials must never enter the model context, tool output, event logs, Live View, GitHub, or command-line arguments. The current vault accepts provider secrets only through internal adapter calls, keeps raw values process-bound, and stores only opaque references and safe metadata on disk. It does not persist passwords, cookies, OAuth tokens, recovery codes, or private keys. The second live provider test proves session recovery from browser persistence state without exposing that state to the Agent.

The tool does not create or distribute consumer accounts, bypass CAPTCHA/MFA/anti-bot controls, change recovery settings, or provide unrestricted “log in anywhere” automation. When a provider does not expose an operation, the provider adapter reports that operation as unavailable.

## Development and tests

```bash
python3 -m compileall -q agentguard adapters tests
python3 -m pytest -q
python3 -m compileall -q agentguard adapters
python3 -m agentguard --help
```

## Repository layout

```text
agentguard/          Account Runtime, identity, browser, supervisor, policy, events, and redaction
adapters/            Claude Code and Codex adapters
skill/               Chat-invocable Agent Account Google ID skill
tests/               Unit and lifecycle tests
SUPPORTED_SITES.md   Sites, Agents, environments, requirements, and provider paths
REVIEW_FULL_CONCEPT.md  Full product concept and acceptance criteria
```
