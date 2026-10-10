# ADR 004: Local state format and process lock

## Status

Superseded by [004-1](../004-1-local-state-format-and-process-lock.md).

## Context

Feature [02](../../feature/02-local-state.md) defines the per-user state root, record fields, and log layout, but not serialization or lock mechanics. Orchestration, intake, dashboard, and shutdown all share this store ([05](../../feature/05-agent-orchestration.md), [08](../../feature/08-cli-and-dashboard.md)).

## Decision

### Root

`Path.home() / ".local" / "share" / "orkie" / f"{owner}--{repo}"` on every platform (including macOS), with `owner` and `repo` lowercased — GitHub names are case-insensitive, so differently-cased clones or `connector.repo` values must share one state root and one lock. Create parents as needed. Never use the Git project tree as the primary store.

### Serialization: JSON files

| Path | Format |
|------|--------|
| `lock` | JSON object: `pid` (int), `started_at` (UTC ISO-8601 string) |
| `snapshot` | JSON object matching intake snapshot fields |
| `claims` | JSON object: `claims` array of claim records |
| `sessions` | JSON object: `sessions` array of session records |
| `spawn_failures` | JSON object: `failures` array of spawn-failure records |
| `logs/<agent_id>.log` | Append-only text; UTF-8; each line includes `session_id=` and issue/PR when known |

No SQLite, no pickle, no YAML for runtime state.

### Atomic writes

For JSON documents: write to a temp file in the same directory (`*.tmp`), `fsync`, then `os.replace` onto the target. Readers that catch partial content treat the poll/operation as failed and keep the last good in-memory/on-disk document (intake already preserves last good snapshot on fetch failure).

Persist a claim record when the claim is established, not only at shutdown. On process start, reload snapshot and claims; force every session record `working` to false before the first spawn.

### Process lock

1. Open/create `lock` for read/write.
2. Try exclusive `fcntl.flock` (POSIX). Orkie v1 targets Unix-like operators (macOS/Linux; systemd). 
3. After lock held, read existing JSON if any. If `pid` is alive (`os.kill(pid, 0)` succeeds), release flock and refuse start. If pid is dead or missing, write this process's `pid` and `started_at`, keep flock for the process lifetime.
4. On graceful shutdown, release flock and leave `lock` file in place (content may remain; next start treats dead pid as stale).

Windows is out of scope for v1 locking; document Unix requirement with the CLI.

### Logs

Append with flush. Redact any substring equal to the current `GITHUB_TOKEN` value before write. No rotation or size cap in v1.

### Worktrees directory

`worktrees/<session_id>/` under the same state root ([008](008-git-worktrees.md)). Not a JSON document.

## Reasoning

- JSON matches the field tables in feature 02, is stdlib-friendly, and is easy to inspect when debugging.
- File-per-concern keeps intake snapshot updates from rewriting large log history.
- flock + pid check implements “one live Orkie” and “stale lock does not block” without a separate lock daemon.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| SQLite single DB | Heavier; harder to eyeball; unnecessary for record volumes |
| PID-only file without flock | TOCTOU races between two starters |
| flock-only without pid record | Feature 02 requires pid and started_at for operators and refuse messages |
| State inside `.orkie/` or the repo | Pollutes the project; breaks multi-clone sharing rules |
| Per-session log files | Feature 02: one log per config agent id with in-line session markers |

## Consequences for design

- `orkie.state` exposes a small store API: `acquire_lock`, `load_*`, `save_*`, `append_log`, `mark_sessions_not_working`.
- Dashboard and orchestration share the same store instance; no second writer format.
- Tests use a temporary home/state root via injectable base path.
- Crash mid-write: atomic replace limits corruption; next cycle reloads last good snapshot.
