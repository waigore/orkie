"""build_connector and git remote resolution coverage."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from orkie.config import (
    AgentConfig,
    BabysitterConfig,
    Config,
    ConnectorConfig,
    Trigger,
)
from orkie.connectors import build_connector, resolve_github_repo
from orkie.connectors.github import GitHubConnector
from orkie.connectors.types import ConnectorError, OwnerRepo


def _config() -> Config:
    return Config(
        version=1,
        connector=ConnectorConfig(type="github", repo=None),
        poll_interval_seconds=60,
        issue_labels=["orkie"],
        max_concurrent_sessions=1,
        dashboard_port=8765,
        agents=[
            AgentConfig(
                id="w",
                name="W",
                role="w",
                command=["x"],
                max_concurrent_sessions=1,
                prompt_template="p",
                triggers=[Trigger(type="any", labels=[])],
            )
        ],
        babysitter=BabysitterConfig(False, None, None, None, None, None),
    )


def test_build_connector_github() -> None:
    client = build_connector(_config(), "tok", OwnerRepo("o", "r"))
    assert isinstance(client, GitHubConnector)


def test_resolve_origin_remote(tmp_path: Path) -> None:
    remotes = "origin\thttps://github.com/acme/demo.git (fetch)\norigin\thttps://github.com/acme/demo.git (push)\n"

    class Completed:
        stdout = remotes

    with mock.patch("orkie.connectors.subprocess.run", return_value=Completed()):
        owner = resolve_github_repo(tmp_path, None)
    assert owner == OwnerRepo("acme", "demo")


def test_resolve_sole_github_remote(tmp_path: Path) -> None:
    remotes = "upstream\tgit@github.com:solo/repo.git (fetch)\n"

    class Completed:
        stdout = remotes

    with mock.patch("orkie.connectors.subprocess.run", return_value=Completed()):
        owner = resolve_github_repo(tmp_path, None)
    assert owner == OwnerRepo("solo", "repo")


def test_resolve_fails_without_github(tmp_path: Path) -> None:
    class Completed:
        stdout = "origin\thttps://example.com/x.git (fetch)\n"

    with mock.patch("orkie.connectors.subprocess.run", return_value=Completed()):
        with pytest.raises(ConnectorError, match="connector.repo"):
            resolve_github_repo(tmp_path, None)
