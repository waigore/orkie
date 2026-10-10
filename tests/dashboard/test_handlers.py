"""Dashboard view models, render, and control handlers."""

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
    AgentsView,
    SessionView,
    build_agents_view,
    handle_http,
    render_agents,
    render_index,
)
from orkie.intake import Intake
from orkie.orchestration import Orchestrator, RuntimeContext
from orkie.state import StateStore
from orkie.worktree import WorktreeService


def _ctx(tmp_path: Path) -> RuntimeContext:
    owner = OwnerRepo("acme", "demo")
    config = Config(
        version=1,
        connector=ConnectorConfig(type="github", repo="acme/demo"),
        poll_interval_seconds=60,
        issue_labels=["orkie"],
        max_concurrent_sessions=1,
        dashboard_port=8765,
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
        babysitter=BabysitterConfig(
            enabled=False,
            id=None,
            name=None,
            role=None,
            command=None,
            prompt_template=None,
        ),
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
        dashboard_port=8765,
        github_token="tok",
    )
    ctx.orchestrator = Orchestrator(ctx)
    return ctx


def test_render_index_contains_repo() -> None:
    html = render_index("acme/demo", 8765)
    assert "acme/demo" in html
    assert "/agents" in html


def test_render_agents_empty() -> None:
    view = AgentsView(repo="acme/demo", intake_error=None, sessions=[], failures=[])
    html = render_agents(view)
    assert "No working sessions." in html


def test_build_agents_view_and_kill_404(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    view = build_agents_view(ctx)
    assert view.sessions == []
    status, body, redirect, _ctype = handle_http(
        ctx, method="POST", path="/sessions/missing/kill", referer="/agents"
    )
    assert status == 404
    assert redirect is None


def test_interrupt_unknown_and_shutdown_503(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.shutdown_event.set()
    status, _, _, _ = handle_http(
        ctx, method="POST", path="/sessions/x/interrupt", referer=None
    )
    assert status == 503


def test_get_agents_ok(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    status, body, redirect, ctype = handle_http(
        ctx, method="GET", path="/agents", referer=None
    )
    assert status == 200
    assert redirect is None
    assert "text/html" in ctype
    assert "Agents" in body


def test_static_css_ok(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    status, body, redirect, ctype = handle_http(
        ctx, method="GET", path="/static/dashboard.css", referer=None
    )
    assert status == 200
    assert redirect is None
    assert ctype.startswith("text/css")
    assert isinstance(body, bytes)
    assert b"--accent" in body


def test_static_path_traversal_rejected(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    status, body, redirect, ctype = handle_http(
        ctx, method="GET", path="/static/../dashboard.py", referer=None
    )
    assert status == 404
    assert redirect is None
    assert "text/plain" in ctype
    assert body == "not found"


def test_session_view_in_render() -> None:
    view = AgentsView(
        repo="acme/demo",
        intake_error="boom",
        sessions=[
            SessionView(
                session_id="s1",
                agent_id="worker",
                agent_name="Worker",
                bound_work="issue #1",
                log_lines=["line"],
            )
        ],
        failures=[],
    )
    html = render_agents(view)
    assert "Interrupt" in html
    assert "as of last failed poll" in html
