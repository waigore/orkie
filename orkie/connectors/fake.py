"""In-memory Connector for offline tests."""

from __future__ import annotations

from orkie.connectors.types import (
    ConnectorError,
    Issue,
    OwnerRepo,
    Privilege,
    ProbeResult,
    PullRequest,
)


class FakeConnector:
    def __init__(
        self,
        owner_repo: OwnerRepo,
        *,
        issues: list[Issue] | None = None,
        pull_requests: list[PullRequest] | None = None,
        probe_result: ProbeResult | None = None,
        issues_error: Exception | None = None,
        pulls_error: Exception | None = None,
    ) -> None:
        self._owner_repo = owner_repo
        self.issues = list(issues or [])
        self.pull_requests = list(pull_requests or [])
        self.probe_result = probe_result or ProbeResult(
            missing_required=set(),
            missing_warn_only=set(),
        )
        self.issues_error = issues_error
        self.pulls_error = pulls_error

    def repository_id(self) -> OwnerRepo:
        return self._owner_repo

    def list_open_issues(self) -> list[Issue]:
        if self.issues_error is not None:
            raise self.issues_error
        return list(self.issues)

    def list_open_pull_requests(self) -> list[PullRequest]:
        if self.pulls_error is not None:
            raise self.pulls_error
        return list(self.pull_requests)

    def probe_privileges(self, required: set[Privilege]) -> ProbeResult:
        missing = set(self.probe_result.missing_required) & required
        return ProbeResult(missing_required=missing, missing_warn_only=set())


class RaisingConnector(FakeConnector):
    """Connector that always fails issue fetches."""

    def __init__(self, owner_repo: OwnerRepo, error: Exception | None = None) -> None:
        super().__init__(
            owner_repo,
            issues_error=error or ConnectorError("fake failure"),
        )
