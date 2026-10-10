# Configuration

Project settings live only in:

```text
{project_root}/.orkie/config.yaml
```

Loaded once at bootstrap. Edit the file, then restart Orkie for changes to take effect. Unknown fields fail validation. Optional fields use the defaults below.

Canonical schema: [feature 01](../spec/feature/01-project-bootstrap-and-config.md). Shape and defaults used by the implementation: [design config](../spec/design/config.md).

## Minimal example

```yaml
version: 1
connector:
  type: github
  # repo: owner/name   # optional; otherwise resolved from git remotes
poll_interval_seconds: 60
issue_labels:
  - orkie
max_concurrent_sessions: 1
dashboard_port: 8765
agents:
  - id: worker
    name: Worker
    role: worker
    command: [opencode, acp]
    max_concurrent_sessions: 1
    prompt: |
      You are working on issue #__ISSUENO__: __ISSUE_TITLE__
      __ISSUE_URL__

      __ISSUE_BODY__

      Handle only this issue.
    triggers:
      - type: any
babysitter:
  enabled: false
```

## Top-level fields

| Field | Required | Default | Notes |
|-------|----------|---------|--------|
| `version` | yes | — | Must be `1` |
| `connector` | yes | — | `type: github`; optional `repo: owner/name` |
| `poll_interval_seconds` | no | `60` | Integer ≥ 15 |
| `issue_labels` | yes | — | Open non-PR issues with any of these labels are intake |
| `max_concurrent_sessions` | no | `1` | Global ceiling on working **issue** sessions |
| `dashboard_port` | no | `8765` | Overridable with CLI `--port` |
| `prompt_root` | no | `.` | Base directory for `prompt_file` paths; relative to the project root (no `..` escape) |
| `agents` | yes | — | At least one agent definition |
| `babysitter` | no | `{enabled: false}` | Optional PR babysitter |

### Repository identity

Precedence: `connector.repo` → GitHub `origin` → sole GitHub remote → fail (set `connector.repo`).

### Secrets

| Variable | Required |
|----------|----------|
| `GITHUB_TOKEN` | Yes for the GitHub connector |

## Agents

Each `agents[]` entry is a **config identity** (not a live session). Orkie assigns at most one issue per session.

| Field | Required | Notes |
|-------|----------|--------|
| `id` | yes | Unique vs other agents and enabled babysitter; no whitespace; ≤ 64 chars |
| `name` | yes | Display name |
| `role` | yes | Project metadata only; not an Orkie enum |
| `command` | yes | Non-empty argv; first element is the executable |
| `max_concurrent_sessions` | no | Default `1`; still limited by the global cap |
| `prompt` **or** `prompt_file` | exactly one | Inline template, or path relative to `prompt_root` (no `..` escape; must stay under the project root) |
| `triggers` | yes | At least one trigger |

### Triggers

An agent matches an intake issue when **any** trigger matches (re-evaluated each poll):

| `type` | Extra | Match |
|--------|-------|--------|
| `any` | — | Every intake issue |
| `labels` | `labels: […]` | Issue has every listed label |

### First-class agent commands

Any ACP-compatible command works; these are documented defaults:

| Agent | `command` |
|-------|-----------|
| OpenCode | `[opencode, acp]` |
| Grok Build | `[grok, agent, --always-approve, stdio]` |

See [feature 04](../spec/feature/04-acp-agent-runtime.md).

### Prompt tokens

Substituted before the session receives the prompt. Unlisted text is unchanged.

| Token | Issue session | Babysitter session |
|-------|---------------|--------------------|
| `__ISSUENO__` | Issue number | empty |
| `__ISSUE_TITLE__` | Title | empty |
| `__ISSUE_BODY__` | Body | empty |
| `__ISSUE_URL__` | URL | empty |
| `__ISSUE_LABELS__` | Comma-separated labels | empty |
| `__PRNO__` | empty | PR number |
| `__PR_TITLE__` | empty | Title |
| `__PR_URL__` | empty | URL |
| `__PR_BRANCH__` | empty | Head branch |
| `__PR_BASE__` | empty | Base branch |
| `__PR_MERGE_STATE__` | empty | Connector mergeable state |
| `__AGENT_ID__` | Config `id` | Config `id` |
| `__AGENT_NAME__` | Config `name` | Config `name` |
| `__SESSION_ID__` | Session id | Session id |
| `__REPO__` | `owner/name` | `owner/name` |

Keep prompts scoped to the bound issue or PR. Orkie tracks only that assignment.

### Session caps

Effective room for an agent is the minimum of remaining per-agent and remaining global issue-session room. Defaults of `1` / `1` mean one working issue session process-wide. The babysitter session does not count toward either ceiling.

## PR babysitter

When `babysitter.enabled` is `true`, supply `id`, `name`, `role`, `command`, and exactly one of `prompt` / `prompt_file`. Orkie runs at most one babysitter session, bound to one selectable blocked PR. It does not merge PRs. When `enabled` is `false`, other babysitter fields are ignored.

Details: [feature 07](../spec/feature/07-pr-babysitter.md).

## Permissions

While a session runs, Orkie grants every ACP permission request automatically and logs each grant. Behavioral limits belong in project prompts and agent settings, not in interactive approval during the loop.
