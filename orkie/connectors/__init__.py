"""Connector protocol, resolve/build helpers, and type re-exports."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from orkie.connectors.types import (
    AuthError,
    ConnectorError,
    Issue,
    NotFoundError,
    OwnerRepo,
    Privilege,
    ProbeResult,
    PullRequest,
    RateLimitError,
)

if TYPE_CHECKING:
    from orkie.config import Config

__all__ = [
    "AuthError",
    "Connector",
    "ConnectorError",
    "Issue",
    "NotFoundError",
    "OwnerRepo",
    "Privilege",
    "ProbeResult",
    "PullRequest",
    "RateLimitError",
    "build_connector",
    "required_privileges",
    "resolve_github_repo",
]

_GITHUB_REMOTE = re.compile(
    r"(?:https://github\.com/|git@github\.com:)([^/]+)/([^/.]+?)(?:\.git)?$"
)


class Connector(Protocol):
    def repository_id(self) -> OwnerRepo: ...

    def list_open_issues(self) -> list[Issue]: ...

    def list_open_pull_requests(self) -> list[PullRequest]: ...

    def probe_privileges(self, required: set[Privilege]) -> ProbeResult: ...


def required_privileges(config: Config) -> set[Privilege]:
    required = {
        Privilege.TOKEN,
        Privilege.READ_REPOSITORY,
        Privilege.READ_ISSUES,
    }
    if config.babysitter.enabled:
        required.add(Privilege.READ_PULL_REQUESTS)
    return required


def build_connector(config: Config, token: str, owner_repo: OwnerRepo) -> Connector:
    from orkie.connectors.github import GitHubConnector

    if config.connector.type == "github":
        return GitHubConnector(token, owner_repo)
    raise ConnectorError(f"unsupported connector type: {config.connector.type}")


def resolve_github_repo(project_root: Path, connector_repo: str | None) -> OwnerRepo:
    if connector_repo is not None:
        owner, name = connector_repo.split("/", 1)
        return OwnerRepo(owner=owner, name=name)
    remotes = _list_remotes(project_root)
    github: list[tuple[str, OwnerRepo]] = []
    for name, url in remotes:
        parsed = _parse_github_url(url)
        if parsed is not None:
            github.append((name, parsed))
    for name, owner_repo in github:
        if name == "origin":
            return owner_repo
    if len(github) == 1:
        return github[0][1]
    raise ConnectorError(
        "could not resolve GitHub repository; set connector.repo to owner/name"
    )


def _list_remotes(project_root: Path) -> list[tuple[str, str]]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(project_root), "remote", "-v"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConnectorError(f"failed to list git remotes: {exc}") from exc
    remotes: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, url = parts[0], parts[1]
        if name in seen:
            continue
        seen.add(name)
        remotes.append((name, url))
    return remotes


def _parse_github_url(url: str) -> OwnerRepo | None:
    match = _GITHUB_REMOTE.match(url.strip())
    if match is None:
        return None
    return OwnerRepo(owner=match.group(1), name=match.group(2))
