"""Per-user state root, process lock, in-memory runtime docs, agent logs."""

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
    """Unusable state (e.g. lock held by another live process)."""


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


_LEGACY_DOCUMENTS = ("claims", "snapshot", "sessions", "spawn_failures")


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
        self._doc_lock = threading.Lock()
        self._claims: list[ClaimRecord] = []
        self._snapshot: Snapshot | None = None
        self._spawn_failures: list[SpawnFailureRecord] = []

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
            data: dict[str, Any] | None
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                parsed = None
            if isinstance(parsed, dict) and type(parsed.get("pid")) is int:
                data = parsed
                pid = data["pid"]
                if _pid_alive(pid):
                    holder_alive = True
            else:
                data = None
            if holder_alive:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                assert data is not None
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
        lock_path = self._state_root / "lock"
        try:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(self._lock_fd)
            self._lock_fd = None

    def ensure_layout(self) -> None:
        self._state_root.mkdir(parents=True, exist_ok=True)
        (self._state_root / "logs").mkdir(exist_ok=True)
        (self._state_root / "worktrees").mkdir(exist_ok=True)
        self.scrub_legacy_documents()

    def scrub_legacy_documents(self) -> None:
        """Remove on-disk documents from older Orkie versions; do not parse them."""
        for name in _LEGACY_DOCUMENTS:
            path = self._state_root / name
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            tmp = self._state_root / f"{name}.tmp"
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def load_snapshot(self) -> Snapshot | None:
        with self._doc_lock:
            return self._snapshot

    def save_snapshot(self, snapshot: Snapshot) -> None:
        with self._doc_lock:
            self._snapshot = snapshot

    def load_claims(self) -> list[ClaimRecord]:
        with self._doc_lock:
            return list(self._claims)

    def save_claims(self, claims: list[ClaimRecord]) -> None:
        with self._doc_lock:
            self._claims = list(claims)

    def load_spawn_failures(self) -> list[SpawnFailureRecord]:
        with self._doc_lock:
            return list(self._spawn_failures)

    def save_spawn_failures(self, failures: list[SpawnFailureRecord]) -> None:
        with self._doc_lock:
            self._spawn_failures = list(failures)

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


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
