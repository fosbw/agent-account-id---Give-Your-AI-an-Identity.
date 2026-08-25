# Supported agents and integration boundary

The project is agent-neutral: it supervises a process or receives documented hook events, while the user supplies the agent and model access.

| Agent/runtime | Current status | Integration boundary |
|---|---|---|
| Claude Code | First-class local adapter | Documented hook JSON through `adapters/claude_hook.py`; no provider authentication changes. See the [Claude Code hooks documentation](https://code.claude.com/docs/en/hooks). |
| Codex CLI | First-class local adapter | Thin process wrapper through `adapters/codex_run.py`; the locally installed CLI remains responsible for its own authorization. |
| Gemini CLI | Planned adapter | The agent can be supervised as a local command. A dedicated hook/MCP adapter should be added only against the current official interface; the repository does not claim one is implemented. See [Gemini CLI web search](https://geminicli.com/docs/tools/web-search/). |
| GitHub Copilot CLI | Planned adapter | The command can be wrapped locally. A first-class hook/MCP mapping remains roadmap work. See [GitHub Copilot documentation](https://docs.github.com/en/copilot). |
| MCP-compatible agent | Planned generic adapter | A future MCP server can expose policy decisions and lifecycle events. It must not expose passwords, cookies, refresh tokens, or unrestricted browser control. |

## Provider identity boundary

The identity layer accepts a provider/subject reference and safe metadata. It does not create or share accounts, import browser state, broker credentials, or assert that a manual login succeeded. A provider-specific implementation requires explicit provider authorization, a documented identity ownership model, scope restrictions, revocation, retention, and an isolated deployment environment.

## Adding an adapter

An adapter should translate only documented lifecycle/tool events into the common event schema. It must preserve the session TTL and stop controls, call the redactor before logging, avoid logging command arguments that may contain secrets, and fail closed for unsupported browser or identity operations. Tests should cover malformed payloads, missing session IDs, policy denials, child-process cleanup, and secret redaction.
