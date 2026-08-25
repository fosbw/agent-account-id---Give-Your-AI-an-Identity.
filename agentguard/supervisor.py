from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .events import EventLog
from .policy import Policy
from .redaction import Redactor


@dataclass
class SessionPaths:
    root: Path
    session_id: str

    @property
    def directory(self) -> Path:
        return self.root / self.session_id

    @property
    def events(self) -> Path:
        return self.directory / "events.jsonl"

    @property
    def metadata(self) -> Path:
        return self.directory / "session.json"


class Supervisor:
    def __init__(self, root: Path | None = None):
        configured_root = os.environ.get("AGENTGUARD_SESSION_ROOT")
        self.root = (root or Path(configured_root) if configured_root else root or Path.home() / ".agentguard" / "sessions").expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def new_session(self, command: Iterable[str], workspace: Path, ttl: float, allow_network: bool = False, context: dict[str, str] | None = None) -> str:
        if ttl <= 0:
            raise ValueError("ttl must be greater than zero")
        command = list(command)
        if not command:
            raise ValueError("an agent command is required")
        session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        paths = SessionPaths(self.root, session_id)
        paths.directory.mkdir(parents=True, exist_ok=False)
        redactor = Redactor()
        log = EventLog(paths.events, session_id, redactor)
        policy = Policy(workspace, allow_network=allow_network)
        safe_context = {}
        for key, value in (context or {}).items():
            if key in {"identity_id", "browser_session_id", "browser_profile", "browser_allowed_domains"} and isinstance(value, str) and len(value) <= 2048:
                safe_context[key] = value
        metadata = {
            "session_id": session_id,
            "command": command,
            "workspace": str(policy.workspace),
            "ttl_seconds": ttl,
            "allow_network": allow_network,
            "status": "starting",
            "created_at": time.time(),
            "pid": None,
            "pgid": None,
            "context": safe_context,
        }
        self._write_metadata(paths, metadata)
        log.emit("session.created", {"command": command, "workspace": str(policy.workspace), "ttl_seconds": ttl, "context": safe_context})
        if safe_context:
            log.emit("session.identity_context_attached", safe_context)
        return session_id

    def run(self, session_id: str, command: list[str], workspace: Path, ttl: float, allow_network: bool = False, extra_env: dict[str, str] | None = None) -> int:
        paths = SessionPaths(self.root, session_id)
        redactor = Redactor()
        log = EventLog(paths.events, session_id, redactor)
        policy = Policy(workspace, allow_network=allow_network)
        env = policy.environment()
        env["AGENTGUARD_SESSION_ID"] = session_id
        if extra_env:
            env.update({key: value for key, value in extra_env.items() if key.startswith("AGENTGUARD_")})
        start_new_session = os.name != "nt"
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(policy.workspace),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=None,
                text=False,
                bufsize=0,
                start_new_session=start_new_session,
                creationflags=creationflags,
            )
        except OSError as exc:
            log.emit("session.start_failed", {"error": str(exc), "command": command})
            self._update_metadata(paths, {"status": "failed", "error": str(exc)})
            raise

        pgid = os.getpgid(proc.pid) if os.name != "nt" else None
        self._update_metadata(paths, {"status": "running", "pid": proc.pid, "pgid": pgid, "started_at": time.time()})
        log.emit("session.started", {"pid": proc.pid, "pgid": pgid, "command": command})
        deadline = time.monotonic() + ttl
        timed_out = threading.Event()

        def timeout_worker() -> None:
            remaining = max(0.0, deadline - time.monotonic())
            if not timed_out.wait(remaining):
                timed_out.set()
                log.emit("session.expired", {"ttl_seconds": ttl})
                self.stop(session_id, reason="ttl_expired")

        timer = threading.Thread(target=timeout_worker, name=f"agentguard-timer-{session_id}", daemon=True)
        timer.start()
        try:
            assert proc.stdout is not None
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                safe = redactor.redact_text(line)
                log.emit("agent.output", {"stream": "stdout", "text": safe})
                print(safe, flush=True)
            return_code = proc.wait()
        finally:
            timed_out.set()
            timer.join(timeout=1)
            if proc.poll() is None:
                self._kill_process(proc.pid, pgid, log, "parent_exit_cleanup")
                proc.wait(timeout=5)
        status = "expired" if self._metadata_status(paths) == "stopping" and timed_out.is_set() else ("completed" if return_code == 0 else "failed")
        self._update_metadata(paths, {"status": status, "return_code": return_code, "finished_at": time.time()})
        log.emit("session.finished", {"return_code": return_code, "status": status})
        return return_code

    def stop(self, session_id: str, reason: str = "user_stop") -> None:
        paths = self._paths(session_id)
        data = self._read_metadata(paths)
        pid, pgid = data.get("pid"), data.get("pgid")
        self._update_metadata(paths, {"status": "stopping", "stop_reason": reason})
        log = EventLog(paths.events, session_id, Redactor())
        log.emit("session.stop_requested", {"reason": reason, "pid": pid, "pgid": pgid})
        if pid:
            self._kill_process(int(pid), int(pgid) if pgid else None, log, reason)

    def pause(self, session_id: str) -> None:
        paths = self._paths(session_id)
        data = self._read_metadata(paths)
        pid, pgid = data.get("pid"), data.get("pgid")
        if not pid:
            raise RuntimeError("session has no running process")
        if os.name == "nt":
            raise RuntimeError("pause is not implemented on Windows; use stop")
        os.killpg(int(pgid or os.getpgid(int(pid))), signal.SIGSTOP)
        self._update_metadata(paths, {"status": "paused"})
        EventLog(paths.events, session_id, Redactor()).emit("session.paused", {})

    def resume(self, session_id: str) -> None:
        paths = self._paths(session_id)
        data = self._read_metadata(paths)
        pid, pgid = data.get("pid"), data.get("pgid")
        if not pid:
            raise RuntimeError("session has no process")
        if os.name == "nt":
            raise RuntimeError("resume is not implemented on Windows")
        os.killpg(int(pgid or os.getpgid(int(pid))), signal.SIGCONT)
        self._update_metadata(paths, {"status": "running"})
        EventLog(paths.events, session_id, Redactor()).emit("session.resumed", {})

    def _kill_process(self, pid: int, pgid: int | None, log: EventLog, reason: str) -> None:
        # Never target our own process group; metadata is treated as untrusted input.
        try:
            if os.name != "nt" and pgid and pgid not in (os.getpgrp(), 1):
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.2)
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
            else:
                os.kill(pid, signal.SIGKILL)
            log.emit("session.process_group_stopped", {"pid": pid, "pgid": pgid, "reason": reason})
        except ProcessLookupError:
            log.emit("session.process_already_stopped", {"pid": pid, "pgid": pgid, "reason": reason})
        except PermissionError as exc:
            log.emit("session.stop_error", {"error": str(exc), "pid": pid, "pgid": pgid, "reason": reason})

    def _paths(self, session_id: str) -> SessionPaths:
        if not session_id or "/" in session_id or "\\" in session_id or session_id in {".", ".."}:
            raise ValueError("invalid session id")
        return SessionPaths(self.root, session_id)

    def _read_metadata(self, paths: SessionPaths) -> dict:
        return json.loads(paths.metadata.read_text(encoding="utf-8"))

    def _metadata_status(self, paths: SessionPaths) -> str | None:
        try:
            return self._read_metadata(paths).get("status")
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _write_metadata(self, paths: SessionPaths, data: dict) -> None:
        paths.metadata.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _update_metadata(self, paths: SessionPaths, updates: dict) -> None:
        data = self._read_metadata(paths) if paths.metadata.exists() else {}
        data.update(updates)
        self._write_metadata(paths, data)
