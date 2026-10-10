"""Issue view and dashboard bind tests."""

from __future__ import annotations

import threading
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
from orkie.dashboard import (
    bind_dashboard,
    build_issues_view,
    handle_http,
    render_issues,
    start_bound_dashboard,
    stop_dashboard,
)
from orkie.intake import Intake
from orkie.orchestration import Orchestrator, RuntimeContext
from orkie.state import ClaimRecord, Snapshot, SnapshotIssue, StateStore
from orkie.worktree import WorktreeService


def _ctx(tmp_path: Path, port: int = 0) -> RuntimeContext:
    owner = OwnerRepo("acme", "demo")
    config = Config(
        version=1,
        connector=ConnectorConfig(type="github", repo="acme/demo"),
        poll_interval_seconds=60,
        issue_labels=["orkie"],
        max_concurrent_sessions=1,
        dashboard_port=port or 8765,
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
        dashboard_port=port or 8765,
        github_token="tok",
    )
    ctx.orchestrator = Orchestrator(ctx)
    return ctx


def test_issues_view_claimed_unclaimed(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.store.save_snapshot(
        Snapshot(
            fetched_at="t",
            issues=[
                SnapshotIssue(1, "a", "", "u", "open", ["orkie"]),
                SnapshotIssue(2, "b", "", "u", "open", ["orkie"]),
            ],
        )
    )
    ctx.store.save_claims([ClaimRecord("worker", 1, "t")])
    view = build_issues_view(ctx)
    assert len(view.claimed) == 1
    assert len(view.unclaimed) == 1
    html = render_issues(view)
    assert "Claimed" in html
    assert "#1" in html


def test_issues_empty_snapshot(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    view = build_issues_view(ctx)
    html = render_issues(view)
    assert "No intake snapshot yet." in html


def test_get_issues_and_index(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    status, body, _, ctype = handle_http(ctx, method="GET", path="/issues", referer=None)
    assert status == 200
    assert "text/html" in ctype
    assert "Issues" in body
    status, body, _, ctype = handle_http(ctx, method="GET", path="/", referer=None)
    assert status == 200
    assert "Orkie" in body
    assert "/static/dashboard.css" in body


def test_bind_and_stop_dashboard(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, port=0)
    # port 0 lets OS pick a free port — ThreadingHTTPServer supports it
    bind_dashboard(ctx)
    assert ctx.dashboard_server is not None
    # Update port from the bound socket
    server = ctx.dashboard_server
    ctx.dashboard_port = server.server_address[1]  # type: ignore[index]
    start_bound_dashboard(ctx)
    stop_dashboard(ctx)
