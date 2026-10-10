# Config

| Features | ADRs |
|----------|------|
| [01](../feature/01-project-bootstrap-and-config.md), [03](../feature/03-connector-interface-and-github.md), [08](../feature/08-cli-and-dashboard.md) | [002](../adr/002-2-tech-stack-and-dependencies.md), [003](../adr/003-3-config-load-and-bootstrap-sequence.md) |

Canonical product schema: feature [01](../feature/01-project-bootstrap-and-config.md). This document is the implementable validation shape, defaults, and precedence.

## Location

```text
{project_root}/.orkie/config.yaml
```

Only config file. Loaded with `yaml.safe_load`. Unknown fields at any validated object level **fail** validation. Config is immutable for the process lifetime after load; file edits require restart.

Secrets are never read from `.orkie/`.

## Precedence

Highest wins:

| Concern | Order |
|---------|-------|
| Dashboard port | CLI `--port` → `dashboard_port` in YAML → default `8765` |
| Repository identity | `connector.repo` → GitHub `origin` remote → sole GitHub remote → fail (tell operator to set `connector.repo`) |
| GitHub token | Environment `GITHUB_TOKEN` only (required non-empty for GitHub connector) |
| Poll interval | YAML `poll_interval_seconds` → default `60` (still must be ≥ 15) |
| Session caps | YAML per-agent / global → default `1` each |
| Agent command / prompt | YAML `command` or `command_ref` (resolved against builtins + `commands`); no Orkie role catalog |
| Interactive prompts | Allowed only when stdin and stdout are TTYs; no CLI override flag |

## Top-level shape

```yaml
version: 1
connector:
  type: github
  repo: owner/name          # optional
poll_interval_seconds: 60   # optional
issue_labels:
  - orkie
max_concurrent_sessions: 1  # optional
dashboard_port: 8765        # optional
prompt_root: .              # optional; base for prompt_file
commands:                   # optional project presets
  my_fork: [opencode, acp, --foo]
agents:
  - id: worker
    name: Worker
    role: worker
    command_ref: opencode   # XOR command: [opencode, acp]
    max_concurrent_sessions: 1
    prompt: |
      …
    # XOR prompt_file: relative/path.md
    triggers:
      - type: any
      # or: {type: labels, labels: [a, b]}
babysitter:
  enabled: false
  # when enabled: id, name, role, command XOR command_ref, prompt XOR prompt_file
```

### Top-level fields

| Field | Required | Default | Validation |
|-------|----------|---------|------------|
| `version` | yes | — | Must be integer `1` |
| `connector` | yes | — | Object; see below |
| `poll_interval_seconds` | no | `60` | Integer ≥ `15` |
| `issue_labels` | yes | — | Non-empty list of unique label names; each non-empty, ≤ 50 chars |
| `max_concurrent_sessions` | no | `1` | Integer ≥ `1`. Ceiling on working issue sessions |
| `dashboard_port` | no | `8765` | Integer `1`–`65535` |
| `prompt_root` | no | `.` | Non-empty relative path under the project root; reject absolute or `..` escape. Base directory for every `prompt_file` |
| `commands` | no | — | Object map; see [Command presets](#command-presets) |
| `agents` | yes | — | Non-empty list of agent objects |
| `babysitter` | no | `{enabled: false}` | Object; see below |

### Command presets

Exactly one of `command` or `command_ref` on each agent and on the enabled babysitter. Resolve `command_ref` at load; `AgentConfig.command` / babysitter `command` are always argv lists afterward.

**Built-in** (reserved; always available):

| Name | Argv |
|------|------|
| `cursor` | `[agent, acp]` |
| `opencode` | `[opencode, acp]` |
| `grok` | `[grok, agent, --always-approve, stdio]` |

Optional `commands`: each key non-empty, no whitespace, ≤ 64 chars; each value a non-empty argv list. Key colliding with a built-in name → fail. Unknown `command_ref` → fail. Unused custom names allowed.

### `connector`

| Field | Required | Validation |
|-------|----------|------------|
| `type` | yes | Exactly `github` in v1 |
| `repo` | no | `owner/name`: one slash, both sides non-empty |

### Agent object

| Field | Required | Default | Validation |
|-------|----------|---------|------------|
| `id` | yes | — | Unique among agents and enabled babysitter; non-empty; no whitespace; ≤ 64 chars |
| `name` | yes | — | Non-empty string |
| `role` | yes | — | Non-empty string; display/metadata only; not an enum |
| `command` | XOR | — | Exactly one of `command` or `command_ref`. Non-empty list of strings; `[0]` is executable |
| `command_ref` | XOR | — | Non-empty string; built-in or project `commands` name |
| `max_concurrent_sessions` | no | `1` | Integer ≥ `1` |
| `prompt` | XOR | — | Exactly one of `prompt` or `prompt_file` |
| `prompt_file` | XOR | — | Relative path under `prompt_root`; reject absolute or `..` escape; resolved path must stay under the project root |
| `triggers` | yes | — | Non-empty list of trigger objects |

### Trigger object

| `type` | Extra | Match |
|--------|-------|-------|
| `any` | none | Every intake issue |
| `labels` | `labels`: non-empty string list | Issue has every listed label |

An agent matches an issue when **any** of its triggers matches. Evaluated on current issue state each poll.

### Babysitter object

| Field | Required | Default | Validation |
|-------|----------|---------|------------|
| `enabled` | no | `false` | Boolean |
| `id` | when enabled | — | Same rules as agent `id`; unique vs agents |
| `name` | when enabled | — | Non-empty |
| `role` | when enabled | — | Non-empty |
| `command` / `command_ref` | when enabled | — | Exactly one; same rules as agent |
| `prompt` / `prompt_file` | when enabled | — | Exactly one |

When `enabled` is `false`, other babysitter fields are **ignored** (not validated for uniqueness or shape). No issue triggers. No `max_concurrent_sessions` field — Orkie enforces at most one babysitter session and excludes it from issue caps.

## Prompt tokens

Substitution owned by `orkie.config.substitute_prompt`. Replace every token below; other text unchanged. No other templating engine.

| Token | Issue session | Babysitter session |
|-------|---------------|--------------------|
| `__ISSUENO__` | Issue number as decimal string | empty string |
| `__ISSUE_TITLE__` | Title | empty |
| `__ISSUE_BODY__` | Body | empty |
| `__ISSUE_URL__` | URL | empty |
| `__ISSUE_LABELS__` | Comma-separated labels | empty |
| `__PRNO__` | empty | PR number as decimal string |
| `__PR_TITLE__` | empty | Title |
| `__PR_URL__` | empty | URL |
| `__PR_BRANCH__` | empty | Head branch |
| `__PR_BASE__` | empty | Base branch |
| `__PR_MERGE_STATE__` | empty | Connector `mergeable_state` string |
| `__AGENT_ID__` | Config `id` | Config `id` |
| `__AGENT_NAME__` | Config `name` | Config `name` |
| `__SESSION_ID__` | Orkie session id | Orkie session id |
| `__REPO__` | `owner/name` | `owner/name` |

## Session caps (effective room)

```text
room(agent) = min(
  agent.max_concurrent_sessions - working_sessions(agent),
  config.max_concurrent_sessions - working_issue_sessions_all_agents
)
```

Babysitter sessions do not count. Failed spawns do not count. A saved claim with no working session does not count. Defaults 1/1 mean at most one working issue session process-wide.

## Default scaffold

Interactive accept writes **exactly** this document (not `yaml.safe_dump` of a dict):

```yaml
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
```

After write, load it as normal config (no special mode).

## Documented first-class agent commands

Not exclusive; any ACP-compatible argv uses the same path. Built-in `command_ref` names:

| Agent | `command_ref` | Argv |
|-------|---------------|------|
| OpenCode | `opencode` | `[opencode, acp]` |
| Grok Build | `grok` | `[grok, agent, --always-approve, stdio]` |
| Cursor | `cursor` | `[agent, acp]` |

## Environment

| Variable | Required | Meaning |
|----------|----------|---------|
| `GITHUB_TOKEN` | yes (GitHub connector) | Bearer token; never stored under `.orkie/` |

## Validation error style

Messages name the field path (e.g. `agents[0].prompt`) and the rule violated. Bootstrap fails before lock when config is present but invalid. Missing-config offer applies only when the file is absent, never when it is broken.

## Mapping to components

| Concern | Module |
|---------|--------|
| Load / validate / scaffold / substitute | `orkie.config` |
| Port override | `orkie.cli` |
| Repo resolution | `orkie.connectors` (`resolve_github_repo`) |
| Token read | `orkie.cli` bootstrap → connector / acp env |
