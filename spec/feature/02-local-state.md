# Feature: Local State

## Description

Orkie persists project-related runtime state outside the Git repository, in a per-user, tool-owned location under the operator's home directory: `~/.local/share/orkie/<owner>--<repo>/`, where `<owner>` and `<repo>` are the resolved GitHub repository. This state includes the known intake-issue snapshot used for delta comparison, local claims, spawn-failure records, a process lock, and per-agent logs needed by the dashboard.

A **claim** is Orkie's assignment of one config agent to one issue. It is the source of truth for which issue Orkie will spawn next. Claims survive process stop and crash. A **session record** says which config agent a live spawn bound to one issue or one PR. Session records and ACP transcripts are discarded on both shutdown modes and on the next start. A new spawn is a new session. After a process start, no session is working until orchestration spawns one.

Because state is per user and machine, starting Orkie under a different OS account or on a different machine uses a separate state tree. That run does not see this machine's claims. Two clones of the same GitHub repository on one machine share this directory. A second live Orkie for that project refuses to start (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md)).

The [state layout](#state-layout) below is the single source of truth for on-disk fields. Intake, orchestration, and the dashboard all use this layout.

## Use cases

Actors are defined in [users.md](users.md).

- **Operator**: Runs Orkie continuously and expects claims, the intake snapshot, and spawn failures to survive polls, shutdown, and crashes without rewriting the project repo. On another machine or OS account, accepts a fresh local state, including an empty claim set.
- **Dashboard user**: Views agent and issue status, permission grants, and logs sourced from local state and live ACP sessions.

## State layout

Root: `~/.local/share/orkie/<owner>--<repo>/` (under the user's home directory on every platform).

| Path / record | Kept across stop and start | Purpose |
|---------------|----------------------------|---------|
| `lock` | Yes | Process lock: holder pid and start time. One live Orkie per GitHub repository. |
| `snapshot` | Yes | Last good intake snapshot (see below). |
| `claims` | Yes | Local claim records (see below). |
| `spawn_failures` | Yes | Spawn-failure records (see below). |
| `logs/<agent_id>.log` | Yes | Append-only agent log for that config identity. |
| `sessions` | No | Live session records. Deleted on shutdown and discarded at the next start. |
| `worktrees/<session_id>/` | No | Dedicated git worktree. Removed when the session ends, and leftovers are removed at the next start. |

### Claim record fields

At most one claim per issue. The claim is not keyed by session id.

| Field | Meaning |
|-------|---------|
| `agent_id` | Config agent assigned to the issue. |
| `issue_number` | Issue number. |
| `claimed_at` | When the claim was written. |

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
| `issues[].labels` | Project label names on the issue. |

### Session record fields

Present only while a session is live in this process.

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

One row per failed attempt. Rows are appended. A later failure does not overwrite an earlier row.

| Field | Meaning |
|-------|---------|
| `agent_id` | Config id that failed to spawn. |
| `agent_name` | Display name at failure time. |
| `issue_number` | Issue number, or empty for babysitter. |
| `pr_number` | PR number, or empty for issue agents. |
| `attempt` | Which consecutive attempt this failure was (`1`–`3`) for that issue or PR. |
| `released` | True on the issue row whose `attempt` is `3`, when that failure dropped the local claim. |
| `error` | Redacted error text (never contains `GITHUB_TOKEN`). |
| `at` | Timestamp. |

### Process lock fields

| Field | Meaning |
|-------|---------|
| `pid` | Holder process id. |
| `started_at` | When the holder took the lock. |

### Agent log format

Each line in `logs/<agent_id>.log` includes a clear `session_id=` marker (and `issue=` or `pr=` when known) so the dashboard can filter by session without a separate file per session. Lines from sessions that share an agent are appended whole, one line at a time. Logs are kept in full for the life of the project state directory; there is no size cap in v1. Stored lines never contain the `GITHUB_TOKEN` value.

Permission grants are ordinary log lines. A grant line names `optionId`, `kind`, and `title` when the request included them:

```text
2026-10-10T04:01:05Z session_id=<uuid> issue=42 permission grant optionId=<id> kind=<kind> title=<title>
```

A permission answered `cancelled` because the operator interrupted the session, or because graceful shutdown cancelled the turn, is a different line:

```text
2026-10-10T04:01:05Z session_id=<uuid> issue=42 permission cancelled
```

Agent message text and the child process stderr are appended on the same log, with the same session marker.

## User stories

### Store state under the per-user Orkie directory

**Given** a successfully bootstrapped project whose GitHub repository is `owner/repo`  
**When** Orkie needs to persist the issue snapshot, claims, spawn failures, or logs  
**Then** data is written under `~/.local/share/orkie/owner--repo/` and not into the project's Git working tree as the primary state store

### Isolate state by account and machine

**Given** the same Git project cloned on two machines (or used by two OS accounts)  
**When** Orkie runs on each  
**Then** each run uses its own `~/.local/share/orkie/<owner>--<repo>/` tree. Claims written on one machine are absent on the other

### A claim binds one agent to one issue

**Given** orchestration assigns an issue to a config agent  
**When** local state is updated  
**Then** the claim record stores that `agent_id`, that `issue_number`, and `claimed_at`. A second claim for the same issue is not stored

### A session binds one live spawn

**Given** orchestration has written a claim and spawned a session for that issue  
**When** local state is updated  
**Then** the session record stores the session id, the config agent id, that issue, and that the session is working. The claim stays the assignment; the session id is not written onto the claim

### A start discards leftover sessions

**Given** a previous process left session records or worktrees behind  
**When** Orkie starts again for the same project by the same user on the same machine  
**Then** it loads `claims`, `snapshot`, and `spawn_failures`, deletes leftover session records, and removes leftover worktrees. It does not resume an ACP session. No session is working until a new spawn. Claims remain

### Corrupt state fails bootstrap

**Given** `claims`, `snapshot`, or `spawn_failures` is unreadable or not valid state  
**When** bootstrap loads local state  
**Then** bootstrap fails and names that file. A missing file is an empty starting value and is not an error

### A corrupt lock file does not block a start that holds the lock

**Given** the process has acquired the project lock and the lock file's contents are unreadable or not valid lock data  
**When** bootstrap records the holder  
**Then** Orkie overwrites the lock contents in place and continues. It does not fail startup for that file

### Retain agent logs for the dashboard

**Given** one or more sessions are or were active  
**When** an operator opens the local web dashboard  
**Then** status, permission grants, and other log lines are read from `logs/<agent_id>.log`, filtered by `session_id=`, together with live ACP data where supported

### Append to a per-agent log

**Given** a session produces log output or Orkie grants a permission  
**When** Orkie stores that line  
**Then** it appends one complete line to `logs/<agent_id>.log` with a clear session id marker, stores no copy of the `GITHUB_TOKEN` value, and does not truncate by size

### Record a spawn failure until resolved

**Given** a spawn attempt for a config agent and an issue, or for the babysitter and a PR, fails  
**When** local state is updated  
**Then** a new spawn-failure record stores the fields in [Spawn-failure record fields](#spawn-failure-record-fields). Those records are the consecutive attempt history. The dashboard can read them. Issue attempts follow the three-strike rule in [05-agent-orchestration.md](05-agent-orchestration.md)

### Shutdown deletes sessions and keeps claims

**Given** Orkie is shutting down by either mode in [08-cli-and-dashboard.md](08-cli-and-dashboard.md)  
**When** the shutdown flush runs  
**Then** session records for this process are deleted, worktree removal is attempted, and `claims`, `snapshot`, `spawn_failures`, and agent logs remain. A worktree that cannot be removed is logged and does not by itself fail the flush

## Acceptance criteria

- [ ] Default local state root is `~/.local/share/orkie/<owner>--<repo>/` under the user's home directory, using the resolved GitHub owner and repository name.
- [ ] Project id is stable for that GitHub repository and is shared by clones of it on the same machine and OS account.
- [ ] On-disk layout and record fields match [State layout](#state-layout). Intake, orchestration, and the dashboard share that layout.
- [ ] `claims` stores `agent_id`, `issue_number`, and `claimed_at`, with at most one claim per issue. Claims survive shutdown and crash.
- [ ] Session records and `worktrees/<session_id>/` do not survive shutdown. The next start deletes leftover session records and removes leftover worktrees. ACP sessions are not resumed.
- [ ] Agent logs live at `logs/<agent_id>.log`, mark `session_id=` (and `issue=` or `pr=` when known) in-line, include permission-grant and permission-cancelled lines, are appended one complete line at a time, are not size-capped in v1, and never store the `GITHUB_TOKEN` value.
- [ ] Spawn-failure records are the consecutive attempt history for an issue or PR. `released` is true on the issue row that dropped the local claim at attempt 3.
- [ ] The Git project tree is not the primary store for orchestration runtime state.
- [ ] State is not shared across OS users or machines. A start on another machine begins with its own empty claim set. This isolation is documented.
- [ ] After a start on the same user and machine, Orkie loads the last persisted `claims`, `snapshot`, and `spawn_failures`.
- [ ] Corrupt `claims`, `snapshot`, or `spawn_failures` fails bootstrap and names the file. A missing file is empty. Corrupt lock contents, once the lock is held, are overwritten in place and do not block startup.
- [ ] Both shutdown modes flush local state before exit so session records are gone and claims remain. Worktree removal failure is logged and does not change that flush.
