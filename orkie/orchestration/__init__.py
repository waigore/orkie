"""Orchestrator and the poll-cycle procedure."""

from __future__ import annotations

import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from orkie.acp import AcpClient, AcpError, SessionHandle
from orkie.config import AgentConfig, Config, substitute_prompt
from orkie.connectors import Connector
from orkie.connectors.types import Issue, OwnerRepo
from orkie.intake import Intake
from orkie.orchestration.decide import (
    ExitWork,
    SpawnWork,
    cap_room,
    claim_still_applies,
    clear_spawn_failures,
    clear_unselectable_pr_failures,
    pick_agent_for_issue,
    plan_exits,
    plan_fulfillment,
    plan_new_claims,
    record_spawn_failure,
    select_babysitter,
)
from orkie.state import ClaimRecord, SessionRecord, StateStore, utc_now_iso
from orkie.worktree import WorktreeError, WorktreeService

if TYPE_CHECKING:
    pass

WRAP_UP_PROMPT = (
    "Wrap up your current work now. Commit or stash local changes, and open a "
    "pull request if the work is ready to share. Do not start new work."
)


@dataclass
class RuntimeContext:
    project_root: Path
    state_root: Path
    config: Config
    owner_repo: OwnerRepo
    connector: Connector
    store: StateStore
    worktree: WorktreeService
    intake: Intake
    acp_client: AcpClient
    shutdown_event: threading.Event
    immediate_kill: threading.Event
    prompt_requested: threading.Event
    cycle_lock: threading.Lock
    start_commit_sha: str
    start_branch_or_detached: str
    dashboard_port: int
    github_token: str
    sessions: dict[str, SessionHandle] = field(default_factory=dict)
    orchestrator: Orchestrator | None = None
    dashboard_server: object | None = None
    dashboard_thread: threading.Thread | None = None


class Orchestrator:
    def __init__(self, ctx: RuntimeContext) -> None:
        self._ctx = ctx

    def run_cycle(self) -> None:
        ctx = self._ctx
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            return
        # Step 2: intake
        intake_result = ctx.intake.fetch_and_diff()
        if not intake_result.ok and intake_result.error:
            print(f"intake fetch failed: {intake_result.error}", file=sys.stderr)
        # Step 3: observe ACP exits
        self._reconcile_exits()
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            return
        if intake_result.ok:
            # Steps 4–7
            self._drop_stale_claims(intake_result.intake_issues)
            working = self._working_issue_sessions()
            failures = ctx.store.load_spawn_failures()
            claims = ctx.store.load_claims()
            fulfill = plan_fulfillment(
                claims,
                intake_result.intake_issues,
                ctx.config.agents,
                working,
                failures,
                global_max=ctx.config.max_concurrent_sessions,
            )
            for work in fulfill:
                if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
                    return
                if self._global_issue_room() <= 0:
                    break
                if self._cap_room_for(work.agent) <= 0:
                    continue
                self._spawn_issue_work(work)
            working = self._working_issue_sessions()
            failures = ctx.store.load_spawn_failures()
            claims = ctx.store.load_claims()
            new_claims = plan_new_claims(
                intake_result.intake_issues,
                claims,
                ctx.config.agents,
                working,
                failures,
                global_max=ctx.config.max_concurrent_sessions,
            )
            for work in new_claims:
                if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
                    return
                if self._global_issue_room() <= 0:
                    break
                agent = pick_agent_for_issue(
                    work.issue,
                    ctx.config.agents,
                    self._working_issue_sessions(),
                    global_max=ctx.config.max_concurrent_sessions,
                )
                if agent is None:
                    continue
                self._spawn_issue_work(
                    SpawnWork(issue=work.issue, agent=agent, claim=None),
                    write_claim=True,
                )
        # Step 8: babysitter
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            return
        self._run_babysitter()

    def interrupt_session(self, session_id: str) -> None:
        ctx = self._ctx
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            raise RuntimeError("shutting down")
        handle = ctx.sessions.get(session_id)
        if handle is None:
            raise KeyError(session_id)
        ctx.acp_client.interrupt(handle)

    def kill_session(self, session_id: str) -> None:
        ctx = self._ctx
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            raise RuntimeError("shutting down")
        handle = ctx.sessions.get(session_id)
        if handle is None:
            raise KeyError(session_id)
        ctx.acp_client.end_session(handle)
        self._remove_session_record(session_id)
        if handle.issue_number is not None:
            self._drop_claim(handle.issue_number)
        ctx.worktree.remove(handle.worktree_path)
        ctx.sessions.pop(session_id, None)

    def request_shutdown(self) -> None:
        self._ctx.shutdown_event.set()

    def wrap_up_sessions(self) -> None:
        ctx = self._ctx
        for session_id, handle in list(ctx.sessions.items()):
            try:
                ctx.acp_client.interrupt(handle)
                ctx.acp_client.prompt(handle, WRAP_UP_PROMPT)
            except AcpError:
                ctx.acp_client.end_session(handle)
                ctx.sessions.pop(session_id, None)

    def end_all_sessions(self) -> None:
        ctx = self._ctx
        for session_id, handle in list(ctx.sessions.items()):
            ctx.acp_client.end_session(handle)
            ctx.sessions.pop(session_id, None)

    def remove_all_worktrees(self) -> None:
        ctx = self._ctx
        root = ctx.state_root / "worktrees"
        if not root.exists():
            return
        for child in root.iterdir():
            if child.is_dir():
                ctx.worktree.remove(child)

    def _reconcile_exits(self) -> None:
        ctx = self._ctx
        records = self._session_records_from_live()
        alive_ids = {
            session_id
            for session_id, handle in ctx.sessions.items()
            if ctx.acp_client.is_alive(handle)
        }
        shutdown_started = ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set()
        for exit_work in plan_exits(
            records, alive_ids=alive_ids, shutdown_started=shutdown_started
        ):
            self._apply_exit(exit_work)

    def _apply_exit(self, exit_work: ExitWork) -> None:
        ctx = self._ctx
        handle = ctx.sessions.pop(exit_work.session_id, None)
        if handle is not None and ctx.acp_client.is_alive(handle):
            ctx.acp_client.end_session(handle)
        self._remove_session_record(exit_work.session_id)
        if exit_work.drop_claim and exit_work.issue_number is not None:
            self._drop_claim(exit_work.issue_number)
        if exit_work.worktree_path:
            ctx.worktree.remove(Path(exit_work.worktree_path))

    def _drop_stale_claims(self, intake_issues: list[Issue]) -> None:
        ctx = self._ctx
        for claim in list(ctx.store.load_claims()):
            if claim_still_applies(claim, intake_issues, ctx.config.agents):
                continue
            for session_id, handle in list(ctx.sessions.items()):
                if handle.issue_number == claim.issue_number:
                    ctx.acp_client.end_session(handle)
                    self._remove_session_record(session_id)
                    ctx.worktree.remove(handle.worktree_path)
                    ctx.sessions.pop(session_id, None)
            self._drop_claim(claim.issue_number)

    def _spawn_issue_work(self, work: SpawnWork, *, write_claim: bool = False) -> None:
        ctx = self._ctx
        issue = work.issue
        agent = work.agent
        if write_claim:
            claims = ctx.store.load_claims()
            claim = ClaimRecord(
                agent_id=agent.id,
                issue_number=issue.number,
                claimed_at=utc_now_iso(),
            )
            ctx.store.save_claims(claims + [claim])
        session_id = str(uuid.uuid4())
        try:
            worktree_path = ctx.worktree.create(session_id)
        except WorktreeError as exc:
            self._record_failure(
                agent_id=agent.id,
                agent_name=agent.name,
                issue_number=issue.number,
                pr_number=None,
                error=str(exc),
            )
            return
        self._refresh_start_checkout()
        prompt = substitute_prompt(
            agent.prompt_template,
            session_id=session_id,
            agent_id=agent.id,
            agent_name=agent.name,
            repo=f"{ctx.owner_repo.owner}/{ctx.owner_repo.name}",
            issue=issue,
            pr=None,
        )
        try:
            handle = ctx.acp_client.spawn(
                session_id,
                command=list(agent.command),
                worktree_path=worktree_path,
                agent_id=agent.id,
                prompt=prompt,
                issue_number=issue.number,
                pr_number=None,
                env_token=ctx.github_token,
                append_log=ctx.store.append_log,
            )
        except AcpError as exc:
            ctx.worktree.remove(worktree_path)
            self._record_failure(
                agent_id=agent.id,
                agent_name=agent.name,
                issue_number=issue.number,
                pr_number=None,
                error=str(exc),
            )
            return
        ctx.sessions[session_id] = handle
        failures = clear_spawn_failures(
            ctx.store.load_spawn_failures(), issue_number=issue.number
        )
        ctx.store.save_spawn_failures(failures)

    def _run_babysitter(self) -> None:
        ctx = self._ctx
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            return
        babysitter = ctx.config.babysitter
        if not babysitter.enabled:
            return
        if babysitter.id is None or babysitter.command is None or babysitter.prompt_template is None:
            return
        if any(handle.pr_number is not None for handle in ctx.sessions.values()):
            return
        try:
            pull_requests = ctx.connector.list_open_pull_requests()
        except Exception as exc:  # noqa: BLE001
            print(f"PR fetch failed: {exc}", file=sys.stderr)
            return
        failures = clear_unselectable_pr_failures(
            ctx.store.load_spawn_failures(), pull_requests
        )
        if failures != ctx.store.load_spawn_failures():
            ctx.store.save_spawn_failures(failures)
        pr = select_babysitter(
            pull_requests,
            failures,
            babysitter_working=False,
        )
        if pr is None:
            return
        session_id = str(uuid.uuid4())
        try:
            worktree_path = ctx.worktree.create(session_id)
        except WorktreeError as exc:
            self._record_failure(
                agent_id=babysitter.id,
                agent_name=babysitter.name or babysitter.id,
                issue_number=None,
                pr_number=pr.number,
                error=str(exc),
            )
            return
        self._refresh_start_checkout()
        prompt = substitute_prompt(
            babysitter.prompt_template,
            session_id=session_id,
            agent_id=babysitter.id,
            agent_name=babysitter.name or babysitter.id,
            repo=f"{ctx.owner_repo.owner}/{ctx.owner_repo.name}",
            issue=None,
            pr=pr,
        )
        try:
            handle = ctx.acp_client.spawn(
                session_id,
                command=list(babysitter.command),
                worktree_path=worktree_path,
                agent_id=babysitter.id,
                prompt=prompt,
                issue_number=None,
                pr_number=pr.number,
                env_token=ctx.github_token,
                append_log=ctx.store.append_log,
            )
        except AcpError as exc:
            ctx.worktree.remove(worktree_path)
            self._record_failure(
                agent_id=babysitter.id,
                agent_name=babysitter.name or babysitter.id,
                issue_number=None,
                pr_number=pr.number,
                error=str(exc),
            )
            return
        ctx.sessions[session_id] = handle
        cleared = clear_spawn_failures(
            ctx.store.load_spawn_failures(), pr_number=pr.number
        )
        ctx.store.save_spawn_failures(cleared)

    def _record_failure(
        self,
        *,
        agent_id: str,
        agent_name: str,
        issue_number: int | None,
        pr_number: int | None,
        error: str,
    ) -> None:
        ctx = self._ctx
        update = record_spawn_failure(
            ctx.store.load_spawn_failures(),
            agent_id=agent_id,
            agent_name=agent_name,
            issue_number=issue_number,
            pr_number=pr_number,
            error=error,
            at=utc_now_iso(),
        )
        ctx.store.save_spawn_failures(update.failures)
        if update.drop_claim and issue_number is not None:
            self._drop_claim(issue_number)
        if update.warn and issue_number is not None:
            print(
                f"warning: dropped local claim for issue #{issue_number} "
                f"after three spawn failures for agent {agent_name} ({agent_id})",
                file=sys.stderr,
            )

    def _refresh_start_checkout(self) -> None:
        sha, branch = self._ctx.worktree.resolve_base()
        self._ctx.start_commit_sha = sha
        self._ctx.start_branch_or_detached = branch

    def _drop_claim(self, issue_number: int) -> None:
        claims = [
            claim
            for claim in self._ctx.store.load_claims()
            if claim.issue_number != issue_number
        ]
        self._ctx.store.save_claims(claims)

    def _remove_session_record(self, session_id: str) -> None:
        self._ctx.sessions.pop(session_id, None)

    def _working_issue_sessions(self) -> list[SessionRecord]:
        return [
            SessionRecord(
                session_id=session_id,
                agent_id=handle.agent_id,
                issue_number=handle.issue_number,
                pr_number=handle.pr_number,
                working=True,
                worktree_path=str(handle.worktree_path),
                started_at="",
            )
            for session_id, handle in self._ctx.sessions.items()
            if handle.issue_number is not None
            and self._ctx.acp_client.is_alive(handle)
        ]

    def _session_records_from_live(self) -> list[SessionRecord]:
        return [
            SessionRecord(
                session_id=session_id,
                agent_id=handle.agent_id,
                issue_number=handle.issue_number,
                pr_number=handle.pr_number,
                working=True,
                worktree_path=str(handle.worktree_path),
                started_at="",
            )
            for session_id, handle in self._ctx.sessions.items()
        ]

    def _cap_room_for(self, agent: AgentConfig) -> int:
        return cap_room(
            agent,
            self._working_issue_sessions(),
            global_max=self._ctx.config.max_concurrent_sessions,
        )

    def _global_issue_room(self) -> int:
        working = self._working_issue_sessions()
        return max(0, self._ctx.config.max_concurrent_sessions - len(working))

