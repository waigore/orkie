# Data

| Features | ADRs |
|----------|------|
| [02](../feature/02-local-state.md), [06](../feature/06-work-intake-and-issue-monitoring.md) | [004](../adr/004-1-local-state-format-and-process-lock.md), [008](../adr/008-1-git-worktrees.md), [009](../adr/009-1-intake-poll-and-delta.md) |

On-disk field meanings come from feature [02](../feature/02-local-state.md). Serialization and lock mechanics come from ADR [004](../adr/004-1-local-state-format-and-process-lock.md). This document is the implementable schema and ownership map.

## State root

```text
{Path.home()}/.local/share/orkie/{owner}--{repo}/
```

Used on **every** platform including macOS (not `~/Library`). `{owner}` and `{repo}` are the resolved GitHub identity. Injectable base path for tests ([components.md](components.md) `default_state_root`).

Two clones of the same GitHub repo on the same OS user/machine share this tree. Different users or machines do not.

**Not stored in the Git project tree** as the primary runtime store. No local `claims` file — claim status is the remote claim label only.

## Layout

| Path | Kind | Purpose |
|------|------|---------|
| `lock` | JSON object | Process lock |
| `snapshot` | JSON object | Last good intake snapshot |
| `sessions` | JSON object | Session records wrapper |
| `spawn_failures` | JSON object | Spawn-failure records wrapper |
| `logs/<agent_id>.log` | Append-only UTF-8 text | Per config-identity logs |
| `worktrees/<session_id>/` | Directory | Detached git worktree |

Create `logs/` and `worktrees/` on ensure_layout. Missing JSON files at first run mean empty defaults (`snapshot` absent → first fetch baselines; `sessions` → `[]`; `failures` → `[]`).

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

**Acquire:** open/create for read/write → exclusive `fcntl.flock` → read JSON if any → if `pid` alive (`os.kill(pid, 0)` succeeds) release flock and refuse start → else write this pid/`started_at` on the **same** FD → keep flock until shutdown. Do **not** `os.replace` the lock file.

**Release:** unlock flock; leave file on disk (stale content OK).

Windows locking is out of scope for v1.

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
      "labels": ["orkie", "orkie:claimed"]
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
| `issues[].labels` | string[] | Label names, including claim label when present |

`claim_labeled` non-intake opens are **not** stored here; they are a per-tick handoff from intake to orchestration ([009](../adr/009-1-intake-poll-and-delta.md)).

## `sessions`

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
| `session_id` | string | Orkie UUID4 |
| `agent_id` | string | Config agent or babysitter `id` |
| `issue_number` | int \| null | Bound issue; null for babysitter |
| `pr_number` | int \| null | Bound PR; null for issue session |
| `working` | bool | ACP process running for this session |
| `worktree_path` | string | Absolute path |
| `started_at` | string \| null | When last became working; null if never |

Invariant: exactly one of `issue_number` / `pr_number` is non-null for a record created by a successful design path. On process start, after reload, force every `working` to `false` and save before the dashboard serves or the first spawn.

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
| `released` | bool | True when third issue failure caused claim removal |
| `error` | string | Redacted; never contains `GITHUB_TOKEN` value |
| `at` | string | Timestamp |

**Consecutive rules:** keep the history for one issue or one PR as the records sharing that key. On failure append/update with `attempt = prior+1` capped at recording the third. On successful spawn for that key, delete all failures for that key. For babysitter, clear a PR's failures when a poll finds that PR not selectable, or on successful spawn.

## Atomic writes

For `snapshot`, `sessions`, `spawn_failures`:

1. Write to `{name}.tmp` in the same directory.
2. `flush` + `os.fsync` the temp file.
3. `os.replace(tmp, target)`.

If a reader sees corrupt/partial JSON: treat the operation as failed; keep the last good in-memory/on-disk document. Intake already preserves last good snapshot on fetch failure.

## Logs

Path: `logs/<agent_id>.log` (agent_id from config; sanitize only if needed for path safety — ids are already constrained).

Each appended line MUST include `session_id=<uuid>` and, when known, `issue=<n>` or `pr=<n>`:

```text
2026-10-10T04:01:05Z session_id=550e8400-e29b-41d4-a716-446655440000 issue=42 <message>
```

Before write, replace any substring equal to the current `GITHUB_TOKEN` with `***`. Append + flush. No rotation or size cap in v1.

Dashboard filters: lines containing `session_id=<that session's id>`.

## Worktrees

Directory: `worktrees/<session_id>/`. Not JSON. Owning git directory discovered from the worktree (git metadata), not stored as a separate state field. Human branch name / `detached` is **in-memory only** for the dashboard ([008](../adr/008-1-git-worktrees.md)).

## In-memory (not on disk)

| Data | Owner | Readers |
|------|-------|---------|
| Live `SessionHandle` table (`session_id` → handle, includes `acp_session_id`, `Popen`) | orchestration / acp | dashboard (status), orchestration |
| `shutdown_event`, `immediate_kill` | cli | all |
| Cycle lock | cli / orchestration / dashboard | — |
| Last intake error string | intake | dashboard |
| Start-checkout branch or `detached` | worktree/cli at bootstrap | dashboard issue view |
| Effective listen port | cli | dashboard URL print |
| Loaded `Config` | cli | all modules |

## Ownership matrix

| Artifact | Writer | Readers |
|----------|--------|---------|
| `lock` | state (`cli` bootstrap/shutdown) | state (acquire) |
| `snapshot` | intake (on successful fetch) | intake (diff), dashboard (issue view), orchestration (via intake handoff) |
| `sessions` | orchestration (and bootstrap mark-not-working) | dashboard, orchestration |
| `spawn_failures` | orchestration | dashboard, orchestration |
| `logs/*` | acp (via store.append_log) | dashboard |
| `worktrees/*` | worktree | acp cwd; worktree remove |
| Remote claim label | orchestration only (via connector) | intake fetch (presence), collaborators on GitHub |
| Open PR list | not stored; fetched each babysitter step | orchestration step 8 |

## Corrupt / missing file at startup

| File | Behavior |
|------|----------|
| Missing `sessions` / `spawn_failures` | Treat as empty arrays |
| Missing `snapshot` | First successful fetch baselines and still runs orchestration that tick |
| Corrupt JSON on reload | Bootstrap fails hard with a message naming the file (operator can delete/repair) |
| Corrupt mid-run after atomic replace failure | Keep prior good document; log; continue |

## Secrets

Never persist `GITHUB_TOKEN` in state files, logs, spawn-failure errors, or dashboard HTML. Token exists only in process environment and child env for ACP.
