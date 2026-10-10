"""Interrupt and permission grant paths for stdio client."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

from orkie.acp.stdio import StdioAcpClient


def test_spawn_with_permission_and_interrupt(tmp_path: Path) -> None:
    script = tmp_path / "agent.py"
    script.write_text(
        textwrap.dedent(
            """\
            import json, sys

            def read():
                line = sys.stdin.readline()
                return json.loads(line) if line else None

            def write(msg):
                sys.stdout.write(json.dumps(msg) + "\\n")
                sys.stdout.flush()

            # initialize
            msg = read()
            write({
                "jsonrpc": "2.0", "id": msg["id"],
                "result": {
                    "protocolVersion": 2,
                    "capabilities": {"session": {"delete": False}},
                    "authMethods": [],
                },
            })
            # ask permission before session/new completes
            write({
                "jsonrpc": "2.0",
                "id": 99,
                "method": "session/request_permission",
                "params": {
                    "options": [
                        {"optionId": "a", "kind": "allow_once", "title": "Allow"}
                    ]
                },
            })
            # consume grant
            read()
            msg = read()
            write({"jsonrpc": "2.0", "id": msg["id"], "result": {"sessionId": "s"}})
            msg = read()
            write({"jsonrpc": "2.0", "id": msg["id"], "result": {"messageId": "m"}})
            # stay alive until stdin closes / cancel
            while True:
                msg = read()
                if msg is None:
                    break
            """
        ),
        encoding="utf-8",
    )
    cwd = tmp_path / "wt"
    cwd.mkdir()
    logs: list[str] = []

    def append_log(agent_id: str, line: str, **kwargs: object) -> None:
        logs.append(line)

    client = StdioAcpClient()
    handle = client.spawn(
        "sess",
        command=[sys.executable, str(script)],
        worktree_path=cwd,
        agent_id="w",
        prompt="p",
        issue_number=None,
        pr_number=2,
        env_token="secret",
        append_log=append_log,
    )
    assert any("permission grant" in line for line in logs)
    client.interrupt(handle)
    client.end_session(handle)
