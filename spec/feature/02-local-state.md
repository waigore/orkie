# Feature: Local State

## Description

Orkie keeps a small per-user, tool-owned directory outside the Git repository: `~/.local/share/orkie/<owner>--<repo>/`, where `<owner>` and `<repo>` are the resolved GitHub repository. On disk, that tree holds only what must outlive a process: the instance **lock** (while Orkie is running), **per-agent logs** (execution history for the dashboard), and **session worktrees** (while a session is live). Claims, the intake snapshot, spawn-failure records, and session bookkeeping are **process-local** (in memory). A restart starts with empty claims, an empty snapshot, and an empty spawn-failure set, then re-fetches intake from the remote tracker.

A **claim** is Orkie's assignment of one config agent to one issue inside the current process. It is the source of truth for which issue this Orkie will spawn next **while it is running**. Claims do not survive process stop or crash. A **session** is a live ACP spawn bound to one issue or one PR; sessions are never resumed. After a process start, no session is working until orchestration spawns one.

Because the state root is per user and machine, starting Orkie under a different OS account or on a different machine uses a separate directory (separate logs and lock). Two clones of the same GitHub repository on one machine share this directory. A second live Orkie for that project refuses to start (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md)).

Persistence policy: only data with a real need after restart is durable. See ADR [013](../adr/013-minimize-persisted-state.md). The [state layout](#state-layout) below is the source of truth for on-disk vs in-memory fields.

## Use cases

Actors are defined in [users.md](users.md).

- **Operator**: Runs Orkie continuously. Expects agent logs and the instance lock behavior to work without rewriting the project repo. Accepts that stopping Orkie clears in-flight claims and spawn-failure history; the next start re-sweeps intake and claims anew.
- **Dashboard user**: Views agent and issue status, permission grants, and logs sourced from durable logs plus live process state (claims, snapshot, sessions, spawn failures).

## State layout

Root: `~/.local/share/orkie/<owner>--<repo>/` (under the user's home directory on every platform).

### On disk

| Path | Survives clean stop? | Purpose |
|------|----------------------|---------|
| `lock` | No (removed on normal shutdown) | Process lock: holder pid and start time. One live Orkie per GitHub repository. Leftover after crash: stale if pid is dead. |
| `logs/<agent_id>.log` | Yes | Append-only agent log for that config identity (execution history). |
| `worktrees/<session_id>/` | No | Dedicated git worktree. Removed when the session ends; leftovers removed at the next start. |

### In memory (this process only)

| Record | Purpose |
|--------|---------|
| Intake snapshot | Last good intake set for delta comparison within this process. Empty until the first successful fetch after start. |
| Claims | Local claim records for this process. Empty at every start. |
| Spawn failures | Consecutive spawn-failure rows for this process. Empty at every start (three-strike budget resets). |
| Live sessions | ACP session handles / session identity for working spawns. Empty at every start. |

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
| `fetched_at` | Timestamp of the last successful intake fetch in this process. |
| `issues[]` | Open non-PR intake issues from that fetch. |
| `issues[].number` | Issue number. |
| `issues[].title` | Title. |
| `issues[].body` | Body. |
| `issues[].url` | HTML URL. |
| `issues[].state` | Open/closed as reported by the connector. |
| `issues[].labels` | Project label names on the issue. |

### Session fields (live process)

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

One row per failed attempt in this process. Rows are appended. A later failure does not overwrite an earlier row.

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

### Keep durable data under the per-user Orkie directory

**Given** a successfully bootstrapped project whose GitHub repository is `owner/repo`  
**When** Orkie needs a process lock, agent logs, or session worktrees  
**Then** data is written under `~/.local/share/orkie/owner--repo/` and not into the project's Git working tree as the primary store

### Isolate the state root by account and machine

**Given** the same Git project cloned on two machines (or used by two OS accounts)  
**When** Orkie runs on each  
**Then** each run uses its own `~/.local/share/orkie/<owner>--<repo>/` tree for lock, logs, and worktrees

### A claim binds one agent to one issue in this process

**Given** orchestration assigns an issue to a config agent  
**When** process state is updated  
**Then** the claim record stores that `agent_id`, that `issue_number`, and `claimed_at`. A second claim for the same issue is not stored. The claim is not written to disk

### Restart starts with a blank assignment slate

**Given** a previous Orkie process had claims, an intake snapshot, and spawn-failure rows  
**When** Orkie starts again for the same project by the same user on the same machine  
**Then** claims, snapshot, and spawn failures are empty. Orkie re-fetches the full intake set on the first successful poll and may claim under current config. It removes leftover worktrees. It does not resume an ACP session. Agent logs from prior runs remain on disk

### Stale lock does not block a start

**Given** a `lock` file exists but its `pid` is not alive (or the JSON is corrupt once the flock is held)  
**When** Orkie starts  
**Then** it takes the lock for itself. If another live Orkie holds the lock, start refuses

### Clean shutdown removes the lock file

**Given** Orkie shuts down by either mode in [08-cli-and-dashboard.md](08-cli-and-dashboard.md)  
**When** the shutdown flush finishes  
**Then** the `lock` file is removed, worktree removal is attempted, and agent logs remain. Process-local claims, snapshot, and spawn failures end with the process

### Retain agent logs for the dashboard

**Given** one or more sessions are or were active  
**When** an operator opens the local web dashboard  
**Then** status, permission grants, and other log lines are read from `logs/<agent_id>.log`, filtered by `session_id=`, together with live ACP and process state where supported

### Append to a per-agent log

**Given** a session produces log output or Orkie grants a permission  
**When** Orkie stores that line  
**Then** it appends one complete line to `logs/<agent_id>.log` with a clear session id marker, stores no copy of the `GITHUB_TOKEN` value, and does not truncate by size

### Record a spawn failure until resolved (this process)

**Given** a spawn attempt for a config agent and an issue, or for the babysitter and a PR, fails  
**When** process state is updated  
**Then** a new spawn-failure record stores the fields in [Spawn-failure record fields](#spawn-failure-record-fields). Those records are the consecutive attempt history for this process. The dashboard can read them. Issue attempts follow the three-strike rule in [05-agent-orchestration.md](05-agent-orchestration.md). A new process starts with no rows

## Acceptance criteria

- [ ] Default local state root is `~/.local/share/orkie/<owner>--<repo>/` under the user's home directory, using the resolved GitHub owner and repository name.
- [ ] Project id is stable for that GitHub repository and is shared by clones of it on the same machine and OS account.
- [ ] On-disk layout matches [On disk](#on-disk): `lock`, `logs/<agent_id>.log`, `worktrees/<session_id>/` only. Claims, snapshot, spawn failures, and sessions are not durable documents.
- [ ] Claims store `agent_id`, `issue_number`, and `claimed_at`, with at most one claim per issue, in process memory only. They do not survive stop or crash.
- [ ] Worktrees do not survive session end. The next start removes leftover worktrees. ACP sessions are not resumed.
- [ ] Agent logs live at `logs/<agent_id>.log`, mark `session_id=` (and `issue=` or `pr=` when known) in-line, include permission-grant and permission-cancelled lines, are appended one complete line at a time, are not size-capped in v1, and never store the `GITHUB_TOKEN` value.
- [ ] Spawn-failure records are the consecutive attempt history for an issue or PR **in this process**. `released` is true on the issue row that dropped the local claim at attempt 3. The budget resets on the next start.
- [ ] The Git project tree is not the primary store for orchestration runtime state.
- [ ] State roots are not shared across OS users or machines. This isolation is documented.
- [ ] After a start, Orkie begins with empty claims, snapshot, and spawn failures, then re-sweeps remote intake.
- [ ] Every starter checks the separate `lock` file. Live pid → refuse. Dead/missing/corrupt once flock held → take over. Clean shutdown removes the lock file.
- [ ] Both shutdown modes end sessions, attempt worktree removal, remove the lock file, and leave agent logs. Worktree removal failure is logged and does not by itself fail the flush.
