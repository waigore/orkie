"""Config load, scaffold, and prompt substitution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from orkie.config import (
    DEFAULT_SCAFFOLD,
    ConfigError,
    load_config,
    substitute_prompt,
    write_default_scaffold,
)
from orkie.connectors.types import Issue, PullRequest


def test_load_valid_config(write_scaffold_config: Path) -> None:
    config = load_config(write_scaffold_config)
    assert config.version == 1
    assert config.agents[0].id == "worker"
    assert config.poll_interval_seconds == 60
    assert config.max_concurrent_sessions == 1


def test_unknown_field_rejects(write_scaffold_config: Path) -> None:
    path = write_scaffold_config / ".orkie" / "config.yaml"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nextra: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="extra"):
        load_config(write_scaffold_config)


def test_scaffold_exact_text(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    write_default_scaffold(project)
    text = (project / ".orkie" / "config.yaml").read_text(encoding="utf-8")
    assert text == DEFAULT_SCAFFOLD


def test_prompt_file_rejects_escape(write_scaffold_config: Path) -> None:
    path = write_scaffold_config / ".orkie" / "config.yaml"
    path.write_text(
        """\
version: 1
connector:
  type: github
issue_labels: [orkie]
agents:
  - id: worker
    name: Worker
    role: worker
    command: [opencode, acp]
    prompt_file: ../../secret.md
    triggers:
      - type: any
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="prompt_file"):
        load_config(write_scaffold_config)


def test_substitute_prompt_issue_clears_pr_tokens() -> None:
    issue = Issue(
        number=1,
        title="T",
        body="B",
        url="U",
        state="open",
        labels=["a", "b"],
    )
    text = substitute_prompt(
        "__ISSUENO__|__PRNO__|__ISSUE_LABELS__|__REPO__",
        session_id="s",
        agent_id="w",
        agent_name="W",
        repo="o/r",
        issue=issue,
        pr=None,
    )
    assert text == "1||a,b|o/r"


def test_substitute_prompt_babysitter_clears_issue_tokens() -> None:
    pr = PullRequest(
        number=9,
        title="PT",
        url="PU",
        head="h",
        base="main",
        draft=False,
        mergeable_state="dirty",
    )
    text = substitute_prompt(
        "__ISSUENO__|__PRNO__|__PR_MERGE_STATE__",
        session_id="s",
        agent_id="b",
        agent_name="B",
        repo="o/r",
        issue=None,
        pr=pr,
    )
    assert text == "|9|dirty"
