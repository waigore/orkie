"""Additional CLI coverage for poll loop and signals."""

from __future__ import annotations

import signal
import threading
from pathlib import Path
from unittest import mock

from orkie.acp.fake import FakeAcpClient
from orkie.cli import install_signal_handlers, run_poll_loop, shutdown
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
from orkie.orchestration import Orchestrator, RuntimeContext
from orkie.state import StateStore
from orkie.worktree import WorktreeService


def _ctx(tmp_path: Path) -> RuntimeContext:
    owner = OwnerRepo("a", "b")
    config = Config(
        version=1,
        connector=ConnectorConfig(type="github", repo="a/b"),
        poll_interval_seconds=1,
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
        start_commit_sha="x",
        start_branch_or_detached="main",
        dashboard_port=8765,
        github_token="t",
    )
    ctx.orchestrator = Orchestrator(ctx)
    return ctx


def test_run_poll_loop_exits_on_shutdown(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.shutdown_event.set()
    run_poll_loop(ctx)


def test_install_signal_handlers_sets_flags(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr("orkie.cli.is_interactive", lambda: False)
    install_signal_handlers(ctx)
    handler = signal.getsignal(signal.SIGTERM)
    assert callable(handler)
    handler(signal.SIGTERM, None)  # type: ignore[operator]
    assert ctx.shutdown_event.is_set()


def test_shutdown_graceful(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    # Avoid waiting 20s: set immediate_kill during wait by patching sleep
    with mock.patch("orkie.cli.time.sleep", side_effect=lambda *_: ctx.immediate_kill.set()):
        code = shutdown(ctx, mode="graceful")
    assert code == 0
