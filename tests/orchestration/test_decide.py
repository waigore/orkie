"""Pure orchestration decision tests."""

from __future__ import annotations

from orkie.config import AgentConfig, Trigger
from orkie.connectors.types import Issue, PullRequest
from orkie.orchestration.decide import (
    agent_matches,
    blocked_by_spawn_failures,
    cap_room,
    claim_still_applies,
    clear_spawn_failures,
    plan_exits,
    plan_fulfillment,
    plan_new_claims,
    record_spawn_failure,
    select_babysitter,
)
from orkie.state import ClaimRecord, SessionRecord, SpawnFailureRecord


def _agent(agent_id: str = "worker", *, labels: list[str] | None = None) -> AgentConfig:
    if labels is None:
        triggers = [Trigger(type="any", labels=[])]
    else:
        triggers = [Trigger(type="labels", labels=labels)]
    return AgentConfig(
        id=agent_id,
        name=agent_id.title(),
        role="worker",
        command=["opencode", "acp"],
        max_concurrent_sessions=1,
        prompt_template="x",
        triggers=triggers,
    )


def test_agent_matches_any_and_labels() -> None:
    issue = Issue(1, "t", "", "u", "open", ["orkie", "bug"])
    assert agent_matches(_agent(), issue)
    assert agent_matches(_agent(labels=["orkie"]), issue)
    assert not agent_matches(_agent(labels=["missing"]), issue)


def test_claim_still_applies() -> None:
    issue = Issue(1, "t", "", "u", "open", ["orkie"])
    claim = ClaimRecord("worker", 1, "t")
    assert claim_still_applies(claim, [issue], [_agent()])
    assert not claim_still_applies(claim, [], [_agent()])
    assert not claim_still_applies(claim, [issue], [_agent("other")])


def test_cap_room() -> None:
    agent = _agent()
    working = [
        SessionRecord("s", "worker", 1, None, True, "/w", "t"),
    ]
    assert cap_room(agent, working, global_max=1) == 0
    assert cap_room(agent, [], global_max=1) == 1


def test_blocked_by_spawn_failures() -> None:
    failures = [
        SpawnFailureRecord("w", "W", 1, None, 3, True, "e", "t"),
    ]
    assert blocked_by_spawn_failures(failures, issue_number=1)
    assert not blocked_by_spawn_failures(failures, issue_number=2)


def test_plan_fulfillment_ascending() -> None:
    issues = [
        Issue(2, "b", "", "u", "open", ["orkie"]),
        Issue(1, "a", "", "u", "open", ["orkie"]),
    ]
    claims = [
        ClaimRecord("worker", 2, "t"),
        ClaimRecord("worker", 1, "t"),
    ]
    agent = _agent()
    agent = AgentConfig(
        id=agent.id,
        name=agent.name,
        role=agent.role,
        command=agent.command,
        max_concurrent_sessions=2,
        prompt_template=agent.prompt_template,
        triggers=agent.triggers,
    )
    plan = plan_fulfillment(claims, issues, [agent], [], [], global_max=2)
    assert [w.issue.number for w in plan] == [1, 2]


def test_plan_new_claims_stops_when_caps_full() -> None:
    issues = [
        Issue(1, "a", "", "u", "open", ["orkie"]),
        Issue(2, "b", "", "u", "open", ["orkie"]),
    ]
    plan = plan_new_claims(issues, [], [_agent()], [], [], global_max=1)
    assert len(plan) == 1
    assert plan[0].issue.number == 1


def test_plan_exits_drop_claim_only_when_running() -> None:
    sessions = [SessionRecord("s", "worker", 1, None, True, "/w", "t")]
    exits = plan_exits(sessions, alive_ids=set(), shutdown_started=False)
    assert exits[0].drop_claim is True
    exits2 = plan_exits(sessions, alive_ids=set(), shutdown_started=True)
    assert exits2[0].drop_claim is False


def test_select_babysitter_lowest_blocked() -> None:
    prs = [
        PullRequest(3, "c", "u", "h", "main", False, "dirty"),
        PullRequest(1, "a", "u", "h", "main", True, "dirty"),
        PullRequest(2, "b", "u", "h", "main", False, "clean"),
        PullRequest(4, "d", "u", "h", "main", False, "unknown"),
        PullRequest(5, "e", "u", "h", "main", False, "blocked"),
    ]
    chosen = select_babysitter(prs, [], babysitter_working=False)
    assert chosen is not None
    assert chosen.number == 3


def test_attempt_three_drops_the_claim() -> None:
    prior = [
        SpawnFailureRecord("w", "W", 1, None, 1, False, "e", "t"),
        SpawnFailureRecord("w", "W", 1, None, 2, False, "e", "t"),
    ]
    update = record_spawn_failure(
        prior,
        agent_id="w",
        agent_name="W",
        issue_number=1,
        pr_number=None,
        error="fail",
        at="t",
    )
    assert update.drop_claim is True
    assert update.warn is True
    assert update.failures[-1].attempt == 3
    assert update.failures[-1].released is True


def test_clear_spawn_failures_for_issue() -> None:
    failures = [
        SpawnFailureRecord("w", "W", 1, None, 1, False, "e", "t"),
        SpawnFailureRecord("w", "W", 2, None, 1, False, "e", "t"),
    ]
    cleared = clear_spawn_failures(failures, issue_number=1)
    assert [f.issue_number for f in cleared] == [2]
