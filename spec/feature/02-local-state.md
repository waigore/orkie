# Feature: Local State

## Description

Orkie persists project-related runtime state outside the Git repository, in a per-user, tool-owned location under the operator's home directory: `~/.local/share/orkie/<owner>--<repo>/`, where `<owner>` and `<repo>` are the resolved GitHub repository. This state includes the known intake-issue snapshot used for delta comparison, session records, spawn-failure records, a process lock, and per-agent logs needed by the dashboard.

The claim is the remote claim label. Orkie does not store a local claim. A **session record** says which config agent a spawn bound to one issue or one PR, and whether that ACP process is working. After a process start, no session is working until orchestration spawns one. The label does not encode the agent id or the session id; a working session supplies the agent (see [05-agent-orchestration.md](05-agent-orchestration.md)).

Because state is per user and machine, starting Orkie under a different OS account or on a different machine uses a separate state tree and does not share prior local knowledge. Two clones of the same GitHub repository on one machine share this directory. A second live Orkie for that project refuses to start (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md)).

The [state layout](#state-layout) below is the single source of truth for on-disk fields. Intake, orchestration, and the dashboard all use this layout.

## Use cases

Actors are defined in [users.md](users.md).

- **Operator**: Runs Orkie continuously and expects sessions and spawn failures to survive polls and crashes without rewriting the project repo. On another machine or OS account, accepts a fresh local state; claim labels on the tracker are reconciled per [05-agent-orchestration.md](05-agent-orchestration.md).
- **Dashboard user**: Views agent and issue status and logs sourced from local state and live ACP sessions.

## State layout

Root: `~/.local/share/orkie/<owner>--<repo>/` (under the user's home directory on every platform).

| Path / record | Purpose |
|---------------|---------|
| `lock` | Process lock: holder pid and start time. One live Orkie per GitHub repository. |
| `snapshot` | Last good intake snapshot (see below). |
| `sessions` | Session records (see below). |
| `spawn_failures` | Spawn-failure records (see below). |
| `logs/<agent_id>.log` | Append-only agent log for that config identity. Session ids are marked in the log lines; there is no per-session log file. |

### Intake snapshot fields

| Field | Meaning |
|-------|---------|
| `fetched_at` | Timestamp of the last successful intake fetch. |
| `issues[]` | Open non-PR intake issues from that fetch. |
| `issues[].number` | Issue number. |
| `issues[].title` | Title. |
| `issues[].body` | Body. |
| `issues[].url` | HTML URL. |
| `issues[].state` | Open/closed as reported by the connector. |
| `issues[].labels` | Label names on the issue, including the claim label when present. |

### Session record fields

| Field | Meaning |
|-------|---------|
| `session_id` | Generated session identity. |
| `agent_id` | Config agent or babysitter `id`. |
| `issue_number` | Bound issue number, or empty for a babysitter session. |
| `pr_number` | Bound PR number, or empty for an issue session. |
| `working` | Whether the ACP process for this session is running. |
| `worktree_path` | Dedicated git worktree path for this session. |
| `started_at` | When the session last became working. |

### Spawn-failure record fields

| Field | Meaning |
|-------|---------|
| `agent_id` | Config id that failed to spawn. |
| `agent_name` | Display name at failure time. |
| `issue_number` | Issue number, or empty for babysitter. |
| `pr_number` | PR number, or empty for issue agents. |
| `attempt` | Which consecutive attempt this failure was (`1`–`3`) for that issue or PR. |
| `released` | True when three failures caused Orkie to remove the claim label (issue agents only). |
| `error` | Redacted error text (never contains `GITHUB_TOKEN`). |
| `at` | Timestamp. |

### Process lock fields

| Field | Meaning |
|-------|---------|
| `pid` | Holder process id. |
| `started_at` | When the holder took the lock. |

### Agent log format

Each line in `logs/<agent_id>.log` includes a clear `session_id=` marker (and issue or PR number when known) so the dashboard can filter by session without a separate file per session. Logs are kept in full for the life of the project state directory; there is no size cap in v1. Stored lines never contain the `GITHUB_TOKEN` value.

## User stories

### Store state under the per-user Orkie directory

**Given** a successfully bootstrapped project whose GitHub repository is `owner/repo`  
**When** Orkie needs to persist the issue snapshot, session records, spawn failures, or logs  
**Then** data is written under `~/.local/share/orkie/owner--repo/` and not into the project's Git working tree as the primary state store

### Isolate state by account and machine

**Given** the same Git project cloned on two machines (or used by two OS accounts)  
**When** Orkie runs on each  
**Then** each run uses its own `~/.local/share/orkie/<owner>--<repo>/` tree. Changes on one do not appear on the other

### A session binds one issue

**Given** orchestration has applied the claim label for an issue and spawned a session  
**When** local state is updated  
**Then** the session record stores the session id, the config agent id, that issue, and that the session is working. No local claim is written

### A restart clears working state

**Given** session records were persisted before the process stopped  
**When** Orkie starts again for the same project by the same user on the same machine  
**Then** it reloads the snapshot, sessions, and spawn failures, and it treats every session as not working until a new spawn. It does not treat a stored working flag as evidence that a process is still alive. Claim labels are read from the tracker on the next fetch

### A crash leaves the claim on the tracker

**Given** orchestration has applied the claim label and the process stops before a session is working  
**When** the same user starts Orkie again  
**Then** the label is still on the issue, and the next fetch is what tells orchestration the issue is claimed

### Retain agent logs for the dashboard

**Given** one or more sessions are or were active  
**When** an operator opens the local web dashboard  
**Then** status and log information are read from `logs/<agent_id>.log` and live ACP data where supported, with session ids visible in the log lines

### Append to a per-agent log

**Given** a session produces log output  
**When** Orkie stores that log  
**Then** it appends to `logs/<agent_id>.log` with a clear session id marker, stores no copy of the `GITHUB_TOKEN` value, and does not truncate by size

### Record a spawn failure until resolved

**Given** a spawn attempt for a config agent and an issue, or for the babysitter and a PR, fails  
**When** local state is updated  
**Then** a spawn-failure record stores the fields in [Spawn-failure record fields](#spawn-failure-record-fields). Those records are the consecutive attempt history. The dashboard can read them. Issue attempts follow the three-strike rule in [05-agent-orchestration.md](05-agent-orchestration.md)

### Graceful shutdown leaves no working session

**Given** Orkie is shutting down via SIGINT or SIGTERM and has removed the claim labels for the issue sessions it stopped (see [05-agent-orchestration.md](05-agent-orchestration.md))  
**When** the shutdown flush runs  
**Then** no session is stored as working

### A failed label removal stays on the tracker

**Given** graceful shutdown could not remove one or more claim labels  
**When** the shutdown flush runs  
**Then** those labels remain on the issues and every session is stored as not working. The next start reads the labels from the tracker and reconciles them under the swarm-fit rules in [05-agent-orchestration.md](05-agent-orchestration.md)

## Acceptance criteria

- [ ] Default local state root is `~/.local/share/orkie/<owner>--<repo>/` under the user's home directory, using the resolved GitHub owner and repository name.
- [ ] Project id is stable for that GitHub repository and is shared by clones of it on the same machine and OS account.
- [ ] On-disk layout and record fields match [State layout](#state-layout). Intake, orchestration, and the dashboard share that layout.
- [ ] Agent logs live at `logs/<agent_id>.log`, mark session ids in-line, are not size-capped in v1, and never store the `GITHUB_TOKEN` value.
- [ ] The claim is only the remote claim label. Local state has no claim record. Process start marks every session not working.
- [ ] Spawn-failure records are the consecutive attempt history for an issue or PR.
- [ ] The Git project tree is not the primary store for orchestration runtime state.
- [ ] State is not shared across OS users or machines. This isolation is documented.
- [ ] After a restart on the same user and machine, Orkie reloads the last persisted snapshot, sessions, and spawn failures.
- [ ] Graceful shutdown flushes local state before exit so no session is stored as working. A label that could not be removed is still on the tracker.
