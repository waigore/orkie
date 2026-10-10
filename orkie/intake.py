"""Fetch intake issues, maintain snapshot, compute delta."""

from __future__ import annotations

from dataclasses import dataclass

from orkie.config import Config
from orkie.connectors import Connector
from orkie.connectors.types import ConnectorError, Issue
from orkie.state import Snapshot, SnapshotIssue, StateStore, utc_now_iso


@dataclass(frozen=True, slots=True)
class IntakeDelta:
    entered: list[Issue]
    left: list[Issue]
    labels_changed: list[Issue]


@dataclass(frozen=True, slots=True)
class IntakeResult:
    ok: bool
    intake_issues: list[Issue]
    delta: IntakeDelta | None
    error: str | None


def eligible_issue(issue: Issue, issue_labels: list[str]) -> bool:
    label_set = set(issue_labels)
    return any(label in label_set for label in issue.labels)


def diff_intake(previous: list[SnapshotIssue], current: list[Issue]) -> IntakeDelta:
    prev_by_number = {item.number: item for item in previous}
    curr_by_number = {item.number: item for item in current}
    entered = [curr_by_number[n] for n in sorted(curr_by_number) if n not in prev_by_number]
    left_issues: list[Issue] = []
    for number in sorted(prev_by_number):
        if number not in curr_by_number:
            prev = prev_by_number[number]
            left_issues.append(
                Issue(
                    number=prev.number,
                    title=prev.title,
                    body=prev.body,
                    url=prev.url,
                    state=prev.state,
                    labels=list(prev.labels),
                )
            )
    labels_changed: list[Issue] = []
    for number in sorted(curr_by_number):
        if number not in prev_by_number:
            continue
        prev = prev_by_number[number]
        curr = curr_by_number[number]
        if set(prev.labels) != set(curr.labels):
            labels_changed.append(curr)
    return IntakeDelta(entered=entered, left=left_issues, labels_changed=labels_changed)


class Intake:
    def __init__(self, config: Config, connector: Connector, store: StateStore) -> None:
        self._config = config
        self._connector = connector
        self._store = store
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def fetch_and_diff(self) -> IntakeResult:
        try:
            open_issues = self._connector.list_open_issues()
        except ConnectorError as exc:
            self._last_error = str(exc)
            return IntakeResult(ok=False, intake_issues=[], delta=None, error=str(exc))
        except Exception as exc:  # noqa: BLE001 — surface unexpected connector failures
            self._last_error = str(exc)
            return IntakeResult(ok=False, intake_issues=[], delta=None, error=str(exc))
        intake_issues = [
            issue
            for issue in open_issues
            if eligible_issue(issue, self._config.issue_labels)
        ]
        previous = self._store.load_snapshot()
        prev_issues = list(previous.issues) if previous is not None else []
        delta = diff_intake(prev_issues, intake_issues)
        snapshot = Snapshot(
            fetched_at=utc_now_iso(),
            issues=[
                SnapshotIssue(
                    number=issue.number,
                    title=issue.title,
                    body=issue.body,
                    url=issue.url,
                    state=issue.state,
                    labels=list(issue.labels),
                )
                for issue in intake_issues
            ],
        )
        self._store.save_snapshot(snapshot)
        self._last_error = None
        return IntakeResult(
            ok=True,
            intake_issues=intake_issues,
            delta=delta,
            error=None,
        )
