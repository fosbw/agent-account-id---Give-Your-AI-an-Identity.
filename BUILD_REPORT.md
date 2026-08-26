# Agent Account Google ID — Build Report

## Product

**Agent Account Google ID — Give Your AI an Identity** is a local-first Account Runtime and control plane around a user-owned AI Agent. The user brings the Agent, model access, Agent Key, workspace, and environment. The Tool adds an Agent Account record, identity reference, browser profile, persistent session, capabilities, timer, Live State, controls, policy checks, audit events, and cleanup.

## Implemented

The original Supervisor provides a TTL timer, dedicated POSIX process group, best-effort process-group termination, POSIX pause/resume, a redacted JSONL event log, local watch, workspace and sensitive-path checks, command guardrails, and Claude Code/Codex adapters.

The Account Runtime adds `AgentAccount`, `AccountProvisioner`, `LocalManagedAccountProvisioner`, `GoogleProvider`, `ProviderCapabilities`, `ProviderOperationUnavailable`, and `AccountVault`. Account records contain safe metadata, opaque handles, lifecycle state, identity references, provider state, and browser-profile references. The vault accepts provider secrets through an internal `put_secret` boundary, keeps raw values process-bound, and exposes only opaque references and safe metadata. Raw values are never written to disk, returned by public metadata methods, or sent to the Agent.

The Core Runtime adds a separate `ProviderAdapter`, `ProviderSession`, `AgentIdentity`, `AccountStore`, `AccountRuntime`, and `CorePath`. `AccountRuntime` orchestrates Agent Key -> Agent Identity -> Account Provisioning -> Credential Vault -> Browser Profile -> Persistent Browser Session -> Provider Session -> Agent Action -> Kill -> Restart.

The provider model exposes capability discovery for account creation, identity initialization, credential initialization, browser sessions, persistent sessions, verification, recovery, rotation, and revocation. The Google provider reports third-party account provisioning as unavailable when the provider does not expose that operation. It does not ask for a user's personal account as a silent fallback.

The browser layer supports isolated ephemeral profiles and persistent profiles attached to an Agent Account. A task TTL ends the current task and browser process without deleting a persistent Account record or persistent profile. Browser manifests now include account ID, persistence state, login state, verification state, current URL, current page, and current action. The real provisioning path uses a dedicated persistent profile for the externally created test account.

The browser policy enforces HTTPS, explicit domain allowlists, blocked sensitive Google areas, credentials-in-URL blocking, and private/local/link-local/metadata host blocking. The browser runtime can record safe browser state and real verification states such as email, phone, OTP, MFA, CAPTCHA, provider-blocked, or completed. It never bypasses a challenge.

The Browser Authentication Runtime provides a generic `LoginRequest`, `LoginAdapter`, and `BrowserAutomation` boundary. It accepts only an Agent Account handle and target from the Agent, obtains provider credentials through the process-bound Vault interface, discovers the login form, fills and submits inside the isolated browser, verifies success, persists safe Provider Session metadata, updates login/verification/browser state, and returns `SafeAuthenticationState`. The first authentication integration is `DemoLoginAdapter` for the public `the-internet.herokuapp.com/login` test site; the Demo is an adapter test, not the architecture.

The Account Provisioning Runtime adds the missing external-account stage. `AccountNamingPolicy` creates a deterministic provider-valid identity from organization, Agent, provider, and stable Agent identifier inputs without embedding the Agent Key. `ExpandTestingProvider` is a real browser-only integration for the public Automation Testing Practice environment: it creates an external test account through signup, stores the generated credential bundle behind the internal Vault boundary, logs in with the account created by the tool, verifies `/secure`, and records a harmless authenticated-page read. Its site uses process-bound session cookies, so capability metadata reports reauthentication required after a complete browser process restart; Account Record and Profile retention are still preserved.

The CLI includes:

```text
agent-account-google-id account create
agent-account-google-id account show
agent-account-google-id account revoke
agent-account-google-id account capabilities
agent-account-google-id account sites
agent-account-google-id account vault-reference
agent-account-google-id browser create --account-id ... --persistent-profile
agent-account-google-id browser state
agent-account-google-id browser verification
agent-account-google-id browser authenticate --account-handle ... --target ... --install-demo-credentials
agent-account-google-id browser provision --organization-id ... --agent-id ... --stable-agent-id ... --agent-key-stdin
agent-account-google-id run --account-id ... --persistent-profile ...
```

The product-facing executable is `agent-account-google-id`. The legacy `agentguard` executable remains as a compatibility alias. The package module directory remains `agentguard` so existing imports and integrations do not break.

The repository documentation is in English and uses the product name: README, Skill, integration guide, full concept specification, identity/browser guide, supported-site matrix, threat model, and build report.

## Verification performed

| Check | Result |
|---|---|
| Unit and lifecycle tests | 32 passed |
| Python compilation | Passed for `agentguard`, `adapters`, and tests |
| Existing Supervisor tests | Passed |
| Browser URL policy tests | Passed |
| Browser lifecycle tests | Passed |
| Persistent profile retention test | Passed |
| Account lifecycle test | Passed |
| `test_agent_account_end_to_end_lifecycle` | Passed: Agent Key -> Identity -> Account -> Vault -> Browser Profile -> Provider Session -> Action -> Kill -> Restart -> same persistent Account |
| Account Vault secret-field rejection | Passed |
| Google provider capability test | Passed |
| Capability wildcard rejection | Passed |
| CLI Account/Browser smoke tests | Passed after fixing Browser State parser collision |
| Editable package installation | Passed earlier for product command |
| `agent-account-google-id --help` | Passed; includes Account and Browser commands |
| Browser Authentication unit tests | Passed: Vault isolation, form detection, safe state, Provider Session persistence, failure state, Kill/Cleanup revocation, and same-profile restart |
| Account Provisioning unit tests | Passed: deterministic naming, external-account/Vault/Profile linkage, safe authenticated action, Kill preservation, and Provider Session revocation |
| Real external account provisioning flow | **Passed through authenticated post-signup action**: Expand Testing signup -> account-created redirect -> login -> `/secure` -> safe page read |
| Real process-restart session recovery | **Blocked by provider behavior**: Expand Testing uses process-bound session cookies; Account and Profile survive, but authenticated state is not restored without reauthentication |
| Real public Demo CLI lifecycle | Passed: create -> discover/fill/submit/verify -> safe state -> Provider Session -> cleanup/Kill -> new session -> same Account/Profile -> authenticate again |
| `git diff --check` | Passed |

## Deliberately unavailable provider operations

The repository does not claim to create or distribute consumer Google accounts, operate a shared account pool, import cookies, retrieve passwords or recovery codes, bypass MFA/CAPTCHA, or provide unrestricted cross-site login. The Google provider reports unavailable operations clearly. Provider-specific credentials are accepted only through internal adapter boundaries and raw values remain process-bound; a production deployment should replace that boundary with an approved external secret manager. The Core end-to-end test uses `TestProviderAdapter`, while the Browser Authentication test uses a narrowly scoped public Demo adapter and a real public-site CLI run. The real provisioning proof uses only the public Expand Testing practice environment and does not claim production-provider support.

## Known limitations

Command matching is a guardrail, not a complete sandbox. Browser URL decisions are a policy layer, not a browser extension, proxy, or OS egress firewall. Strong isolation requires a user-controlled container or VM plus OS-level egress controls.

The current Live View is local and text/event based. It can expose safe browser state, but it is not a hosted remote video stream. Browser launch requires a Chromium-compatible executable in the user's environment. Persistent browser profiles require suitable local storage and one active browser session per profile. Browser Authentication currently has one Demo integration and one real public test-site provisioning integration; other providers need their own authorized LoginAdapter, provisioning adapter, and capability declaration. The current AccountVault is process-bound and intentionally does not persist raw passwords to disk.
