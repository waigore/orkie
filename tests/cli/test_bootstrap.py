"""Bootstrap sequence tests with fakes."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from orkie.cli import (
    choose_shutdown_mode,
    resolve_project_root,
    run_bootstrap,
    shutdown,
)
from orkie.config import DEFAULT_SCAFFOLD, write_default_scaffold
from orkie.connectors.types import OwnerRepo, ProbeResult


def _git_project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    write_default_scaffold(project)
    # Point connector.repo so resolve does not need remotes.
    text = (project / ".orkie" / "config.yaml").read_text(encoding="utf-8")
    text = text.replace(
        "connector:\n  type: github\n",
        "connector:\n  type: github\n  repo: acme/demo\n",
    )
    (project / ".orkie" / "config.yaml").write_text(text, encoding="utf-8")
    return project


def test_resolve_project_root_rejects_non_git(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        resolve_project_root(tmp_path)


def test_run_bootstrap_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _git_project(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setattr("orkie.cli.is_interactive", lambda: False)
    monkeypatch.setattr(
        "orkie.cli.default_state_root",
        lambda owner, repo, home=None: home / "state" if False else tmp_path / "state",
    )
    monkeypatch.setattr(
        "orkie.worktree.WorktreeService.resolve_base",
        lambda self: ("abc", "main"),
    )
    monkeypatch.setattr(
        "orkie.worktree.WorktreeService.remove_leftovers",
        lambda self: None,
    )
    monkeypatch.setattr(
        "orkie.cli.build_connector",
        lambda config, token, owner_repo: mock.Mock(
            probe_privileges=lambda required: ProbeResult(set(), set()),
            repository_id=lambda: owner_repo,
        ),
    )
    monkeypatch.setattr("orkie.cli.bind_dashboard", lambda ctx: None)
    ctx = run_bootstrap(project, port=9876)
    assert ctx.owner_repo == OwnerRepo("acme", "demo")
    assert ctx.orchestrator is not None
    monkeypatch.setattr("orkie.cli.stop_dashboard", lambda ctx: None)
    code = shutdown(ctx, mode="normal")
    assert code == 0


def test_choose_shutdown_normal_without_prompt(tmp_path: Path) -> None:
    project = _git_project(tmp_path)
    # Minimal context via bootstrap pieces is heavy; build a tiny stub.
    from orkie.acp.fake import FakeAcpClient
    from orkie.config import load_config
    from orkie.connectors.fake import FakeConnector
    from orkie.intake import Intake
    from orkie.orchestration import RuntimeContext
    from orkie.state import StateStore
    from orkie.worktree import WorktreeService
    import threading

    config = load_config(project)
    owner = OwnerRepo("acme", "demo")
    store = StateStore(tmp_path / "st")
    store.ensure_layout()
    connector = FakeConnector(owner)
    ctx = RuntimeContext(
        project_root=project,
        state_root=tmp_path / "st",
        config=config,
        owner_repo=owner,
        connector=connector,
        store=store,
        worktree=WorktreeService(tmp_path / "st", project),
        intake=Intake(config, connector, store),
        acp_client=FakeAcpClient(),
        shutdown_event=threading.Event(),
        immediate_kill=threading.Event(),
        prompt_requested=threading.Event(),
        cycle_lock=threading.Lock(),
        start_commit_sha="a",
        start_branch_or_detached="main",
        dashboard_port=1,
        github_token="t",
    )
    assert choose_shutdown_mode(ctx) == "normal"


def test_scaffold_constant_loads() -> None:
    assert "version: 1" in DEFAULT_SCAFFOLD
