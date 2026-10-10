# Config

| Features | ADRs |
|----------|------|
| [01](../feature/01-project-bootstrap-and-config.md), [03](../feature/03-connector-interface-and-github.md), [08](../feature/08-cli-and-dashboard.md) | [002](../adr/002-1-tech-stack-and-dependencies.md), [003](../adr/003-1-config-load-and-bootstrap-sequence.md) |

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
| Claim label name | YAML `claim_label` → default `orkie:claimed` |
| Poll interval | YAML `poll_interval_seconds` → default `60` (still must be ≥ 15) |
| Session caps | YAML per-agent / global → default `1` each |
| Agent command / prompt | YAML only (no Orkie role catalog) |
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
claim_label: orkie:claimed  # optional
max_concurrent_sessions: 1  # optional
dashboard_port: 8765        # optional
agents:
  - id: worker
    name: Worker
    role: worker
    command: [opencode, acp]
    max_concurrent_sessions: 1
    prompt: |
      …
    # XOR prompt_file: relative/path.md
    triggers:
      - type: any
      # or: {type: labels, labels: [a, b]}
babysitter:
  enabled: false
  # when enabled: id, name, role, command, prompt XOR prompt_file
```

### Top-level fields

| Field | Required | Default | Validation |
|-------|----------|---------|------------|
| `version` | yes | — | Must be integer `1` |
| `connector` | yes | — | Object; see below |
| `poll_interval_seconds` | no | `60` | Integer ≥ `15` |
| `issue_labels` | yes | — | Non-empty list of unique label names; each non-empty, ≤ 50 chars |
| `claim_label` | no | `orkie:claimed` | Non-empty, ≤ 50 chars; must not appear in `issue_labels` |
| `max_concurrent_sessions` | no | `1` | Integer ≥ `1` |
| `dashboard_port` | no | `8765` | Integer `1`–`65535` |
| `agents` | yes | — | Non-empty list of agent objects |
| `babysitter` | no | `{enabled: false}` | Object; see below |

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
| `command` | yes | — | Non-empty list of strings; `[0]` is executable |
| `max_concurrent_sessions` | no | `1` | Integer ≥ `1` |
| `prompt` | XOR | — | Exactly one of `prompt` or `prompt_file` |
| `prompt_file` | XOR | — | Relative path under `.orkie/` only; reject absolute or `..` escape |
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
| `command` | when enabled | — | Same as agent `command` |
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

Babysitter sessions do not count. Failed spawns do not count. Defaults 1/1 mean at most one issue session process-wide.

## Default scaffold

Interactive accept writes **exactly** this document (not `yaml.safe_dump` of a dict):

```yaml
version: 1
connector:
  type: github
poll_interval_seconds: 60
issue_labels:
  - orkie
claim_label: orkie:claimed
max_concurrent_sessions: 1
dashboard_port: 8765
agents:
  - id: worker
    name: Worker
    role: worker
    command:
      - opencode
      - acp
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

Not exclusive; any ACP-compatible `command` uses the same path:

| Agent | `command` |
|-------|-----------|
| OpenCode | `[opencode, acp]` |
| Grok Build | `[grok, agent, --always-approve, stdio]` |

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
