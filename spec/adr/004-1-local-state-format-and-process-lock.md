# ADR 004: Local state format and process lock

## Status

Accepted

Supersedes [004](superseded/004-local-state-format-and-process-lock.md).

## Context

Feature [02](../feature/02-local-state.md) defines the per-user state root, record fields, and log layout, but not serialization or lock mechanics. Orchestration, intake, dashboard, and shutdown all share this store ([05](../feature/05-agent-orchestration.md), [08](../feature/08-cli-and-dashboard.md)). Claim status is the remote claim label. Local state does not store a claim record.

## Decision

### Root

`Path.home() / ".local" / "share" / "orkie" / f"{owner}--{repo}"` on every platform (including macOS). Create parents as needed. Never use the Git project tree as the primary store.

### Serialization: JSON files

| Path | Format |
|------|--------|
| `lock` | JSON object: `pid` (int), `started_at` (UTC ISO-8601 string). Updated in place on the open file |
| `snapshot` | JSON object matching intake snapshot fields |
| `sessions` | JSON object: `sessions` array of session records |
| `spawn_failures` | JSON object: `failures` array of spawn-failure records |
| `logs/<agent_id>.log` | Append-only text; UTF-8; each line includes `session_id=` and issue/PR when known |

No `claims` file. No SQLite, no pickle, no YAML for runtime state.

Spawn-failure records are the consecutive attempt history for an issue or a PR ([007-1](007-1-orchestration-cycle-and-claim-session-state-machine.md)).

### Atomic writes

For snapshot, sessions, and spawn_failures: write to a temp file in the same directory (`*.tmp`), `fsync`, then `os.replace` onto the target. Readers that catch partial content treat the poll/operation as failed and keep the last good in-memory/on-disk document (intake already preserves last good snapshot on fetch failure).

The lock file is not replaced. The process opens it, takes the flock, and rewrites that same file descriptor in place. The descriptor stays open until shutdown.

On process start, reload snapshot, sessions, and spawn failures, then force every session record `working` to false before the dashboard serves and before the first spawn.

### Process lock

1. Open/create `lock` for read/write.
2. Try exclusive `fcntl.flock` (POSIX). Orkie v1 targets Unix-like operators (macOS/Linux; systemd).
3. After the lock is held, read existing JSON if any. If `pid` is alive (`os.kill(pid, 0)` succeeds), release the flock and refuse start. If the pid is dead or missing, write this process's `pid` and `started_at` in place, and keep the flock for the process lifetime.
4. On graceful shutdown, release the flock and leave the `lock` file in place (content may remain; the next start treats a dead pid as stale).

Windows is out of scope for v1 locking; document the Unix requirement with the CLI.

### Logs

Append with flush. Redact any substring equal to the current `GITHUB_TOKEN` value before write. No rotation or size cap in v1.

### Worktrees directory

`worktrees/<session_id>/` under the same state root ([008-1](008-1-git-worktrees.md)). Not a JSON document. The owning git directory is discovered from the worktree, not stored here.

## Reasoning

- JSON matches the field tables in feature 02, is stdlib-friendly, and is easy to inspect when debugging.
- File-per-concern keeps intake snapshot updates from rewriting session history.
- The claim lives on the tracker, so a local claim file would be a second status.
- flock plus a pid check implements “one live Orkie” and “stale lock does not block” without a separate lock daemon.
- Replacing the lock file would point the path at a new inode while the flock stayed on the old one.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| SQLite single DB | Heavier; harder to eyeball; unnecessary for record volumes |
| PID-only file without flock | TOCTOU races between two starters |
| flock-only without pid record | Feature 02 requires pid and started_at for operators and refuse messages |
| State inside `.orkie/` or the repo | Pollutes the project; breaks multi-clone sharing rules |
| Per-session log files | Feature 02: one log per config agent id with in-line session markers |
| Local `claims` document | Feature 05: claim status is the remote label |
| Atomic replace of `lock` | Drops the flock's inode |

## Consequences for design

- `orkie.state` exposes a small store API: `acquire_lock`, `load_snapshot`, `load_sessions`, `load_spawn_failures`, `save_*`, `append_log`, `mark_sessions_not_working`.
- `mark_sessions_not_working` runs after reload.
- Dashboard and orchestration share the same store instance; no second writer format.
- Tests use a temporary home/state root via injectable base path.
- Crash mid-write of a replaced document: atomic replace limits corruption; the next cycle reloads the last good snapshot.
