"""Shared pytest fixtures for the offline suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from orkie.config import (
    AgentConfig,
    BabysitterConfig,
    Config,
    ConnectorConfig,
    Trigger,
)
from orkie.connectors.types import Issue, OwnerRepo, PullRequest


@pytest.fixture
def owner_repo() -> OwnerRepo:
    return OwnerRepo(owner="acme", name="demo")


@pytest.fixture
def sample_issue() -> Issue:
    return Issue(
        number=42,
        title="Fix bug",
        body="details",
        url="https://github.com/acme/demo/issues/42",
        state="open",
        labels=["orkie"],
    )


@pytest.fixture
def sample_pr() -> PullRequest:
    return PullRequest(
        number=7,
        title="WIP",
        url="https://github.com/acme/demo/pull/7",
        head="feature",
        base="main",
        draft=False,
        mergeable_state="dirty",
    )


@pytest.fixture
def sample_config() -> Config:
    return Config(
        version=1,
        connector=ConnectorConfig(type="github", repo="acme/demo"),
        poll_interval_seconds=60,
        issue_labels=["orkie"],
        max_concurrent_sessions=1,
        dashboard_port=8765,
        agents=[
            AgentConfig(
                id="worker",
                name="Worker",
                role="worker",
                command=["opencode", "acp"],
                max_concurrent_sessions=1,
                prompt_template="Work on #__ISSUENO__ __ISSUE_TITLE__",
                triggers=[Trigger(type="any", labels=[])],
            )
        ],
        babysitter=BabysitterConfig(
            enabled=False,
            id=None,
            name=None,
            role=None,
            command=None,
            prompt_template=None,
        ),
    )


@pytest.fixture
def write_scaffold_config(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    orkie = project / ".orkie"
    orkie.mkdir()
    (orkie / "config.yaml").write_text(
        """\
version: 1
connector:
  type: github
  repo: acme/demo
issue_labels:
  - orkie
agents:
  - id: worker
    name: Worker
    role: worker
    command: [opencode, acp]
    prompt: "Issue __ISSUENO__"
    triggers:
      - type: any
babysitter:
  enabled: false
""",
        encoding="utf-8",
    )
    return project
