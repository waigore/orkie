# Data

| Features | ADRs |
|----------|------|
| [02](../feature/02-local-state.md), [04](../feature/04-acp-agent-runtime.md), [05](../feature/05-agent-orchestration.md), [06](../feature/06-work-intake-and-issue-monitoring.md) | [004](../adr/004-3-local-state-format-and-process-lock.md), [008](../adr/008-2-git-worktrees.md), [009](../adr/009-3-intake-poll-and-delta.md), [013](../adr/013-minimize-persisted-state.md) |

On-disk vs in-memory meanings come from feature [02](../feature/02-local-state.md). Lock and log mechanics come from ADR [004](../adr/004-3-local-state-format-and-process-lock.md). Persistence principle: ADR [013](../adr/013-minimize-persisted-state.md). This document is the implementable schema and ownership map.

## State root

```text
{Path.home()}/.local/share/orkie/{owner}--{repo}/
```

Used on **every** platform including macOS (not `~/Library`). `{owner}` and `{repo}` are the resolved GitHub identity. Injectable base path for tests ([components.md](components.md) `default_state_root`).

Two clones of the same GitHub repo on the same OS user/machine share this tree. Different users or machines do not.

**Not stored in the Git project tree** as the primary runtime store. Claims are process-local. Orkie does not write a GitHub label for them.

## Layout

### On disk

| Path | Survives clean stop | Kind | Purpose |
|------|---------------------|------|---------|
| `lock` | No (unlinked on clean shutdown) | JSON object | Process lock while this Orkie holds it |
| `logs/<agent_id>.log` | Yes | Append-only UTF-8 text | Per config-identity execution history |
| `worktrees/<session_id>/` | No | Directory | Detached git worktree for a live session |

Create `logs/` and `worktrees/` on ensure_layout. Startup may unlink leftover `claims` / `snapshot` / `sessions` / `spawn_failures` files from older versions without parsing them.

### In memory (process-local)

Empty at every start. Held on `StateStore` (claims, snapshot, spawn failures) and the live session table on the runtime context.

| Data | Purpose |
|------|---------|
| Claims | Assignment of config agent → issue for this process |
| Intake snapshot | Last good fetch in this process for delta comparison |
| Spawn failures | Consecutive attempt history for this process |
| Live sessions | ACP handles keyed by `session_id` (authoritative) |

## Timestamps

All timestamps are UTC ISO-8601 strings with a `Z` suffix, e.g. `2026-10-10T04:00:00Z`. Use second precision minimum.

## `lock`

```json
{
  "pid": 12345,
  "started_at": "2026-10-10T04:00:00Z"
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `pid` | int | Holder OS process id |
| `started_at` | string | When this process took the lock |

**Acquire:** open/create for read/write → exclusive `fcntl.flock` → read JSON if any → if `pid` is alive (`os.kill(pid, 0)` succeeds) release flock and refuse start → else write this pid/`started_at` on the **same** FD → keep flock for the process lifetime. Do **not** `os.replace` the lock file. If the contents are unreadable or not valid lock JSON once the flock is held, overwrite them in place and continue.

**Release (clean shutdown):** unlink `lock` while the flock is still held on that FD, then unlock and close. After a clean exit the lock file must not remain. After a crash, a leftover file with a dead pid is stale on the next start.

Windows locking is out of scope for v1.

## Claims (in memory)

Shape (not a disk document):

```json
{
  "claims": [
    {
      "agent_id": "worker",
      "issue_number": 42,
      "claimed_at": "2026-10-10T04:00:00Z"
    }
  ]
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `agent_id` | string | Config agent assigned to the issue |
| `issue_number` | int | Issue number. At most one claim per issue |
| `claimed_at` | string | When the claim was written |

The claim is not keyed by session id. It does not survive process stop. Orchestration writes it before spawn and drops it on exit while running (before shutdown has started), dashboard kill, leaving intake, absent stored `agent_id` in config, loss of the stored agent's match, or attempt 3. Continuity of `agent_id` across restarts is not required.

## Snapshot (in memory)

```json
{
  "fetched_at": "2026-10-10T04:00:00Z",
  "issues": [
    {
      "number": 42,
      "title": "…",
      "body": "…",
      "url": "https://github.com/owner/repo/issues/42",
      "state": "open",
      "labels": ["orkie"]
    }
  ]
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `fetched_at` | string | Last successful intake fetch in this process |
| `issues` | array | Intake issues only (open non-PR ∩ `issue_labels`) |
| `issues[].number` | int | Issue number |
| `issues[].title` | string | Title |
| `issues[].body` | string | Body (may be empty) |
| `issues[].url` | string | HTML URL |
| `issues[].state` | string | As reported by connector |
| `issues[].labels` | string[] | Project label names |

Absent until the first successful fetch after start (full remote sweep). On fetch failure, keep the last good in-memory snapshot.

## Sessions (live process)

Authoritative store: runtime session table (`session_id` → ACP handle). No sessions document on disk.

Derived view fields when needed:

| Field | Type | Meaning |
|-------|------|---------|
| `session_id` | string | Orkie UUID4 minted by orchestration for this spawn |
| `agent_id` | string | Config agent or babysitter `id` |
| `issue_number` | int \| null | Bound issue; null for babysitter |
| `pr_number` | int \| null | Bound PR; null for issue session |
| `working` | bool | ACP process running for this session |
| `worktree_path` | string | Absolute path |
| `started_at` | string | When the session became working |

Invariant: exactly one of `issue_number` / `pr_number` is non-null. No agent pid is stored.

## Spawn failures (in memory)

```json
{
  "failures": [
    {
      "agent_id": "worker",
      "agent_name": "Worker",
      "issue_number": 42,
      "pr_number": null,
      "attempt": 2,
      "released": false,
      "error": "acp handshake timeout",
      "at": "2026-10-10T04:02:00Z"
    }
  ]
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `agent_id` | string | Config id that failed |
| `agent_name` | string | Display name at failure time |
| `issue_number` | int \| null | Issue key; null for babysitter |
| `pr_number` | int \| null | PR key; null for issue agents |
| `attempt` | int | Consecutive attempt `1`–`3` for that issue or PR |
| `released` | bool | True on the issue row whose `attempt` is `3` (the row that dropped the local claim) |
| `error` | string | Redacted; never contains `GITHUB_TOKEN` value |
| `at` | string | Timestamp |

**Consecutive rules:** append one row per failure. Do not overwrite an earlier row. Do not write a fourth. On successful spawn for that issue or PR, delete all failures for that key. Leaving intake does not clear issue rows. While any row for an issue has `attempt == 3`, orchestration does not write a new claim or spawn that issue. For babysitter, clear a PR's failures when a poll finds that PR not selectable, or on successful spawn. Empty at every process start (three-strike budget resets).

## Logs

Path: `logs/<agent_id>.log` (agent_id from config; ids are already path-safe).

`append_log` holds a lock for that `agent_id` for the duration of one line, so sessions that share an agent do not interleave a line.

Each appended line MUST include `session_id=<uuid>` and, when known, `issue=<n>` or `pr=<n>`:

```text
2026-10-10T04:01:05Z session_id=550e8400-e29b-41d4-a716-446655440000 issue=42 <message>
```

Permission grant:

```text
2026-10-10T04:01:05Z session_id=550e8400-e29b-41d4-a716-446655440000 issue=42 permission grant optionId=<id> kind=<kind> title=<title>
```

Omit `title=` when the request has no title. Permission answered `cancelled` on interrupt or graceful-shutdown cancel:

```text
2026-10-10T04:01:05Z session_id=550e8400-e29b-41d4-a716-446655440000 issue=42 permission cancelled
```

Before write, replace any substring equal to the current `GITHUB_TOKEN` with `***`. Append + flush. No rotation or size cap in v1.

Dashboard filters: lines containing `session_id=<that session's id>`, last 200 after filter.

## Worktrees

Directory: `worktrees/<session_id>/`. Not JSON. Owning git directory discovered from the worktree (git metadata), not stored as a separate state field. The start-checkout tip commit and branch name (or `detached` before the first successful sync) are **in-memory only** and refresh after each successful sync ([008](../adr/008-2-git-worktrees.md)).

## Other in-memory (not on disk)

| Data | Owner | Readers |
|------|-------|---------|
| Live `SessionHandle` table (`session_id` → handle, includes `acp_session_id`, `Popen`, `session_delete` capability) | orchestration / acp | dashboard (status), orchestration |
| `shutdown_event`, `immediate_kill`, shutdown-prompt flag | cli | all |
| Cycle lock | cli / orchestration / dashboard | — |
| Last intake error string | intake | dashboard |
| Start-checkout commit and branch or `detached` | worktree (bootstrap + after each sync) | dashboard issue view |
| Effective listen port | cli | dashboard URL print |
| Loaded `Config` | cli | all modules |

## Ownership matrix

| Artifact | Writer | Readers |
|----------|--------|---------|
| `lock` | state (`cli` bootstrap/shutdown) | state (acquire) |
| Snapshot (memory) | intake (on successful fetch) | intake (diff), dashboard (issue view), orchestration (via intake handoff) |
| Claims (memory) | orchestration | orchestration, dashboard (issue view) |
| Live sessions | orchestration / acp | dashboard, orchestration |
| Spawn failures (memory) | orchestration | dashboard, orchestration |
| `logs/*` | acp (via store.append_log) | dashboard |
| `worktrees/*` | worktree | acp cwd; worktree remove |
| Open PR list | not stored; fetched each babysitter step | orchestration step 8 |

## Startup / shutdown

| Situation | Behavior |
|-----------|----------|
| Process start | Empty claims, snapshot, spawn failures; scrub legacy JSON docs if present; remove leftover worktrees; acquire lock |
| Clean shutdown | End sessions; remove worktrees; unlink `lock`; leave logs |
| Crash | Leftover `lock` with dead pid is stale; next start takes over. No claim/snapshot/failure restore |

## Secrets

Never persist `GITHUB_TOKEN` in state files, logs, spawn-failure errors, or dashboard HTML. Token exists only in process environment and child env for ACP.
