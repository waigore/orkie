"""Connector domain types and errors. No config or HTTP imports."""

from __future__ import annotations

import enum
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OwnerRepo:
    owner: str
    name: str


@dataclass(frozen=True, slots=True)
class Issue:
    number: int
    title: str
    body: str
    url: str
    state: str
    labels: list[str]


@dataclass(frozen=True, slots=True)
class PullRequest:
    number: int
    title: str
    url: str
    head: str
    base: str
    draft: bool
    mergeable_state: str


class Privilege(enum.Enum):
    TOKEN = "token"
    READ_REPOSITORY = "read_repository"
    READ_ISSUES = "read_issues"
    READ_PULL_REQUESTS = "read_pull_requests"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    missing_required: set[Privilege]
    missing_warn_only: set[Privilege]


class ConnectorError(Exception):
    """Base connector failure."""


class AuthError(ConnectorError):
    """HTTP 401/403 or equivalent auth failure."""


class RateLimitError(ConnectorError):
    """GitHub rate-limit response."""


class NotFoundError(ConnectorError):
    """HTTP 404 or missing resource."""
