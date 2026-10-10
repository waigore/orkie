"""One-cycle orchestration tests with fakes."""

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
from orkie.connectors.types import ConnectorError, Issue, OwnerRepo, PullRequest
from orkie.intake import Intake
from orkie.orchestration import Orchestrator, RuntimeContext
from orkie.state import ClaimRecord, StateStore
from orkie.worktree import WorktreeService


class StubWorktree(WorktreeService):
    def __init__(self, state_root: Path, project_root: Path) -> None:
        super().__init__(state_root, project_root)
        self.created: list[str] = []
        self.removed: list[Path] = []
        self._base = ("abc123", "main")

    def resolve_base(self) -> tuple[str, str]:
        return self._base

    def create(self, session_id: str) -> Path:
        self.created.append(session_id)
        path = self._state_root / "worktrees" / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def remove(self, worktree_path: Path) -> None:
        self.removed.append(worktree_path)

    def remove_leftovers(self) -> None:
        return


def _ctx(
    tmp_path: Path,
    *,
    issues: list[Issue] | None = None,
    pulls: list[PullRequest] | None = None,
    issues_error: Exception | None = None,
    fail_spawn: bool = False,
    babysitter: bool = False,
) -> RuntimeContext:
    owner = OwnerRepo("acme", "demo")
    agents = [
        AgentConfig(
            id="worker",
            name="Worker",
            role="worker",
            command=["opencode", "acp"],
            max_concurrent_sessions=1,
            prompt_template="Issue __ISSUENO__",
            triggers=[Trigger(type="any", labels=[])],
        )
    ]
    baby = BabysitterConfig(
        enabled=babysitter,
        id="sitter" if babysitter else None,
        name="Sitter" if babysitter else None,
        role="babysitter" if babysitter else None,
        command=["opencode", "acp"] if babysitter else None,
        prompt_template="PR __PRNO__" if babysitter else None,
    )
    config = Config(
        version=1,
        connector=ConnectorConfig(type="github", repo="acme/demo"),
        poll_interval_seconds=60,
        issue_labels=["orkie"],
        max_concurrent_sessions=1,
        dashboard_port=8765,
        agents=agents,
        babysitter=baby,
    )
    store = StateStore(tmp_path)
    store.ensure_layout()
    connector = FakeConnector(
        owner,
        issues=issues or [],
        pull_requests=pulls or [],
        issues_error=issues_error,
    )
    worktree = StubWorktree(tmp_path, tmp_path)
    intake = Intake(config, connector, store)
    acp = FakeAcpClient(fail_spawn=fail_spawn)
    ctx = RuntimeContext(
        project_root=tmp_path,
        state_root=tmp_path,
        config=config,
        owner_repo=owner,
        connector=connector,
        store=store,
        worktree=worktree,
        intake=intake,
        acp_client=acp,
        shutdown_event=threading.Event(),
        immediate_kill=threading.Event(),
        prompt_requested=threading.Event(),
        cycle_lock=threading.Lock(),
        start_commit_sha="abc123",
        start_branch_or_detached="main",
        dashboard_port=8765,
        github_token="tok",
    )
    ctx.orchestrator = Orchestrator(ctx)
    return ctx


def test_cycle_claims_and_spawns(tmp_path: Path) -> None:
    issue = Issue(42, "t", "b", "u", "open", ["orkie"])
    ctx = _ctx(tmp_path, issues=[issue])
    assert ctx.orchestrator is not None
    with ctx.cycle_lock:
        ctx.orchestrator.run_cycle()
    claims = ctx.store.load_claims()
    assert len(claims) == 1
    assert claims[0].issue_number == 42
    assert len(ctx.sessions) == 1
    assert ctx.store.load_sessions()[0].working is True


def test_cycle_spawn_failure_keeps_claim(tmp_path: Path) -> None:
    issue = Issue(42, "t", "b", "u", "open", ["orkie"])
    ctx = _ctx(tmp_path, issues=[issue], fail_spawn=True)
    assert ctx.orchestrator is not None
    with ctx.cycle_lock:
        ctx.orchestrator.run_cycle()
    assert ctx.store.load_claims()[0].issue_number == 42
    assert ctx.sessions == {}
    assert ctx.store.load_spawn_failures()[0].attempt == 1


def test_attempt_three_drops_claim(tmp_path: Path) -> None:
    issue = Issue(42, "t", "b", "u", "open", ["orkie"])
    ctx = _ctx(tmp_path, issues=[issue], fail_spawn=True)
    assert ctx.orchestrator is not None
    for _ in range(3):
        with ctx.cycle_lock:
            ctx.orchestrator.run_cycle()
    assert ctx.store.load_claims() == []
    assert any(f.attempt == 3 and f.released for f in ctx.store.load_spawn_failures())


def test_intake_failure_skips_claim_steps(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, issues_error=ConnectorError("down"))
    ctx.store.save_claims(
        [ClaimRecord("worker", 99, "2026-01-01T00:00:00Z")]
    )
    assert ctx.orchestrator is not None
    with ctx.cycle_lock:
        ctx.orchestrator.run_cycle()
    assert ctx.store.load_claims()[0].issue_number == 99
    assert ctx.sessions == {}


def test_drop_claim_when_issue_leaves(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, issues=[])
    ctx.store.save_claims(
        [ClaimRecord("worker", 42, "2026-01-01T00:00:00Z")]
    )
    assert ctx.orchestrator is not None
    with ctx.cycle_lock:
        ctx.orchestrator.run_cycle()
    assert ctx.store.load_claims() == []


def test_babysitter_spawns_selectable_pr(tmp_path: Path) -> None:
    pr = PullRequest(7, "t", "u", "h", "main", False, "dirty")
    ctx = _ctx(tmp_path, pulls=[pr], babysitter=True)
    assert ctx.orchestrator is not None
    with ctx.cycle_lock:
        ctx.orchestrator.run_cycle()
    assert len(ctx.sessions) == 1
    handle = next(iter(ctx.sessions.values()))
    assert handle.pr_number == 7


def test_exit_drops_claim_while_running(tmp_path: Path) -> None:
    issue = Issue(42, "t", "b", "u", "open", ["orkie"])
    ctx = _ctx(tmp_path, issues=[issue])
    assert ctx.orchestrator is not None
    with ctx.cycle_lock:
        ctx.orchestrator.run_cycle()
    session_id = next(iter(ctx.sessions))
    assert isinstance(ctx.acp_client, FakeAcpClient)
    ctx.acp_client.mark_exited(session_id)
    # Reconcile only — a full cycle would reclaim the still-eligible issue.
    ctx.orchestrator._reconcile_exits()
    assert session_id not in ctx.sessions
    assert ctx.store.load_claims() == []


def test_kill_session_drops_claim(tmp_path: Path) -> None:
    issue = Issue(42, "t", "b", "u", "open", ["orkie"])
    ctx = _ctx(tmp_path, issues=[issue])
    assert ctx.orchestrator is not None
    with ctx.cycle_lock:
        ctx.orchestrator.run_cycle()
    session_id = next(iter(ctx.sessions))
    ctx.orchestrator.kill_session(session_id)
    assert session_id not in ctx.sessions
    assert ctx.store.load_claims() == []


def test_interrupt_session_keeps_claim(tmp_path: Path) -> None:
    issue = Issue(42, "t", "b", "u", "open", ["orkie"])
    ctx = _ctx(tmp_path, issues=[issue])
    assert ctx.orchestrator is not None
    with ctx.cycle_lock:
        ctx.orchestrator.run_cycle()
    session_id = next(iter(ctx.sessions))
    ctx.orchestrator.interrupt_session(session_id)
    assert session_id in ctx.sessions
    assert ctx.store.load_claims()
