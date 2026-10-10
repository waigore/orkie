"""Stdio ACP client against a tiny fake agent script."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from orkie.acp.framing import AcpError
from orkie.acp.stdio import StdioAcpClient


def _write_fake_agent(
    path: Path,
    *,
    auth_methods: str = "[]",
    auth_fail: bool = False,
) -> Path:
    auth_fail_block = (
        """\
                elif method == "authenticate":
                    write({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32000, "message": "auth failed"},
                    })
"""
        if auth_fail
        else """\
                elif method == "authenticate":
                    write({"jsonrpc": "2.0", "id": req_id, "result": {}})
"""
    )
    script = path / "fake_agent.py"
    script.write_text(
        textwrap.dedent(
            f"""\
            import json
            import sys

            def read():
                line = sys.stdin.readline()
                if not line:
                    return None
                return json.loads(line)

            def write(msg):
                sys.stdout.write(json.dumps(msg) + "\\n")
                sys.stdout.flush()

            while True:
                msg = read()
                if msg is None:
                    break
                method = msg.get("method")
                req_id = msg.get("id")
                if method == "initialize":
                    write({{
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {{
                            "protocolVersion": 2,
                            "capabilities": {{"session": {{"delete": True}}}},
                            "authMethods": {auth_methods},
                        }},
                    }})
{auth_fail_block}\
                elif method == "session/new":
                    write({{
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {{"sessionId": "acp-1"}},
                    }})
                elif method == "session/prompt":
                    write({{
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {{"messageId": "m1"}},
                    }})
                elif method == "session/delete":
                    write({{"jsonrpc": "2.0", "id": req_id, "result": {{}}}})
                    break
            """
        ),
        encoding="utf-8",
    )
    return script


def _spawn(client: StdioAcpClient, script: Path, cwd: Path) -> object:
    return client.spawn(
        "sess-1",
        command=[sys.executable, str(script)],
        worktree_path=cwd,
        agent_id="worker",
        prompt="hello",
        issue_number=1,
        pr_number=None,
        env_token="tok",
        append_log=lambda *a, **k: None,
    )


def test_spawn_prompt_and_end(tmp_path: Path) -> None:
    script = _write_fake_agent(tmp_path)
    cwd = tmp_path / "wt"
    cwd.mkdir()
    client = StdioAcpClient()
    handle = _spawn(client, script, cwd)
    assert handle.acp_session_id == "acp-1"
    assert client.is_alive(handle)
    client.end_session(handle)
    assert not client.is_alive(handle)


def test_spawn_authenticates_when_auth_methods_advertised(tmp_path: Path) -> None:
    script = _write_fake_agent(
        tmp_path, auth_methods='[{"id": "cursor_login"}]'
    )
    cwd = tmp_path / "wt"
    cwd.mkdir()
    client = StdioAcpClient()
    handle = _spawn(client, script, cwd)
    assert handle.acp_session_id == "acp-1"
    client.end_session(handle)


def test_spawn_fails_when_authenticate_errors(tmp_path: Path) -> None:
    script = _write_fake_agent(
        tmp_path,
        auth_methods='[{"id": "cursor_login"}]',
        auth_fail=True,
    )
    cwd = tmp_path / "wt"
    cwd.mkdir()
    client = StdioAcpClient()
    with pytest.raises(AcpError, match="auth failed"):
        _spawn(client, script, cwd)
