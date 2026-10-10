"""Repository resolution and privilege set tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from orkie.config import BabysitterConfig, Config, ConnectorConfig, AgentConfig, Trigger
from orkie.connectors import required_privileges, resolve_github_repo
from orkie.connectors.types import Privilege


def _minimal_config(*, babysitter: bool = False) -> Config:
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
        babysitter=BabysitterConfig(
            enabled=babysitter,
            id="b" if babysitter else None,
            name="B" if babysitter else None,
            role="b" if babysitter else None,
            command=["x"] if babysitter else None,
            prompt_template="p" if babysitter else None,
        ),
    )


def test_required_privileges_without_babysitter() -> None:
    required = required_privileges(_minimal_config(babysitter=False))
    assert Privilege.READ_PULL_REQUESTS not in required
    assert Privilege.TOKEN in required


def test_required_privileges_with_babysitter() -> None:
    required = required_privileges(_minimal_config(babysitter=True))
    assert Privilege.READ_PULL_REQUESTS in required


def test_resolve_explicit_repo(tmp_path: Path) -> None:
    owner = resolve_github_repo(tmp_path, "acme/demo")
    assert owner.owner == "acme"
    assert owner.name == "demo"
