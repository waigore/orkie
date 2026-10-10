"""CLI parse_args and bootstrap smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from orkie.cli import is_interactive, main, parse_args, wait_poll_interval
from orkie.orchestration import RuntimeContext
import threading


def test_parse_args_project_and_port() -> None:
    ns = parse_args(["/tmp/proj", "--port", "9000"])
    assert ns.project == Path("/tmp/proj")
    assert ns.port == 9000


def test_parse_args_defaults() -> None:
    ns = parse_args([])
    assert ns.project is None
    assert ns.port is None


def test_is_interactive_false_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert is_interactive() is False


def test_main_noninteractive_missing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setattr("orkie.cli.is_interactive", lambda: False)
    code = main([str(project)])
    assert code != 0


def test_wait_poll_interval_wakes_on_shutdown() -> None:
    from orkie.config import (
        AgentConfig,
        BabysitterConfig,
        Config,
        ConnectorConfig,
        Trigger,
    )
    from orkie.connectors.fake import FakeConnector
    from orkie.connectors.types import OwnerRepo
    from orkie.acp.fake import FakeAcpClient
    from orkie.intake import Intake
    from orkie.state import StateStore
    from orkie.worktree import WorktreeService

    owner = OwnerRepo("a", "b")
    config = Config(
        version=1,
        connector=ConnectorConfig(type="github", repo="a/b"),
        poll_interval_seconds=30,
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
    store = StateStore(Path("/tmp"))
    connector = FakeConnector(owner)
    shutdown = threading.Event()
    shutdown.set()
    ctx = RuntimeContext(
        project_root=Path("."),
        state_root=Path("."),
        config=config,
        owner_repo=owner,
        connector=connector,
        store=store,
        worktree=WorktreeService(Path("."), Path(".")),
        intake=Intake(config, connector, store),
        acp_client=FakeAcpClient(),
        shutdown_event=shutdown,
        immediate_kill=threading.Event(),
        prompt_requested=threading.Event(),
        cycle_lock=threading.Lock(),
        start_commit_sha="x",
        start_branch_or_detached="main",
        dashboard_port=8765,
        github_token="",
    )
    wait_poll_interval(ctx)
