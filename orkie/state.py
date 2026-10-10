"""Per-user state root, process lock, JSON documents, agent logs."""

from __future__ import annotations

import fcntl
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StateError(Exception):
    """Corrupt or unusable state document."""


@dataclass(frozen=True, slots=True)
class ClaimRecord:
    agent_id: str
    issue_number: int
    claimed_at: str


@dataclass(frozen=True, slots=True)
class SnapshotIssue:
    number: int
    title: str
    body: str
    url: str
    state: str
    labels: list[str]


@dataclass(frozen=True, slots=True)
class Snapshot:
    fetched_at: str
    issues: list[SnapshotIssue]


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: str
    agent_id: str
    issue_number: int | None
    pr_number: int | None
    working: bool
    worktree_path: str
    started_at: str


@dataclass(frozen=True, slots=True)
class SpawnFailureRecord:
    agent_id: str
    agent_name: str
    issue_number: int | None
    pr_number: int | None
    attempt: int
    released: bool
    error: str
    at: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_state_root(owner: str, repo: str, *, home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / ".local" / "share" / "orkie" / f"{owner}--{repo}"


def redact_token(text: str, token: str | None) -> str:
    if not token:
        return text
    return text.replace(token, "***")


class StateStore:
    def __init__(self, state_root: Path, *, github_token: str | None = None) -> None:
        self._state_root = state_root
        self._github_token = github_token
        self._lock_fd: int | None = None
        self._log_locks: dict[str, threading.Lock] = {}
        self._log_locks_guard = threading.Lock()

    @property
    def state_root(self) -> Path:
        return self._state_root

    def set_github_token(self, github_token: str | None) -> None:
        """Refresh the token used for log redaction (e.g. after privilege retry)."""
        self._github_token = github_token

    def acquire_lock(self) -> None:
        self.ensure_layout()
        lock_path = self._state_root / "lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise StateError("process lock is held by another process") from exc
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 65536)
        if raw:
            holder_alive = False
            try:
                data = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = None
            if isinstance(data, dict) and type(data.get("pid")) is int:
                pid = data["pid"]
                if _pid_alive(pid):
                    holder_alive = True
            if holder_alive:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                raise StateError(f"another Orkie process is running (pid {data['pid']})")
            # Stale or corrupt lock JSON once flock held: overwrite below.
        started = utc_now_iso()
        payload = json.dumps({"pid": os.getpid(), "started_at": started}, separators=(",", ":"))
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, payload.encode("utf-8"))
        os.fsync(fd)
        self._lock_fd = fd

    def release_lock(self) -> None:
        if self._lock_fd is None:
            return
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(self._lock_fd)
            self._lock_fd = None

    def ensure_layout(self) -> None:
        self._state_root.mkdir(parents=True, exist_ok=True)
        (self._state_root / "logs").mkdir(exist_ok=True)
        (self._state_root / "worktrees").mkdir(exist_ok=True)

    def load_snapshot(self) -> Snapshot | None:
        path = self._state_root / "snapshot"
        if not path.exists():
            return None
        data = self._load_json(path, label="snapshot")
        return _parse_snapshot(data)

    def save_snapshot(self, snapshot: Snapshot) -> None:
        payload = {
            "fetched_at": snapshot.fetched_at,
            "issues": [
                {
                    "number": issue.number,
                    "title": issue.title,
                    "body": issue.body,
                    "url": issue.url,
                    "state": issue.state,
                    "labels": list(issue.labels),
                }
                for issue in snapshot.issues
            ],
        }
        self._atomic_write("snapshot", payload)

    def load_claims(self) -> list[ClaimRecord]:
        path = self._state_root / "claims"
        if not path.exists():
            return []
        data = self._load_json(path, label="claims")
        return _parse_claims(data)

    def save_claims(self, claims: list[ClaimRecord]) -> None:
        payload = {
            "claims": [
                {
                    "agent_id": claim.agent_id,
                    "issue_number": claim.issue_number,
                    "claimed_at": claim.claimed_at,
                }
                for claim in claims
            ]
        }
        self._atomic_write("claims", payload)

    def load_sessions(self) -> list[SessionRecord]:
        path = self._state_root / "sessions"
        if not path.exists():
            return []
        data = self._load_json(path, label="sessions")
        return _parse_sessions(data)

    def save_sessions(self, sessions: list[SessionRecord]) -> None:
        payload = {
            "sessions": [
                {
                    "session_id": session.session_id,
                    "agent_id": session.agent_id,
                    "issue_number": session.issue_number,
                    "pr_number": session.pr_number,
                    "working": session.working,
                    "worktree_path": session.worktree_path,
                    "started_at": session.started_at,
                }
                for session in sessions
            ]
        }
        self._atomic_write("sessions", payload)

    def delete_sessions(self) -> None:
        path = self._state_root / "sessions"
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def load_spawn_failures(self) -> list[SpawnFailureRecord]:
        path = self._state_root / "spawn_failures"
        if not path.exists():
            return []
        data = self._load_json(path, label="spawn_failures")
        return _parse_spawn_failures(data)

    def save_spawn_failures(self, failures: list[SpawnFailureRecord]) -> None:
        payload = {
            "failures": [
                {
                    "agent_id": failure.agent_id,
                    "agent_name": failure.agent_name,
                    "issue_number": failure.issue_number,
                    "pr_number": failure.pr_number,
                    "attempt": failure.attempt,
                    "released": failure.released,
                    "error": failure.error,
                    "at": failure.at,
                }
                for failure in failures
            ]
        }
        self._atomic_write("spawn_failures", payload)

    def append_log(
        self,
        agent_id: str,
        line: str,
        *,
        session_id: str,
        issue_number: int | None = None,
        pr_number: int | None = None,
    ) -> None:
        lock = self._agent_log_lock(agent_id)
        redacted = redact_token(line, self._github_token)
        parts = [utc_now_iso(), f"session_id={session_id}"]
        if issue_number is not None:
            parts.append(f"issue={issue_number}")
        if pr_number is not None:
            parts.append(f"pr={pr_number}")
        parts.append(redacted)
        text = " ".join(parts) + "\n"
        path = self._state_root / "logs" / f"{agent_id}.log"
        with lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()

    def read_log(self, agent_id: str) -> str:
        path = self._state_root / "logs" / f"{agent_id}.log"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _agent_log_lock(self, agent_id: str) -> threading.Lock:
        with self._log_locks_guard:
            lock = self._log_locks.get(agent_id)
            if lock is None:
                lock = threading.Lock()
                self._log_locks[agent_id] = lock
            return lock

    def _load_json(self, path: Path, *, label: str) -> dict[str, Any]:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StateError(f"corrupt {label} file: {path}") from exc
        if not isinstance(data, dict):
            raise StateError(f"corrupt {label} file: {path}")
        return data

    def _atomic_write(self, name: str, payload: dict[str, Any]) -> None:
        target = self._state_root / name
        tmp = self._state_root / f"{name}.tmp"
        text = json.dumps(payload, indent=2) + "\n"
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _require_key(data: dict[str, Any], key: str, *, label: str) -> object:
    if key not in data:
        raise StateError(f"corrupt {label}: missing {key}")
    return data[key]


def _parse_snapshot(data: dict[str, Any]) -> Snapshot:
    fetched_at = _require_key(data, "fetched_at", label="snapshot")
    issues_raw = _require_key(data, "issues", label="snapshot")
    if not isinstance(fetched_at, str) or not isinstance(issues_raw, list):
        raise StateError("corrupt snapshot file")
    for key in data:
        if key not in {"fetched_at", "issues"}:
            raise StateError(f"corrupt snapshot: unknown key {key}")
    issues: list[SnapshotIssue] = []
    for item in issues_raw:
        if not isinstance(item, dict):
            raise StateError("corrupt snapshot file")
        issues.append(
            SnapshotIssue(
                number=_as_int(item, "number", label="snapshot"),
                title=_as_str(item, "title", label="snapshot"),
                body=_as_str(item, "body", label="snapshot"),
                url=_as_str(item, "url", label="snapshot"),
                state=_as_str(item, "state", label="snapshot"),
                labels=_as_str_list(item, "labels", label="snapshot"),
            )
        )
    return Snapshot(fetched_at=fetched_at, issues=issues)


def _parse_claims(data: dict[str, Any]) -> list[ClaimRecord]:
    claims_raw = _require_key(data, "claims", label="claims")
    if not isinstance(claims_raw, list):
        raise StateError("corrupt claims file")
    for key in data:
        if key != "claims":
            raise StateError(f"corrupt claims: unknown key {key}")
    claims: list[ClaimRecord] = []
    for item in claims_raw:
        if not isinstance(item, dict):
            raise StateError("corrupt claims file")
        claims.append(
            ClaimRecord(
                agent_id=_as_str(item, "agent_id", label="claims"),
                issue_number=_as_int(item, "issue_number", label="claims"),
                claimed_at=_as_str(item, "claimed_at", label="claims"),
            )
        )
    return claims


def _parse_sessions(data: dict[str, Any]) -> list[SessionRecord]:
    sessions_raw = _require_key(data, "sessions", label="sessions")
    if not isinstance(sessions_raw, list):
        raise StateError("corrupt sessions file")
    sessions: list[SessionRecord] = []
    for item in sessions_raw:
        if not isinstance(item, dict):
            raise StateError("corrupt sessions file")
        sessions.append(
            SessionRecord(
                session_id=_as_str(item, "session_id", label="sessions"),
                agent_id=_as_str(item, "agent_id", label="sessions"),
                issue_number=_as_optional_int(item, "issue_number", label="sessions"),
                pr_number=_as_optional_int(item, "pr_number", label="sessions"),
                working=_as_bool(item, "working", label="sessions"),
                worktree_path=_as_str(item, "worktree_path", label="sessions"),
                started_at=_as_str(item, "started_at", label="sessions"),
            )
        )
    return sessions


def _parse_spawn_failures(data: dict[str, Any]) -> list[SpawnFailureRecord]:
    failures_raw = _require_key(data, "failures", label="spawn_failures")
    if not isinstance(failures_raw, list):
        raise StateError("corrupt spawn_failures file")
    for key in data:
        if key != "failures":
            raise StateError(f"corrupt spawn_failures: unknown key {key}")
    failures: list[SpawnFailureRecord] = []
    for item in failures_raw:
        if not isinstance(item, dict):
            raise StateError("corrupt spawn_failures file")
        failures.append(
            SpawnFailureRecord(
                agent_id=_as_str(item, "agent_id", label="spawn_failures"),
                agent_name=_as_str(item, "agent_name", label="spawn_failures"),
                issue_number=_as_optional_int(item, "issue_number", label="spawn_failures"),
                pr_number=_as_optional_int(item, "pr_number", label="spawn_failures"),
                attempt=_as_int(item, "attempt", label="spawn_failures"),
                released=_as_bool(item, "released", label="spawn_failures"),
                error=_as_str(item, "error", label="spawn_failures"),
                at=_as_str(item, "at", label="spawn_failures"),
            )
        )
    return failures


def _as_str(obj: dict[str, Any], key: str, *, label: str) -> str:
    value = _require_key(obj, key, label=label)
    if not isinstance(value, str):
        raise StateError(f"corrupt {label}: {key} must be a string")
    return value


def _as_int(obj: dict[str, Any], key: str, *, label: str) -> int:
    value = _require_key(obj, key, label=label)
    if type(value) is not int:
        raise StateError(f"corrupt {label}: {key} must be an integer")
    return value


def _as_optional_int(obj: dict[str, Any], key: str, *, label: str) -> int | None:
    if key not in obj:
        raise StateError(f"corrupt {label}: missing {key}")
    value = obj[key]
    if value is None:
        return None
    if type(value) is not int:
        raise StateError(f"corrupt {label}: {key} must be an integer or null")
    return value


def _as_bool(obj: dict[str, Any], key: str, *, label: str) -> bool:
    value = _require_key(obj, key, label=label)
    if not isinstance(value, bool):
        raise StateError(f"corrupt {label}: {key} must be a boolean")
    return value


def _as_str_list(obj: dict[str, Any], key: str, *, label: str) -> list[str]:
    value = _require_key(obj, key, label=label)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise StateError(f"corrupt {label}: {key} must be a list of strings")
    return list(value)
