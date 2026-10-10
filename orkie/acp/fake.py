"""Controllable AcpClient for offline tests. No real subprocess."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from orkie.acp.framing import AcpError
from orkie.acp.stdio import SessionHandle

AppendLog = Callable[..., None]


@dataclass
class FakeSessionState:
    session_id: str
    alive: bool = True
    interrupted: bool = False
    ended: bool = False
    prompts: list[str] = field(default_factory=list)


class FakeAcpClient:
    def __init__(
        self,
        *,
        fail_spawn: bool = False,
        spawn_error: str = "fake spawn failure",
        session_delete: bool = True,
    ) -> None:
        self.fail_spawn = fail_spawn
        self.spawn_error = spawn_error
        self.session_delete = session_delete
        self.sessions: dict[str, FakeSessionState] = {}
        self.spawn_calls: list[str] = []
        self._handles: dict[str, SessionHandle] = {}

    def spawn(
        self,
        session_id: str,
        *,
        command: list[str],
        worktree_path: Path,
        agent_id: str,
        prompt: str,
        issue_number: int | None,
        pr_number: int | None,
        env_token: str,
        append_log: AppendLog,
    ) -> SessionHandle:
        self.spawn_calls.append(session_id)
        if self.fail_spawn:
            raise AcpError(self.spawn_error)
        # `cat` stays alive until stdin closes — no sleep in tests.
        live = subprocess.Popen(
            ["cat"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        reader = threading.Thread(target=lambda: None, daemon=True)
        handle = SessionHandle(
            session_id=session_id,
            acp_session_id=f"acp-{session_id}",
            agent_id=agent_id,
            issue_number=issue_number,
            pr_number=pr_number,
            worktree_path=worktree_path,
            process=live,
            reader_thread=reader,
            session_delete=self.session_delete,
            _append_log=append_log,
            _token=env_token,
        )
        self.sessions[session_id] = FakeSessionState(session_id=session_id)
        self._handles[session_id] = handle
        append_log(
            agent_id,
            "fake spawn ok",
            session_id=session_id,
            issue_number=issue_number,
            pr_number=pr_number,
        )
        return handle

    def interrupt(self, handle: SessionHandle) -> None:
        state = self.sessions.get(handle.session_id)
        if state is not None:
            state.interrupted = True
        if handle._append_log is not None:
            handle._append_log(
                handle.agent_id,
                "permission cancelled",
                session_id=handle.session_id,
                issue_number=handle.issue_number,
                pr_number=handle.pr_number,
            )

    def prompt(self, handle: SessionHandle, text: str) -> None:
        state = self.sessions.get(handle.session_id)
        if state is not None:
            state.prompts.append(text)

    def end_session(self, handle: SessionHandle) -> None:
        state = self.sessions.get(handle.session_id)
        if state is not None:
            state.ended = True
            state.alive = False
        if handle.process.poll() is None:
            handle.process.kill()
            handle.process.wait(timeout=2)

    def is_alive(self, handle: SessionHandle) -> bool:
        state = self.sessions.get(handle.session_id)
        if state is not None and not state.alive:
            return False
        return handle.process.poll() is None

    def mark_exited(self, session_id: str) -> None:
        state = self.sessions.get(session_id)
        if state is not None:
            state.alive = False
        handle = self._handles.get(session_id)
        if handle is not None and handle.process.poll() is None:
            handle.process.kill()
            handle.process.wait(timeout=2)
