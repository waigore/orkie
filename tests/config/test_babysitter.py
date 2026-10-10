"""Babysitter and labels-trigger config parsing."""

from __future__ import annotations

from pathlib import Path

from orkie.config import load_config


def test_load_babysitter_enabled(tmp_path: Path) -> None:
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
  repo: a/b
issue_labels: [orkie]
agents:
  - id: worker
    name: Worker
    role: worker
    command: [opencode, acp]
    prompt: "x"
    triggers:
      - type: labels
        labels: [orkie]
babysitter:
  enabled: true
  id: sitter
  name: Sitter
  role: babysitter
  command_ref: grok
  prompt: "PR __PRNO__"
""",
        encoding="utf-8",
    )
    config = load_config(project)
    assert config.babysitter.enabled
    assert config.babysitter.id == "sitter"
    assert config.babysitter.command == [
        "grok",
        "agent",
        "--always-approve",
        "stdio",
    ]
    assert config.agents[0].triggers[0].type == "labels"
