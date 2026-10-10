"""Subprocess ACP client over newline-delimited JSON-RPC stdio."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orkie import __version__
from orkie.acp.framing import (
    AcpError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    build_authenticate,
    build_initialize,
    build_permission_cancelled,
    build_permission_selected,
    build_session_cancel,
    build_session_delete,
    build_session_new,
    build_session_prompt,
    choose_permission_option,
    classify_message,
    decode_line,
    encode_message,
    first_auth_method_id,
    parse_permission_options,
)

HANDSHAKE_TIMEOUT_SECONDS = 60
PROCESS_EXIT_WAIT_SECONDS = 5
AppendLog = Callable[..., None]


@dataclass
class SessionHandle:
    session_id: str
    acp_session_id: str
    agent_id: str
    issue_number: int | None
    pr_number: int | None
    worktree_path: Path
    process: subprocess.Popen[bytes]
    reader_thread: threading.Thread
    session_delete: bool
    _stdin_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _pending: dict[int | str, threading.Event] = field(default_factory=dict, repr=False)
    _results: dict[int | str, object] = field(default_factory=dict, repr=False)
    _errors: dict[int | str, object] = field(default_factory=dict, repr=False)
    _pending_permissions: dict[int | str, dict[str, Any]] = field(
        default_factory=dict, repr=False
    )
    _next_id: int = field(default=1, repr=False)
    _closed: bool = field(default=False, repr=False)
    _cancel_permissions: bool = field(default=False, repr=False)
    _append_log: AppendLog | None = field(default=None, repr=False)
    _token: str = field(default="", repr=False)


def _redact(text: str, token: str) -> str:
    if not token:
        return text
    return text.replace(token, "***")


class StdioAcpClient:
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
        env = os.environ.copy()
        env["GITHUB_TOKEN"] = env_token
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(worktree_path),
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            raise AcpError(_redact(str(exc), env_token)) from exc
        handle = SessionHandle(
            session_id=session_id,
            acp_session_id="",
            agent_id=agent_id,
            issue_number=issue_number,
            pr_number=pr_number,
            worktree_path=worktree_path,
            process=process,
            reader_thread=threading.Thread(target=lambda: None, daemon=True),
            session_delete=False,
            _append_log=append_log,
            _token=env_token,
        )
        reader = threading.Thread(
            target=self._reader_loop,
            args=(handle,),
            name=f"acp-reader-{session_id}",
            daemon=True,
        )
        handle.reader_thread = reader
        reader.start()
        stderr_thread = threading.Thread(
            target=self._stderr_loop,
            args=(handle,),
            name=f"acp-stderr-{session_id}",
            daemon=True,
        )
        stderr_thread.start()
        deadline = time.monotonic() + HANDSHAKE_TIMEOUT_SECONDS
        try:
            init_result = self._request(
                handle,
                build_initialize(self._next_id(handle), version=__version__),
                deadline=deadline,
            )
            if not isinstance(init_result, dict):
                raise AcpError("initialize returned unexpected result")
            if init_result.get("protocolVersion") != 2:
                raise AcpError("unsupported ACP protocol version")
            auth_methods = init_result.get("authMethods") or []
            if isinstance(auth_methods, list) and len(auth_methods) > 0:
                method_id = first_auth_method_id(auth_methods)
                if method_id is None:
                    raise AcpError("authMethods advertised but no usable method id")
                self._request(
                    handle,
                    build_authenticate(self._next_id(handle), method_id=method_id),
                    deadline=deadline,
                )
            capabilities = init_result.get("capabilities") or {}
            session_caps = {}
            if isinstance(capabilities, dict):
                session_caps = capabilities.get("session") or {}
            handle.session_delete = bool(
                isinstance(session_caps, dict) and session_caps.get("delete") is True
            )
            new_result = self._request(
                handle,
                build_session_new(
                    self._next_id(handle), cwd=str(worktree_path.resolve())
                ),
                deadline=deadline,
            )
            if not isinstance(new_result, dict) or "sessionId" not in new_result:
                raise AcpError("session/new missing sessionId")
            handle.acp_session_id = str(new_result["sessionId"])
            prompt_result = self._request(
                handle,
                build_session_prompt(
                    self._next_id(handle),
                    session_id=handle.acp_session_id,
                    text=prompt,
                ),
                deadline=deadline,
            )
            if not isinstance(prompt_result, dict) or "messageId" not in prompt_result:
                raise AcpError("session/prompt missing messageId")
        except Exception as exc:
            self._kill_process_group(handle)
            if isinstance(exc, AcpError):
                raise AcpError(_redact(str(exc), env_token)) from exc
            raise AcpError(_redact(str(exc), env_token)) from exc
        return handle

    def interrupt(self, handle: SessionHandle) -> None:
        handle._cancel_permissions = True
        self._write(handle, build_session_cancel(session_id=handle.acp_session_id))
        self._cancel_pending_permissions(handle)

    def prompt(self, handle: SessionHandle, text: str) -> None:
        result = self._request(
            handle,
            build_session_prompt(
                self._next_id(handle),
                session_id=handle.acp_session_id,
                text=text,
            ),
            deadline=time.monotonic() + HANDSHAKE_TIMEOUT_SECONDS,
        )
        if isinstance(result, dict) and "error" in result:
            raise AcpError(_redact(str(result["error"]), handle._token))

    def end_session(self, handle: SessionHandle) -> None:
        if handle._closed:
            return
        handle._closed = True
        handle._cancel_permissions = True
        self._cancel_pending_permissions(handle)
        if handle.session_delete and handle.acp_session_id:
            try:
                self._request(
                    handle,
                    build_session_delete(
                        self._next_id(handle), session_id=handle.acp_session_id
                    ),
                    deadline=time.monotonic() + PROCESS_EXIT_WAIT_SECONDS,
                )
            except AcpError:
                pass
            deadline = time.monotonic() + PROCESS_EXIT_WAIT_SECONDS
            while time.monotonic() < deadline:
                if handle.process.poll() is not None:
                    break
                time.sleep(0.05)
            if handle.process.poll() is None:
                self._kill_process_group(handle)
        else:
            self._kill_process_group(handle)
        handle.reader_thread.join(timeout=2.0)

    def force_kill(self, handle: SessionHandle) -> None:
        """SIGKILL the process group immediately (immediate-kill / second signal)."""
        if handle._closed:
            self._kill_process_group(handle)
            return
        handle._closed = True
        handle._cancel_permissions = True
        self._cancel_pending_permissions(handle)
        self._kill_process_group(handle)
        handle.reader_thread.join(timeout=2.0)

    def is_alive(self, handle: SessionHandle) -> bool:
        return handle.process.poll() is None

    def _next_id(self, handle: SessionHandle) -> int:
        request_id = handle._next_id
        handle._next_id += 1
        return request_id

    def _request(
        self,
        handle: SessionHandle,
        message: dict[str, Any],
        *,
        deadline: float,
    ) -> object:
        request_id = message["id"]
        event = threading.Event()
        handle._pending[request_id] = event
        self._write(handle, message)
        remaining = max(0.0, deadline - time.monotonic())
        if not event.wait(timeout=remaining):
            handle._pending.pop(request_id, None)
            raise AcpError("ACP handshake timeout")
        if request_id in handle._errors:
            error = handle._errors.pop(request_id)
            raise AcpError(_redact(str(error), handle._token))
        return handle._results.pop(request_id, {})

    def _write(self, handle: SessionHandle, message: dict[str, Any]) -> None:
        if handle.process.stdin is None:
            raise AcpError("agent stdin closed")
        payload = encode_message(message)
        with handle._stdin_lock:
            try:
                handle.process.stdin.write(payload)
                handle.process.stdin.flush()
            except OSError as exc:
                raise AcpError(_redact(str(exc), handle._token)) from exc

    def _reader_loop(self, handle: SessionHandle) -> None:
        stdout = handle.process.stdout
        if stdout is None:
            return
        while True:
            line = stdout.readline()
            if not line:
                break
            try:
                data = decode_line(line.rstrip(b"\n"))
                message = classify_message(data)
            except Exception:
                self._log(handle, "ignored invalid ACP line")
                continue
            if isinstance(message, JsonRpcResponse):
                if message.id is None:
                    continue
                if message.error is not None:
                    handle._errors[message.id] = message.error
                else:
                    handle._results[message.id] = message.result
                event = handle._pending.pop(message.id, None)
                if event is not None:
                    event.set()
                continue
            if isinstance(message, (JsonRpcNotification, JsonRpcRequest)):
                method = message.method
                params = message.params
                request_id = message.id if isinstance(message, JsonRpcRequest) else None
                match method:
                    case "session/request_permission":
                        self._handle_permission(handle, request_id, params)
                    case "session/update" | "agent_message" | "agent_message_chunk":
                        self._mirror_update(handle, method, params)
                    case _:
                        self._log(handle, f"ignored ACP method {method}")

    def _stderr_loop(self, handle: SessionHandle) -> None:
        stderr = handle.process.stderr
        if stderr is None:
            return
        while True:
            line = stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            if text:
                self._log(handle, text)

    def _handle_permission(
        self,
        handle: SessionHandle,
        request_id: int | str | None,
        params: dict[str, Any],
    ) -> None:
        if request_id is None:
            return
        if handle._cancel_permissions:
            self._write(handle, build_permission_cancelled(request_id))
            self._log(handle, "permission cancelled")
            return
        options = parse_permission_options(params)
        try:
            chosen = choose_permission_option(options)
        except AcpError as exc:
            self._log(handle, f"permission grant failed: {exc}")
            return
        self._write(handle, build_permission_selected(request_id, chosen.option_id))
        title = chosen.title
        if title:
            line = (
                f"permission grant optionId={chosen.option_id} "
                f"kind={chosen.kind} title={title}"
            )
        else:
            line = f"permission grant optionId={chosen.option_id} kind={chosen.kind}"
        self._log(handle, line)

    def _cancel_pending_permissions(self, handle: SessionHandle) -> None:
        for request_id in list(handle._pending_permissions):
            try:
                self._write(handle, build_permission_cancelled(request_id))
                self._log(handle, "permission cancelled")
            except AcpError:
                pass
            handle._pending_permissions.pop(request_id, None)

    def _mirror_update(
        self, handle: SessionHandle, method: str, params: dict[str, Any]
    ) -> None:
        update = params.get("update") if method == "session/update" else params
        if not isinstance(update, dict):
            text = params.get("text")
            if isinstance(text, str) and text:
                self._log(handle, text)
            return
        content = update.get("content")
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str) and text:
                self._log(handle, text)
                return
        text = update.get("text")
        if isinstance(text, str) and text:
            self._log(handle, text)

    def _log(self, handle: SessionHandle, line: str) -> None:
        if handle._append_log is None:
            return
        handle._append_log(
            handle.agent_id,
            _redact(line, handle._token),
            session_id=handle.session_id,
            issue_number=handle.issue_number,
            pr_number=handle.pr_number,
        )

    def _kill_process_group(self, handle: SessionHandle) -> None:
        process = handle.process
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            print(f"agent process {process.pid} did not exit after SIGKILL", file=sys.stderr)
