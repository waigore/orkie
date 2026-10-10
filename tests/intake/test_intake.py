"""Intake eligibility, delta, and fetch-failure behavior."""

from __future__ import annotations

from pathlib import Path

from orkie.config import Config
from orkie.connectors.fake import FakeConnector
from orkie.connectors.types import ConnectorError, Issue, OwnerRepo
from orkie.intake import Intake, diff_intake, eligible_issue
from orkie.state import Snapshot, SnapshotIssue, StateStore


def test_eligible_issue_intersects_labels(sample_issue: Issue) -> None:
    assert eligible_issue(sample_issue, ["orkie"])
    assert not eligible_issue(sample_issue, ["other"])


def test_diff_intake_entered_left_labels() -> None:
    previous = [
        SnapshotIssue(
            number=1,
            title="a",
            body="",
            url="u",
            state="open",
            labels=["orkie"],
        ),
        SnapshotIssue(
            number=2,
            title="b",
            body="",
            url="u",
            state="open",
            labels=["orkie"],
        ),
    ]
    current = [
        Issue(2, "b", "", "u", "open", ["orkie", "bug"]),
        Issue(3, "c", "", "u", "open", ["orkie"]),
    ]
    delta = diff_intake(previous, current)
    assert [i.number for i in delta.entered] == [3]
    assert [i.number for i in delta.left] == [1]
    assert [i.number for i in delta.labels_changed] == [2]


def test_fetch_success_saves_snapshot(
    tmp_path: Path, sample_config: Config, sample_issue: Issue, owner_repo: OwnerRepo
) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    connector = FakeConnector(owner_repo, issues=[sample_issue])
    intake = Intake(sample_config, connector, store)
    result = intake.fetch_and_diff()
    assert result.ok
    assert result.intake_issues[0].number == 42
    assert store.load_snapshot() is not None
    assert intake.last_error is None


def test_fetch_failure_keeps_snapshot(
    tmp_path: Path, sample_config: Config, sample_issue: Issue, owner_repo: OwnerRepo
) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    store.save_snapshot(
        Snapshot(
            fetched_at="2026-01-01T00:00:00Z",
            issues=[
                SnapshotIssue(
                    number=sample_issue.number,
                    title=sample_issue.title,
                    body=sample_issue.body,
                    url=sample_issue.url,
                    state=sample_issue.state,
                    labels=list(sample_issue.labels),
                )
            ],
        )
    )
    connector = FakeConnector(
        owner_repo,
        issues_error=ConnectorError("network down"),
    )
    intake = Intake(sample_config, connector, store)
    result = intake.fetch_and_diff()
    assert not result.ok
    assert result.error == "network down"
    assert intake.last_error == "network down"
    assert store.load_snapshot() is not None
    assert store.load_snapshot().issues[0].number == 42  # type: ignore[union-attr]
