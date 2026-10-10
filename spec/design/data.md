# Data

| Features | ADRs |
|----------|------|
| [02](../feature/02-local-state.md), [04](../feature/04-acp-agent-runtime.md), [05](../feature/05-agent-orchestration.md), [06](../feature/06-work-intake-and-issue-monitoring.md) | [004](../adr/004-2-local-state-format-and-process-lock.md), [008](../adr/008-1-git-worktrees.md), [009](../adr/009-2-intake-poll-and-delta.md) |

On-disk field meanings come from feature [02](../feature/02-local-state.md). Serialization and lock mechanics come from ADR [004](../adr/004-2-local-state-format-and-process-lock.md). This document is the implementable schema and ownership map.

## State root

```text
{Path.home()}/.local/share/orkie/{owner}--{repo}/
```

Used on **every** platform including macOS (not `~/Library`). `{owner}` and `{repo}` are the resolved GitHub identity. Injectable base path for tests ([components.md](components.md) `default_state_root`).

Two clones of the same GitHub repo on the same OS user/machine share this tree. Different users or machines do not. A start on another machine has its own empty claim set.

**Not stored in the Git project tree** as the primary runtime store. Claims are the local `claims` file. Orkie does not write a GitHub label for them.

## Layout

| Path | Kept across stop | Kind | Purpose |
|------|------------------|------|---------|
| `lock` | Yes | JSON object | Process lock |
| `snapshot` | Yes | JSON object | Last good intake snapshot |
| `claims` | Yes | JSON object | Local claim records |
| `spawn_failures` | Yes | JSON object | Spawn-failure records wrapper |
| `logs/<agent_id>.log` | Yes | Append-only UTF-8 text | Per config-identity logs |
| `sessions` | No | JSON object | Live session records. Deleted on shutdown. Leftovers are deleted at the next start without being resumed |
| `worktrees/<session_id>/` | No | Directory | Detached git worktree. Removed when the session ends. Leftovers are removed at the next start |

Create `logs/` and `worktrees/` on ensure_layout. A missing `claims`, `snapshot`, or `spawn_failures` file means empty (`claims` → `[]`, `snapshot` absent → first fetch baselines, `failures` → `[]`).

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

**Acquire:** open/create for read/write → exclusive `fcntl.flock` → read JSON if any → if `pid` is alive (`os.kill(pid, 0)` succeeds) release flock and refuse start → else write this pid/`started_at` on the **same** FD → keep flock until shutdown. Do **not** `os.replace` the lock file. If the contents are unreadable or not valid lock JSON once the flock is held, overwrite them in place and continue.

**Release:** unlock flock; leave file on disk (stale content OK).

Windows locking is out of scope for v1.

## `claims`

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

The claim is not keyed by session id. It survives shutdown and crash. Orchestration writes it before spawn and drops it on exit while running (before shutdown has started), dashboard kill, leaving intake, absent stored `agent_id` in config, loss of the stored agent's match, or attempt 3.

## `snapshot`

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
| `fetched_at` | string | Last successful intake fetch |
| `issues` | array | Intake issues only (open non-PR ∩ `issue_labels`) |
| `issues[].number` | int | Issue number |
| `issues[].title` | string | Title |
| `issues[].body` | string | Body (may be empty) |
| `issues[].url` | string | HTML URL |
| `issues[].state` | string | As reported by connector |
| `issues[].labels` | string[] | Project label names |

## `sessions`

Present only while this process has live sessions.

```json
{
  "sessions": [
    {
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "agent_id": "worker",
      "issue_number": 42,
      "pr_number": null,
      "working": true,
      "worktree_path": "/Users/me/.local/share/orkie/owner--repo/worktrees/550e8400-e29b-41d4-a716-446655440000",
      "started_at": "2026-10-10T04:01:00Z"
    }
  ]
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `session_id` | string | Orkie UUID4 minted by orchestration for this spawn |
| `agent_id` | string | Config agent or babysitter `id` |
| `issue_number` | int \| null | Bound issue; null for babysitter |
| `pr_number` | int \| null | Bound PR; null for issue session |
| `working` | bool | ACP process running for this session |
| `worktree_path` | string | Absolute path |
| `started_at` | string | When the session became working |

Invariant: exactly one of `issue_number` / `pr_number` is non-null. The file is deleted on shutdown. The next start deletes a leftover file and does not load it. No agent pid is stored.

## `spawn_failures`

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

**Consecutive rules:** append one row per failure. Do not overwrite an earlier row. Do not write a fourth. On successful spawn for that issue or PR, delete all failures for that key. Leaving intake does not clear issue rows. While any row for an issue has `attempt == 3`, orchestration does not write a new claim or spawn that issue. For babysitter, clear a PR's failures when a poll finds that PR not selectable, or on successful spawn.

## Atomic writes

For `snapshot`, `claims`, `sessions`, `spawn_failures`:

1. Write to `{name}.tmp` in the same directory.
2. `flush` + `os.fsync` the temp file.
3. `os.replace(tmp, target)`.

Deleting `sessions` is `unlink` of the document (ignore if missing). If a reader sees corrupt/partial JSON for `claims`, `snapshot`, or `spawn_failures`: treat the operation as failed; keep the last good in-memory/on-disk document. Intake already preserves the last good snapshot on fetch failure.

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

Directory: `worktrees/<session_id>/`. Not JSON. Owning git directory discovered from the worktree (git metadata), not stored as a separate state field. The start-checkout commit and the human branch name / `detached` are **in-memory only** ([008](../adr/008-1-git-worktrees.md)).

## In-memory (not on disk)

| Data | Owner | Readers |
|------|-------|---------|
| Live `SessionHandle` table (`session_id` → handle, includes `acp_session_id`, `Popen`, `session_delete` capability) | orchestration / acp | dashboard (status), orchestration |
| `shutdown_event`, `immediate_kill`, shutdown-prompt flag | cli | all |
| Cycle lock | cli / orchestration / dashboard | — |
| Last intake error string | intake | dashboard |
| Start-checkout commit and branch or `detached` | worktree at bootstrap | dashboard issue view; worktree create |
| Effective listen port | cli | dashboard URL print |
| Loaded `Config` | cli | all modules |

## Ownership matrix

| Artifact | Writer | Readers |
|----------|--------|---------|
| `lock` | state (`cli` bootstrap/shutdown) | state (acquire) |
| `snapshot` | intake (on successful fetch) | intake (diff), dashboard (issue view), orchestration (via intake handoff) |
| `claims` | orchestration | orchestration, dashboard (issue view) |
| `sessions` | orchestration while a session is live; deleted by cli/state at shutdown and at the next start | dashboard, orchestration |
| `spawn_failures` | orchestration | dashboard, orchestration |
| `logs/*` | acp (via store.append_log) | dashboard |
| `worktrees/*` | worktree | acp cwd; worktree remove |
| Open PR list | not stored; fetched each babysitter step | orchestration step 8 |

## Corrupt / missing file at startup

| File | Behavior |
|------|----------|
| Missing `claims` / `spawn_failures` | Treat as empty arrays |
| Missing `snapshot` | First successful fetch baselines and still runs orchestration that tick |
| Missing or leftover `sessions` | Delete the file if present. Do not parse it and do not resume |
| Corrupt `claims`, `snapshot`, or `spawn_failures` | Bootstrap fails hard with a message naming the file |
| Corrupt `lock` JSON once the flock is held | Overwrite in place; continue |
| Corrupt mid-run after atomic replace failure | Keep prior good document; log; continue |

## Secrets

Never persist `GITHUB_TOKEN` in state files, logs, spawn-failure errors, or dashboard HTML. Token exists only in process environment and child env for ACP.
