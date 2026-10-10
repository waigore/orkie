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
    assert config.agents[0].command == ["opencode", "acp"]
    assert config.poll_interval_seconds == 60
    assert config.max_concurrent_sessions == 1


def test_scaffold_resolves_opencode_ref(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    write_default_scaffold(project)
    config = load_config(project)
    assert config.agents[0].command == ["opencode", "acp"]


def test_command_ref_builtin_cursor(write_scaffold_config: Path) -> None:
    path = write_scaffold_config / ".orkie" / "config.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "command: [opencode, acp]", "command_ref: cursor"
        ),
        encoding="utf-8",
    )
    config = load_config(write_scaffold_config)
    assert config.agents[0].command == ["agent", "acp"]


def test_command_ref_custom_preset(write_scaffold_config: Path) -> None:
    path = write_scaffold_config / ".orkie" / "config.yaml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "issue_labels:\n  - orkie\n",
        "issue_labels:\n  - orkie\ncommands:\n  my_fork: [opencode, acp, --foo]\n",
    )
    text = text.replace("command: [opencode, acp]", "command_ref: my_fork")
    path.write_text(text, encoding="utf-8")
    config = load_config(write_scaffold_config)
    assert config.agents[0].command == ["opencode", "acp", "--foo"]


def test_command_ref_unknown_rejects(write_scaffold_config: Path) -> None:
    path = write_scaffold_config / ".orkie" / "config.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "command: [opencode, acp]", "command_ref: missing"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="command_ref"):
        load_config(write_scaffold_config)


def test_commands_builtin_collision_rejects(write_scaffold_config: Path) -> None:
    path = write_scaffold_config / ".orkie" / "config.yaml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "issue_labels:\n  - orkie\n",
        "issue_labels:\n  - orkie\ncommands:\n  opencode: [other, acp]\n",
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="built-in"):
        load_config(write_scaffold_config)


def test_command_and_command_ref_both_reject(write_scaffold_config: Path) -> None:
    path = write_scaffold_config / ".orkie" / "config.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "command: [opencode, acp]",
            "command: [opencode, acp]\n    command_ref: opencode",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="exactly one of command or command_ref"):
        load_config(write_scaffold_config)


def test_command_neither_rejects(write_scaffold_config: Path) -> None:
    path = write_scaffold_config / ".orkie" / "config.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "    command: [opencode, acp]\n", ""
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="exactly one of command or command_ref"):
        load_config(write_scaffold_config)


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


def _write_prompt_file_config(
    project: Path,
    *,
    prompt_root: str | None = None,
    prompt_file: str,
) -> None:
    root_line = f"prompt_root: {prompt_root}\n" if prompt_root is not None else ""
    (project / ".orkie" / "config.yaml").write_text(
        f"""\
version: 1
connector:
  type: github
issue_labels: [orkie]
{root_line}agents:
  - id: worker
    name: Worker
    role: worker
    command: [opencode, acp]
    prompt_file: {prompt_file}
    triggers:
      - type: any
""",
        encoding="utf-8",
    )


def test_prompt_file_default_root(write_scaffold_config: Path) -> None:
    prompt = write_scaffold_config / "prompts" / "worker.md"
    prompt.parent.mkdir()
    prompt.write_text("from project root\n", encoding="utf-8")
    _write_prompt_file_config(write_scaffold_config, prompt_file="prompts/worker.md")
    config = load_config(write_scaffold_config)
    assert config.agents[0].prompt_template == "from project root\n"


def test_prompt_file_custom_root(write_scaffold_config: Path) -> None:
    prompt = write_scaffold_config / "prompts" / "worker.md"
    prompt.parent.mkdir()
    prompt.write_text("from prompt root\n", encoding="utf-8")
    _write_prompt_file_config(
        write_scaffold_config,
        prompt_root="prompts",
        prompt_file="worker.md",
    )
    config = load_config(write_scaffold_config)
    assert config.agents[0].prompt_template == "from prompt root\n"


def test_prompt_file_orkie_root_migration(write_scaffold_config: Path) -> None:
    prompt = write_scaffold_config / ".orkie" / "worker.md"
    prompt.write_text("under orkie\n", encoding="utf-8")
    _write_prompt_file_config(
        write_scaffold_config,
        prompt_root=".orkie",
        prompt_file="worker.md",
    )
    config = load_config(write_scaffold_config)
    assert config.agents[0].prompt_template == "under orkie\n"


def test_prompt_file_rejects_escape(write_scaffold_config: Path) -> None:
    _write_prompt_file_config(write_scaffold_config, prompt_file="../../secret.md")
    with pytest.raises(ConfigError, match="prompt_file"):
        load_config(write_scaffold_config)


def test_prompt_file_rejects_absolute(write_scaffold_config: Path) -> None:
    _write_prompt_file_config(write_scaffold_config, prompt_file="/tmp/secret.md")
    with pytest.raises(ConfigError, match="prompt_file"):
        load_config(write_scaffold_config)


def test_prompt_root_rejects_escape(write_scaffold_config: Path) -> None:
    _write_prompt_file_config(
        write_scaffold_config,
        prompt_root="..",
        prompt_file="worker.md",
    )
    with pytest.raises(ConfigError, match="prompt_root"):
        load_config(write_scaffold_config)


def test_prompt_root_rejects_absolute(write_scaffold_config: Path) -> None:
    _write_prompt_file_config(
        write_scaffold_config,
        prompt_root="/tmp",
        prompt_file="worker.md",
    )
    with pytest.raises(ConfigError, match="prompt_root"):
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
