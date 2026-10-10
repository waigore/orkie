"""Dashboard ThreadingHTTPServer adapter coverage."""

from __future__ import annotations

import threading
import urllib.request
from pathlib import Path

from orkie.acp.fake import FakeAcpClient
from orkie.config import (
    AgentConfig,
    BabysitterConfig,
    Config,
    ConnectorConfig,
    Trigger,
)
from orkie.connectors.fake import FakeConnector
from orkie.connectors.types import OwnerRepo
from orkie.dashboard import bind_dashboard, start_bound_dashboard, stop_dashboard
from orkie.intake import Intake
from orkie.orchestration import Orchestrator, RuntimeContext
from orkie.state import StateStore
from orkie.worktree import WorktreeService


def test_loopback_get_agents(tmp_path: Path) -> None:
    owner = OwnerRepo("acme", "demo")
    config = Config(
        version=1,
        connector=ConnectorConfig(type="github", repo="acme/demo"),
        poll_interval_seconds=60,
        issue_labels=["orkie"],
        max_concurrent_sessions=1,
        dashboard_port=0,
        agents=[
            AgentConfig(
                id="worker",
                name="Worker",
                role="worker",
                command=["opencode", "acp"],
                max_concurrent_sessions=1,
                prompt_template="x",
                triggers=[Trigger(type="any", labels=[])],
            )
        ],
        babysitter=BabysitterConfig(False, None, None, None, None, None),
    )
    store = StateStore(tmp_path)
    store.ensure_layout()
    connector = FakeConnector(owner)
    ctx = RuntimeContext(
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
        start_commit_sha="abc",
        start_branch_or_detached="main",
        dashboard_port=0,
        github_token="tok",
    )
    ctx.orchestrator = Orchestrator(ctx)
    bind_dashboard(ctx)
    server = ctx.dashboard_server
    assert server is not None
    ctx.dashboard_port = server.server_address[1]  # type: ignore[index]
    start_bound_dashboard(ctx)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{ctx.dashboard_port}/agents"
        ) as resp:
            body = resp.read().decode()
        assert "Agents" in body
    finally:
        stop_dashboard(ctx)
