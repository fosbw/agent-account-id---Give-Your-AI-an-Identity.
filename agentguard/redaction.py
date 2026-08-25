from __future__ import annotations

import re
from typing import Any


_PATTERNS = [
    (re.compile(r"(?i)(sk-[a-z0-9_-]{20,})"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"(?i)(gh[pousr]_[a-z0-9_]{20,})"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"(?i)(xox[baprs]-[a-z0-9-]{15,})"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|PRIVATE) KEY-----[\s\S]*?-----END (?:RSA|EC|OPENSSH|PRIVATE) KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"), r"\1[REDACTED_BEARER]"),
    (re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)['\"]?[^\s,'\"]+"), r"\1[REDACTED_API_KEY]"),
    (re.compile(r"(?i)(password\s*[=:]\s*)['\"]?[^\s,'\"]+"), r"\1[REDACTED_PASSWORD]"),
]


class Redactor:
    def __init__(self, extra_patterns: list[tuple[str, str]] | None = None):
        self.patterns = list(_PATTERNS)
        for pattern, replacement in extra_patterns or []:
            self.patterns.append((re.compile(pattern), replacement))

    def redact_text(self, text: str) -> str:
        for pattern, replacement in self.patterns:
            text = pattern.sub(replacement, text)
        return text

    def redact_object(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, list):
            return [self.redact_object(item) for item in value]
        if isinstance(value, dict):
            return {key: self.redact_object(item) for key, item in value.items()}
        return value
