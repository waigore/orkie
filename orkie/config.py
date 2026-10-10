"""Load and validate .orkie/config.yaml; scaffold write; prompt substitution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from orkie.connectors.types import Issue, PullRequest

BUILTIN_COMMANDS: dict[str, list[str]] = {
    "cursor": ["agent", "acp"],
    "opencode": ["opencode", "acp"],
    "grok": ["grok", "agent", "--always-approve", "stdio"],
}

DEFAULT_SCAFFOLD = """\
version: 1
connector:
  type: github
poll_interval_seconds: 60
issue_labels:
  - orkie
max_concurrent_sessions: 1
dashboard_port: 8765
agents:
  - id: worker
    name: Worker
    role: worker
    command_ref: opencode
    max_concurrent_sessions: 1
    prompt: |
      You are working on a single GitHub issue, #__ISSUENO__.
      Title: __ISSUE_TITLE__
      URL: __ISSUE_URL__

      __ISSUE_BODY__

      Attempt to handle this issue. Do not pick up any other issue.
    triggers:
      - type: any
babysitter:
  enabled: false
"""


class ConfigError(Exception):
    """Invalid or unreadable project config."""


@dataclass(frozen=True, slots=True)
class ConnectorConfig:
    type: str
    repo: str | None


@dataclass(frozen=True, slots=True)
class Trigger:
    type: Literal["any", "labels"]
    labels: list[str]


@dataclass(frozen=True, slots=True)
class AgentConfig:
    id: str
    name: str
    role: str
    command: list[str]
    max_concurrent_sessions: int
    prompt_template: str
    triggers: list[Trigger]


@dataclass(frozen=True, slots=True)
class BabysitterConfig:
    enabled: bool
    id: str | None
    name: str | None
    role: str | None
    command: list[str] | None
    prompt_template: str | None


@dataclass(frozen=True, slots=True)
class Config:
    version: int
    connector: ConnectorConfig
    poll_interval_seconds: int
    issue_labels: list[str]
    max_concurrent_sessions: int
    dashboard_port: int
    agents: list[AgentConfig]
    babysitter: BabysitterConfig


def config_path(project_root: Path) -> Path:
    return project_root / ".orkie" / "config.yaml"


def write_default_scaffold(project_root: Path) -> None:
    path = config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_SCAFFOLD, encoding="utf-8")


def load_config(project_root: Path) -> Config:
    path = config_path(project_root)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if data is None:
        raise ConfigError(f"{path}: empty document")
    root = _require_dict(data, path="")
    return _parse_config(root, project_root)


def substitute_prompt(
    template: str,
    *,
    session_id: str,
    agent_id: str,
    agent_name: str,
    repo: str,
    issue: Issue | None,
    pr: PullRequest | None,
) -> str:
    if issue is not None:
        issue_no = str(issue.number)
        issue_title = issue.title
        issue_body = issue.body
        issue_url = issue.url
        issue_labels = ",".join(issue.labels)
    else:
        issue_no = ""
        issue_title = ""
        issue_body = ""
        issue_url = ""
        issue_labels = ""
    if pr is not None:
        pr_no = str(pr.number)
        pr_title = pr.title
        pr_url = pr.url
        pr_branch = pr.head
        pr_base = pr.base
        pr_merge = pr.mergeable_state
    else:
        pr_no = ""
        pr_title = ""
        pr_url = ""
        pr_branch = ""
        pr_base = ""
        pr_merge = ""
    text = template
    text = text.replace("__ISSUENO__", issue_no)
    text = text.replace("__ISSUE_TITLE__", issue_title)
    text = text.replace("__ISSUE_BODY__", issue_body)
    text = text.replace("__ISSUE_URL__", issue_url)
    text = text.replace("__ISSUE_LABELS__", issue_labels)
    text = text.replace("__PRNO__", pr_no)
    text = text.replace("__PR_TITLE__", pr_title)
    text = text.replace("__PR_URL__", pr_url)
    text = text.replace("__PR_BRANCH__", pr_branch)
    text = text.replace("__PR_BASE__", pr_base)
    text = text.replace("__PR_MERGE_STATE__", pr_merge)
    text = text.replace("__AGENT_ID__", agent_id)
    text = text.replace("__AGENT_NAME__", agent_name)
    text = text.replace("__SESSION_ID__", session_id)
    text = text.replace("__REPO__", repo)
    return text


def _parse_config(root: dict[str, Any], project_root: Path) -> Config:
    allowed = {
        "version",
        "connector",
        "poll_interval_seconds",
        "issue_labels",
        "max_concurrent_sessions",
        "dashboard_port",
        "prompt_root",
        "commands",
        "agents",
        "babysitter",
    }
    _reject_unknown(root, allowed, path="")
    version = _require_int(root, "version", path="version")
    if version != 1:
        raise ConfigError("version: must be integer 1")
    connector_raw = _require_dict(root.get("connector"), path="connector")
    connector = _parse_connector(connector_raw)
    poll = _optional_int(root, "poll_interval_seconds", default=60, path="poll_interval_seconds")
    if poll < 15:
        raise ConfigError("poll_interval_seconds: must be an integer >= 15")
    issue_labels = _parse_issue_labels(root.get("issue_labels"))
    max_sessions = _optional_int(
        root, "max_concurrent_sessions", default=1, path="max_concurrent_sessions"
    )
    if max_sessions < 1:
        raise ConfigError("max_concurrent_sessions: must be an integer >= 1")
    dashboard_port = _optional_int(root, "dashboard_port", default=8765, path="dashboard_port")
    if dashboard_port < 1 or dashboard_port > 65535:
        raise ConfigError("dashboard_port: must be an integer 1–65535")
    prompt_root_raw = root.get("prompt_root", ".")
    prompt_base = _resolve_project_relative(
        prompt_root_raw, project_root, path="prompt_root"
    )
    command_presets = _parse_command_presets(root.get("commands"))
    agents_raw = root.get("agents")
    if not isinstance(agents_raw, list) or len(agents_raw) == 0:
        raise ConfigError("agents: must be a non-empty list")
    agents: list[AgentConfig] = []
    for index, item in enumerate(agents_raw):
        agents.append(
            _parse_agent(
                item,
                project_root,
                prompt_base,
                command_presets,
                path=f"agents[{index}]",
            )
        )
    babysitter_raw = root.get("babysitter")
    if babysitter_raw is None:
        babysitter = BabysitterConfig(
            enabled=False,
            id=None,
            name=None,
            role=None,
            command=None,
            prompt_template=None,
        )
    else:
        babysitter = _parse_babysitter(
            _require_dict(babysitter_raw, path="babysitter"),
            project_root,
            prompt_base,
            command_presets,
        )
    _check_unique_ids(agents, babysitter)
    return Config(
        version=version,
        connector=connector,
        poll_interval_seconds=poll,
        issue_labels=issue_labels,
        max_concurrent_sessions=max_sessions,
        dashboard_port=dashboard_port,
        agents=agents,
        babysitter=babysitter,
    )


def _parse_connector(raw: dict[str, Any]) -> ConnectorConfig:
    _reject_unknown(raw, {"type", "repo"}, path="connector")
    conn_type = _require_str(raw, "type", path="connector.type")
    if conn_type != "github":
        raise ConfigError("connector.type: must be github")
    repo = raw.get("repo")
    if repo is None:
        return ConnectorConfig(type=conn_type, repo=None)
    if not isinstance(repo, str) or not repo:
        raise ConfigError("connector.repo: must be a non-empty owner/name string")
    parts = repo.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ConfigError("connector.repo: must be owner/name with one slash")
    return ConnectorConfig(type=conn_type, repo=repo)


def _parse_issue_labels(raw: object) -> list[str]:
    if not isinstance(raw, list) or len(raw) == 0:
        raise ConfigError("issue_labels: must be a non-empty list")
    labels: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        path = f"issue_labels[{index}]"
        if not isinstance(item, str) or not item:
            raise ConfigError(f"{path}: must be a non-empty string")
        if len(item) > 50:
            raise ConfigError(f"{path}: must be at most 50 characters")
        if item in seen:
            raise ConfigError(f"{path}: label names must be unique")
        seen.add(item)
        labels.append(item)
    return labels


def _parse_agent(
    raw: object,
    project_root: Path,
    prompt_base: Path,
    command_presets: dict[str, list[str]],
    *,
    path: str,
) -> AgentConfig:
    obj = _require_dict(raw, path=path)
    _reject_unknown(
        obj,
        {
            "id",
            "name",
            "role",
            "command",
            "command_ref",
            "max_concurrent_sessions",
            "prompt",
            "prompt_file",
            "triggers",
        },
        path=path,
    )
    agent_id = _require_str(obj, "id", path=f"{path}.id")
    _validate_id(agent_id, path=f"{path}.id")
    name = _require_str(obj, "name", path=f"{path}.name")
    if not name:
        raise ConfigError(f"{path}.name: must be a non-empty string")
    role = _require_str(obj, "role", path=f"{path}.role")
    if not role:
        raise ConfigError(f"{path}.role: must be a non-empty string")
    command = _resolve_agent_command(obj, command_presets, path=path)
    max_sessions = _optional_int(
        obj, "max_concurrent_sessions", default=1, path=f"{path}.max_concurrent_sessions"
    )
    if max_sessions < 1:
        raise ConfigError(f"{path}.max_concurrent_sessions: must be an integer >= 1")
    prompt_template = _resolve_prompt(obj, project_root, prompt_base, path=path)
    triggers_raw = obj.get("triggers")
    if not isinstance(triggers_raw, list) or len(triggers_raw) == 0:
        raise ConfigError(f"{path}.triggers: must be a non-empty list")
    triggers = [
        _parse_trigger(item, path=f"{path}.triggers[{i}]") for i, item in enumerate(triggers_raw)
    ]
    return AgentConfig(
        id=agent_id,
        name=name,
        role=role,
        command=command,
        max_concurrent_sessions=max_sessions,
        prompt_template=prompt_template,
        triggers=triggers,
    )


def _parse_babysitter(
    raw: dict[str, Any],
    project_root: Path,
    prompt_base: Path,
    command_presets: dict[str, list[str]],
) -> BabysitterConfig:
    _reject_unknown(
        raw,
        {
            "enabled",
            "id",
            "name",
            "role",
            "command",
            "command_ref",
            "prompt",
            "prompt_file",
        },
        path="babysitter",
    )
    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("babysitter.enabled: must be a boolean")
    if not enabled:
        return BabysitterConfig(
            enabled=False,
            id=None,
            name=None,
            role=None,
            command=None,
            prompt_template=None,
        )
    babysitter_id = _require_str(raw, "id", path="babysitter.id")
    _validate_id(babysitter_id, path="babysitter.id")
    name = _require_str(raw, "name", path="babysitter.name")
    if not name:
        raise ConfigError("babysitter.name: must be a non-empty string")
    role = _require_str(raw, "role", path="babysitter.role")
    if not role:
        raise ConfigError("babysitter.role: must be a non-empty string")
    command = _resolve_agent_command(raw, command_presets, path="babysitter")
    prompt_template = _resolve_prompt(raw, project_root, prompt_base, path="babysitter")
    return BabysitterConfig(
        enabled=True,
        id=babysitter_id,
        name=name,
        role=role,
        command=command,
        prompt_template=prompt_template,
    )


def _parse_trigger(raw: object, *, path: str) -> Trigger:
    obj = _require_dict(raw, path=path)
    trigger_type = obj.get("type")
    if trigger_type == "any":
        _reject_unknown(obj, {"type"}, path=path)
        return Trigger(type="any", labels=[])
    if trigger_type == "labels":
        _reject_unknown(obj, {"type", "labels"}, path=path)
        labels_raw = obj.get("labels")
        if not isinstance(labels_raw, list) or len(labels_raw) == 0:
            raise ConfigError(f"{path}.labels: must be a non-empty list")
        labels: list[str] = []
        for i, item in enumerate(labels_raw):
            if not isinstance(item, str) or not item:
                raise ConfigError(f"{path}.labels[{i}]: must be a non-empty string")
            labels.append(item)
        return Trigger(type="labels", labels=labels)
    raise ConfigError(f"{path}.type: must be any or labels")


def _resolve_project_relative(rel: object, project_root: Path, *, path: str) -> Path:
    if not isinstance(rel, str) or not rel:
        raise ConfigError(f"{path}: must be a non-empty relative path under the project root")
    candidate = Path(rel)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ConfigError(f"{path}: must be a relative path under the project root")
    full = (project_root / candidate).resolve()
    root = project_root.resolve()
    if not full.is_relative_to(root):
        raise ConfigError(f"{path}: must be a relative path under the project root")
    return full


def _resolve_prompt(
    obj: dict[str, Any],
    project_root: Path,
    prompt_base: Path,
    *,
    path: str,
) -> str:
    has_prompt = "prompt" in obj
    has_file = "prompt_file" in obj
    if has_prompt == has_file:
        raise ConfigError(f"{path}: exactly one of prompt or prompt_file is required")
    if has_prompt:
        prompt = obj["prompt"]
        if not isinstance(prompt, str):
            raise ConfigError(f"{path}.prompt: must be a string")
        return prompt
    rel = obj["prompt_file"]
    if not isinstance(rel, str) or not rel:
        raise ConfigError(f"{path}.prompt_file: must be a non-empty relative path")
    candidate = Path(rel)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ConfigError(
            f"{path}.prompt_file: must be a relative path under prompt_root"
        )
    full = (prompt_base / candidate).resolve()
    root = project_root.resolve()
    if not full.is_relative_to(root):
        raise ConfigError(
            f"{path}.prompt_file: must be a relative path under the project root"
        )
    try:
        return full.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{path}.prompt_file: cannot read {rel}: {exc}") from exc


def _parse_command(raw: object, *, path: str) -> list[str]:
    if not isinstance(raw, list) or len(raw) == 0:
        raise ConfigError(f"{path}: must be a non-empty list of strings")
    command: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str) or not item:
            raise ConfigError(f"{path}[{i}]: must be a non-empty string")
        command.append(item)
    return command


def _parse_command_presets(raw: object) -> dict[str, list[str]]:
    presets = {name: list(argv) for name, argv in BUILTIN_COMMANDS.items()}
    if raw is None:
        return presets
    obj = _require_dict(raw, path="commands")
    for name, value in obj.items():
        if not isinstance(name, str) or not name:
            raise ConfigError("commands: keys must be non-empty strings")
        _validate_id(name, path=f"commands.{name}")
        if name in BUILTIN_COMMANDS:
            raise ConfigError(
                f"commands.{name}: name conflicts with a built-in command preset"
            )
        presets[name] = _parse_command(value, path=f"commands.{name}")
    return presets


def _resolve_agent_command(
    obj: dict[str, Any],
    command_presets: dict[str, list[str]],
    *,
    path: str,
) -> list[str]:
    has_command = "command" in obj
    has_ref = "command_ref" in obj
    if has_command == has_ref:
        raise ConfigError(f"{path}: exactly one of command or command_ref is required")
    if has_command:
        return _parse_command(obj.get("command"), path=f"{path}.command")
    ref = obj["command_ref"]
    if not isinstance(ref, str) or not ref:
        raise ConfigError(f"{path}.command_ref: must be a non-empty string")
    if ref not in command_presets:
        raise ConfigError(f"{path}.command_ref: unknown command preset {ref!r}")
    return list(command_presets[ref])


def _validate_id(value: str, *, path: str) -> None:
    if not value:
        raise ConfigError(f"{path}: must be a non-empty string")
    if any(ch.isspace() for ch in value):
        raise ConfigError(f"{path}: must not contain whitespace")
    if len(value) > 64:
        raise ConfigError(f"{path}: must be at most 64 characters")


def _check_unique_ids(agents: list[AgentConfig], babysitter: BabysitterConfig) -> None:
    seen: set[str] = set()
    for agent in agents:
        if agent.id in seen:
            raise ConfigError(f"agents: duplicate id {agent.id!r}")
        seen.add(agent.id)
    if babysitter.enabled and babysitter.id is not None:
        if babysitter.id in seen:
            raise ConfigError(f"babysitter.id: must be unique; conflicts with {babysitter.id!r}")


def _reject_unknown(obj: dict[str, Any], allowed: set[str], *, path: str) -> None:
    for key in obj:
        if key not in allowed:
            prefix = f"{path}." if path else ""
            raise ConfigError(f"{prefix}{key}: unknown field")


def _require_dict(raw: object, *, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        label = path or "config"
        raise ConfigError(f"{label}: must be a mapping")
    return raw


def _require_str(obj: dict[str, Any], key: str, *, path: str) -> str:
    if key not in obj:
        raise ConfigError(f"{path}: required field")
    value = obj[key]
    if not isinstance(value, str):
        raise ConfigError(f"{path}: must be a string")
    return value


def _require_int(obj: dict[str, Any], key: str, *, path: str) -> int:
    if key not in obj:
        raise ConfigError(f"{path}: required field")
    value = obj[key]
    if type(value) is not int:
        raise ConfigError(f"{path}: must be an integer")
    return value


def _optional_int(obj: dict[str, Any], key: str, *, default: int, path: str) -> int:
    if key not in obj:
        return default
    value = obj[key]
    if type(value) is not int:
        raise ConfigError(f"{path}: must be an integer")
    return value
