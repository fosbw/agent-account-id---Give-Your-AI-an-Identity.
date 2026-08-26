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

The Universal Web Runtime adds provider-neutral `navigate`, `read`, `click`, `fill`, `select`, and `submit` mechanics. It reuses Browser Session Manager policy, records safe state, redacts page text, blocks secret-looking selectors, and returns `SafeWebResult`. It intentionally does not pretend that signup or login selectors are universal; those remain provider-adapter responsibilities.

The Agent Identity Aggregate persists a safe graph for one stable Agent identity: account handles, browser-profile references, opaque credential references, provider-session metadata, explicit permissions, bounded activity history, memory references, and lifetime state. It does not persist raw passwords, cookies, tokens, or credential-bearing browser state. The Agent Web Identity facade loads this graph, enforces Agent/account/session ownership, checks permissions, delegates actions to Universal Web Runtime, and records safe activity. The planner remains external.

The Security Boundary centralizes nested redaction, safe object handling, cross-Agent ownership checks, secret-bearing metadata rejection, and screenshot blocking during authentication or credential-entry states. Screenshot policy is deliberately conservative: the runtime blocks capture in known credential phases; it does not claim pixel-perfect OCR or image redaction.

The Browser Authentication Runtime provides a generic `LoginRequest`, `LoginAdapter`, and `BrowserAutomation` boundary. It accepts only an Agent Account handle and target from the Agent, obtains provider credentials through the process-bound Vault interface, discovers the login form, fills and submits inside the isolated browser, verifies success, persists safe Provider Session metadata, updates login/verification/browser state, and returns `SafeAuthenticationState`. The first authentication integration is `DemoLoginAdapter` for the public `the-internet.herokuapp.com/login` test site; the Demo is an adapter test, not the architecture.

The Account Provisioning Runtime adds the missing external-account stage. `AccountNamingPolicy` creates a deterministic provider-valid identity from organization, Agent, provider, and stable Agent identifier inputs without embedding the Agent Key. `ExpandTestingProvider` is a real browser-only integration for the public Automation Testing Practice environment: it creates an external test account through signup, stores the generated credential bundle behind the internal Vault boundary, logs in with the account created by the tool, verifies `/secure`, and records a harmless authenticated-page read. Its site uses process-bound session cookies, so capability metadata reports reauthentication required after a complete browser process restart; Account Record and Profile retention are still preserved.

`AutomationExerciseProvider` reuses the same generic Account Provisioning and Browser Authentication runtimes against a second real public practice environment. It handles only provider-specific normal signup controls, success markers, logout-before-login proof, and URLs. A live run created an external account, logged in with the generated Vault credential, read the authenticated home page, and restored the authenticated state in a new browser process using the same Account/Profile without credential injection.

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
agent-account-google-id web-identity show --runtime-dir ... <identity-id>
agent-account-google-id web-identity action --runtime-dir ... --identity-id ... --account-handle ... --session-id ... --browser-session-name ... --operation read
agent-account-google-id run --account-id ... --persistent-profile ...
```

The product-facing executable is `agent-account-google-id`. The legacy `agentguard` executable remains as a compatibility alias. The package module directory remains `agentguard` so existing imports and integrations do not break.

The repository documentation is in English and uses the product name: README, Skill, integration guide, full concept specification, identity/browser guide, supported-site matrix, threat model, and build report.

## Verification performed

| Check | Result |
|---|---|
| Unit and lifecycle tests | **52 passed** |
| Python compilation | Passed for `agentguard`, `adapters`, tests, and live-validation scripts |
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
| Provider capability matrix test | Passed: normalized `CREATE_ACCOUNT`, `INITIALIZE_ACCOUNT`, `AUTHENTICATE`, `PERSIST_SESSION`, `REFRESH_SESSION`, `REVOKE_SESSION`, `ROTATE_CREDENTIAL`, and `VERIFY_STATE` keys |
| Agent Identity Aggregate tests | Passed: safe graph persistence, ownership rejection, safe session metadata, permissions, activity, and memory references |
| Security Boundary tests | Passed: nested password/token/secret/cookie/bearer redaction, Browser Authentication safe page-label redaction, cross-Agent account rejection, and screenshot blocking during auth/credential phases |
| Agent Web Identity integration tests | Passed: safe read/action result, explicit permission enforcement, activity recording, browser-session ownership rejection, challenge-only chat event, and Done-only resume signal |
| Chat Verification Handoff tests | Passed: no message without a pending challenge, safe challenge message when detected, verification-code rejection, and provider recheck-required resume state |
| Universal Web Runtime live test | **Passed live** in isolated Chrome: `https://example.com/` navigate plus rendered-page read; output contained safe page text only |
| Agent Web Identity CLI smoke test | Passed: parser and help expose `permissions`, `show`, and `action` facade commands |
| Verification handoff CLI | Passed: `browser verification-resume` exposes only a safe resume signal and never accepts a verification code |
| Chat Verification Handoff | Passed: no chat event without a real pending challenge, safe challenge event when detected, rejection of verification codes, `Done` resume signal, and provider authentication recheck requirement |
| Account Provisioning unit tests | Passed: deterministic naming, external-account/Vault/Profile linkage, safe authenticated action, Kill preservation, and Provider Session revocation |
| Real second-provider Full Flow | **Passed live**: AutomationExercise signup -> external account creation -> logout -> Vault-backed login -> authenticated home-page read -> Kill -> new browser process -> same Account/Profile -> authenticated action without credential injection |
| Generic-runtime comparison | **Passed live across two different providers**: the generic Provisioning/Authentication/Profile/Session lifecycle was reused; provider-specific code remained in each adapter's normal form handling and success markers |
| Real external account provisioning flow | **Passed through authenticated post-signup action**: Expand Testing signup -> account-created redirect -> login -> `/secure` -> safe page read |
| Real process-restart session recovery | **Blocked by provider behavior**: Expand Testing uses process-bound session cookies; Account and Profile survive, but authenticated state is not restored without reauthentication |
| Real public Demo CLI lifecycle | Passed: create -> discover/fill/submit/verify -> safe state -> Provider Session -> cleanup/Kill -> new session -> same Account/Profile -> authenticate again |
| `git diff --check` | Passed |

## Deliberately unavailable provider operations

The repository does not claim to create or distribute consumer Google accounts, operate a shared account pool, import cookies, retrieve passwords or recovery codes, bypass MFA/CAPTCHA, or provide unrestricted cross-site login. The Google provider reports unavailable operations clearly. Provider-specific credentials are accepted only through internal adapter boundaries and raw values remain process-bound; a production deployment should replace that boundary with an approved external secret manager. The Core end-to-end test uses `TestProviderAdapter`, while the Browser Authentication tests use narrowly scoped public test-site adapters and live public-site CLI runs. The real provisioning proof uses only public practice environments and does not claim production-provider support.

## Known limitations

Command matching is a guardrail, not a complete sandbox. Browser URL decisions are a policy layer, not a browser extension, proxy, or OS egress firewall. Strong isolation requires a user-controlled container or VM plus OS-level egress controls.

The current Live View is local and text/event based. It can expose safe browser state, but it is not a hosted remote video stream. Browser launch requires a Chromium-compatible executable in the user's environment. Persistent browser profiles require suitable local storage and one active browser session per profile. Browser Authentication currently has one Demo integration and two real public test-site provisioning integrations; other providers need their own authorized LoginAdapter, provisioning adapter, and capability declaration. The current AccountVault is process-bound and intentionally does not persist raw passwords to disk. The Universal Web Runtime is general for browser mechanics, not a universal signup/login engine. Screenshot protection blocks known credential-entry phases but cannot promise perfect pixel-level secret detection in arbitrary page images.
