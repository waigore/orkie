# Feature: Project Bootstrap and Config

## Description

Orkie starts against a target Git project, discovers that project's `.orkie/` configuration directory, and loads [`.orkie/config.yaml`](#config-schema). That file defines the GitHub connector, the labels that mark intake issues, the single claim label, session caps, agents (config identity, command, prompt, triggers), and the optional PR babysitter. If `.orkie/` or `config.yaml` is missing, bootstrap offers to create a basic default config the operator can accept or reject. The default config defines one agent that handles one open issue at a time, among issues that carry the default issue label. Bootstrap validates that the config is usable and prepares the runtime for continuous orchestration. Secrets and tokens are never stored in `.orkie/`; the GitHub token comes from the `GITHUB_TOKEN` environment variable (see [03-connector-interface-and-github.md](03-connector-interface-and-github.md)).

Config is loaded at bootstrap and applies for that process. Editing the file during a run has no effect until the next start.

## Users and use cases

- **Project maintainer**: Adds or customizes `.orkie/config.yaml` so Orkie can run in the repository without code changes to Orkie itself.
- **First-time operator**: Starts Orkie in a repo without config and can accept a default config to get running quickly, or reject creation and stop.
- **Operator**: Starts Orkie via the CLI against a project path (or from inside the project) and expects a clear success or failure during bootstrap.
- **Architect / agent author**: Relies on project-owned YAML for roles and prompts. Orkie does not hard-code agent roles beyond the optional default scaffold.

## User stories

### Discover and load `.orkie` config

**Given** a Git repository that contains `.orkie/config.yaml` with a valid configuration  
**When** Orkie is started pointing at that project (or from within it)  
**Then** Orkie loads the configuration, applies it for this run, and proceeds to subsequent bootstrap steps (local state, connector checks, orchestration loop)

### Offer default config when config is missing

**Given** a Git repository that has no `.orkie/` directory, or a `.orkie/` directory with no `config.yaml`  
**When** Orkie is started against that directory  
**Then** bootstrap prompts the operator to create a basic default config and does not silently invent config without consent

### Accept default config creation

**Given** Orkie has offered to create a default config because none exists  
**When** the operator accepts  
**Then** Orkie writes `.orkie/config.yaml` as specified in [Default scaffold](#default-scaffold), then continues bootstrap using that config

### Reject default config creation

**Given** Orkie has offered to create a default config because none exists  
**When** the operator rejects the offer  
**Then** Orkie does not create config files, bootstrap ends without starting the orchestration loop, and the operator is informed that configuration is required

### Default config is a normal project config

**Given** a default config was just created and accepted  
**When** bootstrap continues  
**Then** the default file is treated like any other project config and is not a special locked-in mode

### Validate YAML shape

**Given** `.orkie/config.yaml` is malformed, uses an unknown field, or misses a required field  
**When** Orkie attempts bootstrap  
**Then** bootstrap fails with an actionable validation error identifying the field or parse error, and no agents are spawned

### Config owns agent identity and behavior boundaries

**Given** project YAML that defines one or more agents with config identity, command, and prompt  
**When** bootstrap completes successfully  
**Then** those definitions are available to orchestration. What agents may or may not do is expressed only through project prompt and settings, not through an Orkie role catalog

### Credentials stay outside the repo config tree

**Given** a project with `.orkie/config.yaml`  
**When** an operator stores or expects API tokens inside `.orkie/`  
**Then** Orkie does not treat `.orkie/` as a credential store. Bootstrap reads the GitHub token from `GITHUB_TOKEN`

### Claim label is configurable or defaulted

**Given** project YAML may set `claim_label`  
**When** bootstrap loads config  
**Then** Orkie uses that label name when set, otherwise `orkie:claimed`, and that single name is available to orchestration (see [05-agent-orchestration.md](05-agent-orchestration.md))

### Missing claim label is created or bootstrap fails

**Given** the resolved claim label does not already exist on the GitHub repository  
**When** bootstrap prepares the connector  
**Then** Orkie creates that label when the token has permission to create labels. When the token does not, bootstrap fails before the loop starts and the error states the label name and that label-creation permission is required

### Related prompt files live under `.orkie/`

**Given** an agent or babysitter uses `prompt_file`  
**When** bootstrap loads config  
**Then** Orkie reads that file from inside `.orkie/` and rejects a path that is absolute or that escapes `.orkie/`

## Config schema

The only config file is `.orkie/config.yaml`. `version` must be `1`. Unknown fields fail validation. Omitted optional fields use the defaults in the table below.

### Top level

| Field | Required | Default | Meaning |
|-------|----------|---------|---------|
| `version` | yes | | Schema version. Must be `1`. |
| `connector` | yes | | Connector selection. See below. |
| `poll_interval_seconds` | no | `60` | Intake and PR poll interval. Integer `>= 15`. |
| `issue_labels` | yes | | One or more GitHub label names. An open issue is an intake issue when it is not a pull request and has at least one of these labels. |
| `claim_label` | no | `orkie:claimed` | The single claim label Orkie applies to an issue it has claimed. |
| `max_concurrent_sessions` | no | `1` | Global ceiling on issue sessions across all agents. Integer `>= 1`. |
| `agents` | yes | | One or more agent definitions. |
| `babysitter` | no | `{enabled: false}` | Optional PR babysitter. |

`issue_labels` and `claim_label` are GitHub label names: non-empty and at most 50 characters. Names in `issue_labels` are unique.

`connector`:

| Field | Required | Meaning |
|-------|----------|---------|
| `type` | yes | `github` in v1. Any other value fails validation. |
| `repo` | no | `owner/name` of the GitHub repository, one slash, both sides non-empty. When omitted, bootstrap resolves it as in [03-connector-interface-and-github.md](03-connector-interface-and-github.md). |

### Agent definition

Each entry in `agents` is one config identity. It is not a live session.

| Field | Required | Default | Meaning |
|-------|----------|---------|---------|
| `id` | yes | | Config identity. Unique among agents and the babysitter. Non-empty, no whitespace, at most 64 characters. |
| `name` | yes | | Display name. |
| `role` | yes | | Project-defined role string. Not an enum. |
| `command` | yes | | Non-empty argument list used to spawn the ACP agent. The first item is the executable. |
| `max_concurrent_sessions` | no | `1` | Ceiling for live sessions of this config identity. Integer `>= 1`. The global ceiling still applies. |
| `prompt` | one of `prompt` or `prompt_file` | | Inline prompt template. |
| `prompt_file` | one of `prompt` or `prompt_file` | | Path relative to `.orkie/` for the prompt template. |
| `triggers` | yes | | One or more spawn predicates. See below. |

A trigger entry is one of:

| `type` | Extra fields | Match |
|--------|----------------|-------|
| `any` | none | Every current intake issue. |
| `labels` | `labels`: one or more label names | The intake issue has every listed label. |

An agent matches an issue when any one of its trigger entries matches. Trigger match is evaluated on current issue state at each poll. A label or open/closed change matters because it changes that result.

### Babysitter definition

| Field | Required | Default | Meaning |
|-------|----------|---------|---------|
| `enabled` | no | `false` | When `false`, Orkie does not manage pull requests. Other babysitter fields are ignored. |
| `id` | when enabled | | Config identity. Same constraints as an agent `id`, and unique across agents. |
| `name` | when enabled | | Display name. |
| `role` | when enabled | | Project-defined role string. |
| `command` | when enabled | | ACP argument list, same rule as an agent `command`. |
| `prompt` or `prompt_file` | when enabled | | Prompt template. Orkie still assigns only one PR per session. The prompt should tell the agent to work only on that PR. |

The babysitter has no issue triggers and no `max_concurrent_sessions`. Orkie runs at most one babysitter session, and that session does not consume issue session caps.

### Prompt variables

Orkie substitutes these tokens in the prompt text before the ACP session receives it. Any other text is unchanged.

| Token | Issue session | Babysitter session |
|-------|---------------|--------------------|
| `__ISSUENO__` | Issue number | empty |
| `__ISSUE_TITLE__` | Issue title | empty |
| `__ISSUE_BODY__` | Issue body | empty |
| `__ISSUE_URL__` | Issue URL | empty |
| `__ISSUE_LABELS__` | Comma-separated labels | empty |
| `__PRNO__` | empty | PR number |
| `__PR_TITLE__` | empty | PR title |
| `__PR_URL__` | empty | PR URL |
| `__PR_BRANCH__` | empty | Head branch name |
| `__PR_BASE__` | empty | Base branch name |
| `__PR_MERGE_STATE__` | empty | Connector mergeable state |
| `__AGENT_ID__` | Config `id` | Config `id` |
| `__AGENT_NAME__` | Config `name` | Config `name` |
| `__SESSION_ID__` | Session id | Session id |
| `__REPO__` | `owner/name` | `owner/name` |

A session is bound to one issue or one PR. The project prompt can tell the agent to do otherwise. Orkie still tracks only the bound work item. What the agent does beyond that is undefined.

### Default scaffold

Accepting the offer writes `.orkie/config.yaml` with exactly this content:

```yaml
version: 1
connector:
  type: github
poll_interval_seconds: 60
issue_labels:
  - orkie
claim_label: orkie:claimed
max_concurrent_sessions: 1
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

The default issue label is `orkie`. The default agent command is OpenCode's ACP entry. Grok Build is selected by changing `command` as documented in [04-acp-agent-runtime.md](04-acp-agent-runtime.md).

### Session caps

- Each agent definition allows at most its `max_concurrent_sessions` live issue sessions. Omitted means 1.
- The project `max_concurrent_sessions` is a hard ceiling on live issue sessions across every agent. Omitted means 1.
- The effective room for an agent is the smaller of its remaining per-agent room and the remaining global room.
- Raising a per-agent limit while the global limit stays `1` still yields one issue session.
- Values above 1 are valid. The operator accepts the risk of concurrent agents.
- The babysitter session does not count toward either ceiling.

## Acceptance criteria

- [ ] Orkie resolves a target project directory from the CLI argument or the current working directory (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md)).
- [ ] Config is `.orkie/config.yaml` and matches the schema in this feature, including defaults, prompt variables, and session caps.
- [ ] When that file is missing, bootstrap interactively offers to create it and does not write it without an explicit accept.
- [ ] The operator can reject the offer. On reject, no config is created and the orchestration loop does not start.
- [ ] On accept, Orkie writes the default scaffold in this feature.
- [ ] Invalid or incomplete config fails bootstrap before the continuous loop starts. Errors name the problem. The default offer applies only when config is absent, not when it is present and broken.
- [ ] Agent roles remain project-defined. The default scaffold is only a starting template.
- [ ] Tokens and secrets are not read from `.orkie/`. `GITHUB_TOKEN` is required. A missing or empty token fails bootstrap. If `claim_label` does not exist on the repo and the token cannot create labels, bootstrap fails with an error that names the label and the missing label-creation permission. Missing issue read, label add or remove, or pull-request read when the babysitter is enabled also fails bootstrap (see [03-connector-interface-and-github.md](03-connector-interface-and-github.md)).
- [ ] `poll_interval_seconds` defaults to 60 and must be an integer greater than or equal to 15.
- [ ] Optional `connector.repo` is `owner/name`. When it is omitted, repository resolution follows [03-connector-interface-and-github.md](03-connector-interface-and-github.md).
- [ ] `issue_labels` selects intake issues. Pull requests are not intake issues (see [06-work-intake-and-issue-monitoring.md](06-work-intake-and-issue-monitoring.md)).
- [ ] Successful bootstrap initializes or attaches per-user local state for the project (see [02-local-state.md](02-local-state.md)) before entering the continuous orchestration loop.
- [ ] Config loaded at bootstrap stays in effect until the process exits.
