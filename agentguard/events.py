from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Event:
    session_id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "session_id": self.session_id,
            "kind": self.kind,
            "payload": self.payload,
        }


class EventLog:
    """Append-only JSONL event log with a process-safe enough local lock."""

    def __init__(self, path: Path, session_id: str, redactor=None):
        self.path = path
        self.session_id = session_id
        self.redactor = redactor
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, kind: str, payload: dict[str, Any] | None = None) -> Event:
        event = Event(self.session_id, kind, payload or {})
        data = event.as_dict()
        if self.redactor:
            data = self.redactor.redact_object(data)
        line = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
        return event

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows
