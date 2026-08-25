# Agent, identity, and browser integration

## Claude Code

Claude Code exposes lifecycle hooks, including pre-tool and post-tool events. The adapter in `adapters/claude_hook.py` accepts hook JSON from standard input, records a redacted event, checks supported payload fields against local guardrails, and emits a `PreToolUse` deny response when a rule matches.

A user's Claude Code settings can call it for an intentionally supervised session:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Read|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python adapters/claude_hook.py --event PreToolUse"
          }
        ]
      }
    ]
  }
}
```

The hook is intentionally a no-op when `AGENTGUARD_SESSION_ID` is absent. The user must set that variable for the process they intentionally supervise. Use an absolute path or an installed package command when the repository is not the working directory.

## Codex

Codex can be wrapped as a local process:

```bash
python adapters/codex_run.py --ttl 1800 --workspace . -- codex
```

The wrapper does not authenticate Codex, create a user, import cookies, or alter provider settings. It supervises the command the user already installed and authorized.

## Google OAuth identity metadata

For an already provisioned and authorized Google identity, the CLI supports a one-time installed-app OAuth flow with loopback callback, PKCE, and `openid email profile` scopes only:

```bash
python -m agentguard google-auth \
  --client-id <installed-app-client-id> \
  --identity-dir ~/.agentguard/identities
```

The flow uses Google's normal consent UI, keeps the access token in memory only long enough to obtain identity metadata, and persists only a generated identity reference. It does not create accounts, request Gmail/Drive/admin scopes, persist access or refresh tokens, import cookies, or prove website login. Provider authorization and identity ownership remain external prerequisites.

## Safe identity reference

Attach only provider-authorized metadata:

```bash
python -m agentguard identity attach \
  --provider google \
  --subject provider-subject-id \
  --authorization-basis test_account
```

The resulting `identity_id` is a reference, not a credential. Never put a password, cookie, OAuth token, recovery code, or private key in CLI arguments, environment variables intended for metadata, manifests, or logs.

## Controlled browser session

Create a short-lived session with an explicit allowlist:

```bash
python -m agentguard browser create \
  --ttl 1800 \
  --allow-domain example.com \
  --identity-provider google \
  --identity-id <identity-id>
```

The browser commands can check URLs, launch an ephemeral Chromium profile, record a manual login handoff, and clean up. The handoff is deliberately human-operated:

```bash
python -m agentguard browser login-handoff <browser-session-id> example.com
python -m agentguard browser launch <browser-session-id> --url https://example.com/
# Authorized operator completes normal login/MFA/CAPTCHA UI.
python -m agentguard browser login-complete <browser-session-id> example.com
```

The local policy blocks embedded URL credentials, private targets, sensitive Google services, and recovery/password/challenge paths. It does not replace a container, VM, browser extension, proxy, or egress firewall.

## Chat invocation

Copy `skill/SKILL.md` into the user's supported skills directory or plugin mechanism. The skill teaches the agent to ask for a duration, workspace, identity reference, and domain allowlist, then invoke local commands. It does not contain provider credentials or account-creation workflows.

## Viewer model

The viewer is local and text-based:

```bash
python -m agentguard watch <session-id> --follow
python -m agentguard browser watch <browser-session-id> --follow
```

This intentionally avoids turning a local session log into a remote account-sharing service. A remote read-only viewer or live video layer, if added later, must be designed separately with authentication, authorization, redaction, retention, explicit consent, and a deployment environment.
