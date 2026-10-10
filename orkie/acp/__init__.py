"""ACP client protocol, SessionHandle, and re-exports."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from orkie.acp.framing import AcpError, PermissionOption, choose_permission_option
from orkie.acp.stdio import SessionHandle, StdioAcpClient

__all__ = [
    "AcpClient",
    "AcpError",
    "PermissionOption",
    "SessionHandle",
    "StdioAcpClient",
    "choose_permission_option",
]

AppendLog = Callable[..., None]


class AcpClient(Protocol):
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
    ) -> SessionHandle: ...

    def interrupt(self, handle: SessionHandle) -> None: ...

    def prompt(self, handle: SessionHandle, text: str) -> None: ...

    def end_session(self, handle: SessionHandle) -> None: ...

    def force_kill(self, handle: SessionHandle) -> None: ...

    def is_alive(self, handle: SessionHandle) -> bool: ...
