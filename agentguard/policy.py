from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Policy:
    workspace: Path
    allow_network: bool = False
    deny_patterns: list[str] = field(default_factory=lambda: [
        "rm -rf /",
        "rm -rf ~",
        "sudo ",
        "chmod 777",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",
    ])
    blocked_paths: tuple[str, ...] = (".env", ".ssh", ".aws", ".config/gcloud")

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()

    def path_allowed(self, path: str | Path) -> bool:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        try:
            candidate.resolve().relative_to(self.workspace)
            return True
        except ValueError:
            return False

    def sensitive_path(self, path: str | Path) -> bool:
        value = str(path).replace(os.sep, "/")
        return any(token in value or value.endswith(token) for token in self.blocked_paths)

    def check_command(self, command: str) -> tuple[bool, str]:
        normalized = command.strip().lower()
        for pattern in self.deny_patterns:
            if pattern.lower() in normalized:
                return False, f"command matched guardrail: {pattern}"
        if not self.allow_network and any(token in normalized for token in ("curl ", "wget ", "invoke-webrequest", "pip install", "npm install", "git clone")):
            return False, "network-capable command blocked while network is disabled"
        return True, "allowed by local guardrails"

    def check_tool_payload(self, tool_name: str, payload: dict) -> tuple[bool, str]:
        command = payload.get("command") or payload.get("cmd")
        if isinstance(command, str):
            return self.check_command(command)
        for key in ("path", "file_path", "cwd", "workdir"):
            value = payload.get(key)
            if isinstance(value, str) and not self.path_allowed(value):
                return False, f"path outside workspace: {value}"
            if isinstance(value, str) and self.sensitive_path(value):
                return False, f"sensitive path blocked: {value}"
        return True, "no blocking rule matched"

    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env["AGENTGUARD_WORKSPACE"] = str(self.workspace)
        env["AGENTGUARD_NETWORK"] = "allow" if self.allow_network else "deny"
        return env
