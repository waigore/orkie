"""Interactive shutdown mode selection."""

from __future__ import annotations

import threading
from pathlib import Path
from orkie.acp.fake import FakeAcpClient
from orkie.cli import choose_shutdown_mode
from orkie.config import (
    AgentConfig,
    BabysitterConfig,
    Config,
    ConnectorConfig,
    Trigger,
)
from orkie.connectors.fake import FakeConnector
from orkie.connectors.types import OwnerRepo
from orkie.intake import Intake
from orkie.orchestration import RuntimeContext
from orkie.state import StateStore
from orkie.worktree import WorktreeService
from orkie.acp.stdio import SessionHandle
import subprocess


def _ctx(tmp_path: Path) -> RuntimeContext:
    owner = OwnerRepo("a", "b")
    config = Config(
        version=1,
        connector=ConnectorConfig(type="github", repo="a/b"),
        poll_interval_seconds=60,
        issue_labels=["orkie"],
        max_concurrent_sessions=1,
        dashboard_port=8765,
        agents=[
            AgentConfig(
                id="w",
                name="W",
                role="w",
                command=["x"],
                max_concurrent_sessions=1,
                prompt_template="p",
                triggers=[Trigger(type="any", labels=[])],
            )
        ],
        babysitter=BabysitterConfig(False, None, None, None, None, None),
    )
    store = StateStore(tmp_path)
    store.ensure_layout()
    connector = FakeConnector(owner)
    return RuntimeContext(
        project_root=tmp_path,
        state_root=tmp_path,
        config=config,
        owner_repo=owner,
        connector=connector,
        store=store,
        worktree=WorktreeService(tmp_path, tmp_path),
        intake=Intake(config, connector, store),
        acp_client=FakeAcpClient(),
        shutdown_event=threading.Event(),
        immediate_kill=threading.Event(),
        prompt_requested=threading.Event(),
        cycle_lock=threading.Lock(),
        start_commit_sha="x",
        start_branch_or_detached="main",
        dashboard_port=8765,
        github_token="t",
    )


def test_choose_graceful(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    ctx.prompt_requested.set()
    # Fake a live session entry
    proc = subprocess.Popen(["cat"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    ctx.sessions["s"] = SessionHandle(
        session_id="s",
        acp_session_id="a",
        agent_id="w",
        issue_number=1,
        pr_number=None,
        worktree_path=tmp_path,
        process=proc,
        reader_thread=threading.Thread(target=lambda: None),
        session_delete=False,
    )
    monkeypatch.setattr("orkie.cli.is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "g")
    assert choose_shutdown_mode(ctx) == "graceful"
    proc.kill()
    proc.wait()


def test_choose_normal_letter(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    ctx.prompt_requested.set()
    proc = subprocess.Popen(["cat"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    ctx.sessions["s"] = SessionHandle(
        session_id="s",
        acp_session_id="a",
        agent_id="w",
        issue_number=1,
        pr_number=None,
        worktree_path=tmp_path,
        process=proc,
        reader_thread=threading.Thread(target=lambda: None),
        session_delete=False,
    )
    monkeypatch.setattr("orkie.cli.is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "n")
    assert choose_shutdown_mode(ctx) == "normal"
    proc.kill()
    proc.wait()
