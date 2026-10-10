"""Pure claim, cap, strike, and babysitter decisions."""

from __future__ import annotations

from dataclasses import dataclass

from orkie.config import AgentConfig
from orkie.connectors.types import Issue, PullRequest  # PullRequest: babysitter select
from orkie.state import ClaimRecord, SessionRecord, SpawnFailureRecord


@dataclass(frozen=True, slots=True)
class SpawnWork:
    issue: Issue
    agent: AgentConfig
    claim: ClaimRecord | None


@dataclass(frozen=True, slots=True)
class ExitWork:
    session_id: str
    drop_claim: bool
    issue_number: int | None
    pr_number: int | None
    worktree_path: str


@dataclass(frozen=True, slots=True)
class StrikeUpdate:
    failures: list[SpawnFailureRecord]
    drop_claim: bool
    warn: bool


def agent_matches(agent: AgentConfig, issue: Issue) -> bool:
    for trigger in agent.triggers:
        match trigger.type:
            case "any":
                return True
            case "labels":
                issue_labels = set(issue.labels)
                if all(label in issue_labels for label in trigger.labels):
                    return True
    return False


def claim_still_applies(
    claim: ClaimRecord, intake: list[Issue], agents: list[AgentConfig]
) -> bool:
    issue = _issue_by_number(intake, claim.issue_number)
    if issue is None:
        return False
    agent = _agent_by_id(agents, claim.agent_id)
    if agent is None:
        return False
    return agent_matches(agent, issue)


def cap_room(
    agent: AgentConfig,
    working_issue_sessions: list[SessionRecord],
    *,
    global_max: int,
) -> int:
    working_agent = sum(
        1 for session in working_issue_sessions if session.agent_id == agent.id
    )
    working_all = len(working_issue_sessions)
    agent_room = agent.max_concurrent_sessions - working_agent
    global_room = global_max - working_all
    return max(0, min(agent_room, global_room))


def blocked_by_spawn_failures(
    failures: list[SpawnFailureRecord],
    *,
    issue_number: int | None = None,
    pr_number: int | None = None,
) -> bool:
    for failure in failures:
        if issue_number is not None and failure.issue_number == issue_number:
            if failure.attempt == 3:
                return True
        if pr_number is not None and failure.pr_number == pr_number:
            if failure.attempt == 3:
                return True
    return False


def plan_fulfillment(
    claims: list[ClaimRecord],
    intake: list[Issue],
    agents: list[AgentConfig],
    working_issue_sessions: list[SessionRecord],
    failures: list[SpawnFailureRecord],
    *,
    global_max: int,
) -> list[SpawnWork]:
    working_issues = {
        session.issue_number
        for session in working_issue_sessions
        if session.issue_number is not None
    }
    planned: list[SpawnWork] = []
    # Track projected working sessions as we walk candidates.
    projected = list(working_issue_sessions)
    for claim in sorted(claims, key=lambda item: item.issue_number):
        if claim.issue_number in working_issues:
            continue
        if not claim_still_applies(claim, intake, agents):
            continue
        if blocked_by_spawn_failures(failures, issue_number=claim.issue_number):
            continue
        agent = _agent_by_id(agents, claim.agent_id)
        if agent is None:
            continue
        if cap_room(agent, projected, global_max=global_max) <= 0:
            continue
        issue = _issue_by_number(intake, claim.issue_number)
        if issue is None:
            continue
        planned.append(SpawnWork(issue=issue, agent=agent, claim=claim))
        projected.append(
            SessionRecord(
                session_id="",
                agent_id=agent.id,
                issue_number=claim.issue_number,
                pr_number=None,
                working=True,
                worktree_path="",
                started_at="",
            )
        )
    return planned


def plan_new_claims(
    intake: list[Issue],
    claims: list[ClaimRecord],
    agents: list[AgentConfig],
    working_issue_sessions: list[SessionRecord],
    failures: list[SpawnFailureRecord],
    *,
    global_max: int,
) -> list[SpawnWork]:
    claimed = {claim.issue_number for claim in claims}
    working_issues = {
        session.issue_number
        for session in working_issue_sessions
        if session.issue_number is not None
    }
    planned: list[SpawnWork] = []
    projected = list(working_issue_sessions)
    for issue in sorted(intake, key=lambda item: item.number):
        if issue.number in claimed or issue.number in working_issues:
            continue
        if blocked_by_spawn_failures(failures, issue_number=issue.number):
            continue
        matching = [agent for agent in agents if agent_matches(agent, issue)]
        if not matching:
            continue
        chosen: AgentConfig | None = None
        for agent in matching:
            if cap_room(agent, projected, global_max=global_max) > 0:
                chosen = agent
                break
        if chosen is None:
            break
        planned.append(SpawnWork(issue=issue, agent=chosen, claim=None))
        projected.append(
            SessionRecord(
                session_id="",
                agent_id=chosen.id,
                issue_number=issue.number,
                pr_number=None,
                working=True,
                worktree_path="",
                started_at="",
            )
        )
    return planned


def plan_exits(
    sessions: list[SessionRecord],
    *,
    alive_ids: set[str],
    shutdown_started: bool,
) -> list[ExitWork]:
    exits: list[ExitWork] = []
    for session in sessions:
        if session.session_id in alive_ids:
            continue
        drop_claim = (
            not shutdown_started
            and session.issue_number is not None
            and session.pr_number is None
        )
        exits.append(
            ExitWork(
                session_id=session.session_id,
                drop_claim=drop_claim,
                issue_number=session.issue_number,
                pr_number=session.pr_number,
                worktree_path=session.worktree_path,
            )
        )
    return exits


def select_babysitter(
    pull_requests: list[PullRequest],
    failures: list[SpawnFailureRecord],
    *,
    babysitter_working: bool,
) -> PullRequest | None:
    if babysitter_working:
        return None
    selectable: list[PullRequest] = []
    for pr in pull_requests:
        if pr.draft:
            continue
        if pr.mergeable_state in {"", "unknown"}:
            continue
        if pr.mergeable_state == "clean":
            continue
        if blocked_by_spawn_failures(failures, pr_number=pr.number):
            continue
        selectable.append(pr)
    if not selectable:
        return None
    return min(selectable, key=lambda item: item.number)


def record_spawn_failure(
    failures: list[SpawnFailureRecord],
    *,
    agent_id: str,
    agent_name: str,
    issue_number: int | None,
    pr_number: int | None,
    error: str,
    at: str,
) -> StrikeUpdate:
    prior = [
        failure
        for failure in failures
        if (issue_number is not None and failure.issue_number == issue_number)
        or (pr_number is not None and failure.pr_number == pr_number)
    ]
    next_attempt = len(prior) + 1
    if next_attempt > 3:
        return StrikeUpdate(failures=list(failures), drop_claim=False, warn=False)
    released = next_attempt == 3 and issue_number is not None
    warn = released
    drop_claim = released
    row = SpawnFailureRecord(
        agent_id=agent_id,
        agent_name=agent_name,
        issue_number=issue_number,
        pr_number=pr_number,
        attempt=next_attempt,
        released=released,
        error=error,
        at=at,
    )
    return StrikeUpdate(
        failures=list(failures) + [row],
        drop_claim=drop_claim,
        warn=warn,
    )


def clear_spawn_failures(
    failures: list[SpawnFailureRecord],
    *,
    issue_number: int | None = None,
    pr_number: int | None = None,
) -> list[SpawnFailureRecord]:
    result: list[SpawnFailureRecord] = []
    for failure in failures:
        if issue_number is not None and failure.issue_number == issue_number:
            continue
        if pr_number is not None and failure.pr_number == pr_number:
            continue
        result.append(failure)
    return result


def clear_unselectable_pr_failures(
    failures: list[SpawnFailureRecord],
    pull_requests: list[PullRequest],
) -> list[SpawnFailureRecord]:
    """Clear PR failure rows when that PR is not selectable on this poll."""
    by_number = {pr.number: pr for pr in pull_requests}
    result: list[SpawnFailureRecord] = []
    for failure in failures:
        if failure.pr_number is None:
            result.append(failure)
            continue
        pr = by_number.get(failure.pr_number)
        if pr is None or not _pr_selectable(pr):
            continue
        result.append(failure)
    return result


def _pr_selectable(pr: PullRequest) -> bool:
    if pr.draft:
        return False
    if pr.mergeable_state in {"", "unknown", "clean"}:
        return False
    return True


def _issue_by_number(intake: list[Issue], number: int) -> Issue | None:
    for issue in intake:
        if issue.number == number:
            return issue
    return None


def _agent_by_id(agents: list[AgentConfig], agent_id: str) -> AgentConfig | None:
    for agent in agents:
        if agent.id == agent_id:
            return agent
    return None
