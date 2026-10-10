"""Stdio ACP client against a tiny fake agent script."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

from orkie.acp.stdio import StdioAcpClient


def _write_fake_agent(path: Path) -> Path:
    script = path / "fake_agent.py"
    script.write_text(
        textwrap.dedent(
            """\
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
                    write({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": 2,
                            "capabilities": {"session": {"delete": True}},
                            "authMethods": [],
                        },
                    })
                elif method == "session/new":
                    write({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"sessionId": "acp-1"},
                    })
                elif method == "session/prompt":
                    write({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"messageId": "m1"},
                    })
                elif method == "session/delete":
                    write({"jsonrpc": "2.0", "id": req_id, "result": {}})
                    break
            """
        ),
        encoding="utf-8",
    )
    return script


def test_spawn_prompt_and_end(tmp_path: Path) -> None:
    script = _write_fake_agent(tmp_path)
    cwd = tmp_path / "wt"
    cwd.mkdir()
    logs: list[str] = []

    def append_log(agent_id: str, line: str, **kwargs: object) -> None:
        logs.append(line)

    client = StdioAcpClient()
    handle = client.spawn(
        "sess-1",
        command=[sys.executable, str(script)],
        worktree_path=cwd,
        agent_id="worker",
        prompt="hello",
        issue_number=1,
        pr_number=None,
        env_token="tok",
        append_log=append_log,
    )
    assert handle.acp_session_id == "acp-1"
    assert client.is_alive(handle)
    client.end_session(handle)
    assert not client.is_alive(handle)
