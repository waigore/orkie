# ADR 004: Local state format and process lock

## Status

Superseded by [004-3-local-state-format-and-process-lock](../004-3-local-state-format-and-process-lock.md).

Was Accepted.


## Context

Feature [02](../feature/02-local-state.md) defines the per-user state root, record fields, and log layout, but not serialization or lock mechanics. Orchestration, intake, dashboard, and shutdown all share this store ([05](../feature/05-agent-orchestration.md), [08](../feature/08-cli-and-dashboard.md)). Claims are local records and survive process stop. Session records do not.

## Decision

### Root

`Path.home() / ".local" / "share" / "orkie" / f"{owner}--{repo}"` on every platform (including macOS). Create parents as needed. Never use the Git project tree as the primary store.

### Serialization: JSON files

| Path | Kept across stop | Format |
|------|------------------|--------|
| `lock` | Yes | JSON object: `pid` (int), `started_at` (UTC ISO-8601 string). Updated in place on the open file |
| `snapshot` | Yes | JSON object matching intake snapshot fields |
| `claims` | Yes | JSON object: `claims` array of `{agent_id, issue_number, claimed_at}`. At most one record per issue |
| `spawn_failures` | Yes | JSON object: `failures` array of spawn-failure records |
| `sessions` | No | JSON object: `sessions` array of session records, present only while this process has live sessions. Deleted on shutdown. Leftovers are deleted at the next start |
| `logs/<agent_id>.log` | Yes | Append-only text; UTF-8; each line includes `session_id=` and `issue=` or `pr=` when known |

No SQLite, no pickle, no YAML for runtime state.

A missing `claims`, `snapshot`, or `spawn_failures` file is empty. Unreadable or corrupt JSON for those files fails bootstrap and names the file.

Spawn-failure records are the consecutive attempt history for an issue or a PR ([007-2](007-2-orchestration-cycle-and-claim-session-state-machine.md)). Rows are appended. `released` is true on the issue row whose `attempt` is 3.

### Atomic writes

For snapshot, claims, sessions, and spawn_failures: write to a temp file in the same directory (`*.tmp`), `fsync`, then `os.replace` onto the target. Readers that catch partial content treat the poll/operation as failed and keep the last good in-memory/on-disk document (intake already preserves last good snapshot on fetch failure).

The lock file is not replaced. The process opens it, takes the flock, and rewrites that same file descriptor in place. The descriptor stays open until shutdown. If the contents are unreadable or not valid lock JSON once the flock is held, overwrite them in place with this process's `pid` and `started_at` and continue.

On process start, load claims, snapshot, and spawn failures. Delete any leftover `sessions` document. Do not mark reloaded sessions not-working in order to resume them.

### Process lock

1. Open/create `lock` for read/write.
2. Try exclusive `fcntl.flock` (POSIX). Orkie v1 targets Unix-like operators (macOS/Linux; systemd).
3. After the lock is held, read existing JSON if any. If `pid` is alive (`os.kill(pid, 0)` succeeds), release the flock and refuse start. If the pid is dead, missing, or the JSON is corrupt, write this process's `pid` and `started_at` in place, and keep the flock for the process lifetime.
4. On shutdown, release the flock and leave the `lock` file in place (content may remain; the next start treats a dead pid as stale).

Windows is out of scope for v1 locking; document the Unix requirement with the CLI.

### Logs

Append one complete line at a time, serialized per `agent_id`, then flush. Several sessions of one agent share the file. Redact any substring equal to the current `GITHUB_TOKEN` value before write. No rotation or size cap in v1. Permission-grant and permission-cancelled lines use the format in feature 02.

### Worktrees directory

`worktrees/<session_id>/` under the same state root ([008-1](008-1-git-worktrees.md)). Not a JSON document. The owning git directory is discovered from the worktree, not stored here. Startup removes leftovers best-effort.

## Reasoning

- JSON matches the field tables in feature 02, is stdlib-friendly, and is easy to inspect when debugging.
- File-per-concern keeps intake snapshot updates from rewriting claims.
- The claim file is the assignment memory the next start uses to spawn. Session files are not, because ACP sessions are not resumed.
- flock plus a pid check implements “one live Orkie” and “stale lock does not block” without a separate lock daemon.
- Replacing the lock file would point the path at a new inode while the flock stayed on the old one.
- A per-agent append lock keeps one log line intact when raised caps share a file across reader threads.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| SQLite single DB | Heavier; harder to eyeball; unnecessary for record volumes |
| PID-only file without flock | TOCTOU races between two starters |
| flock-only without pid record | Feature 02 requires pid and started_at for operators and refuse messages |
| State inside `.orkie/` or the repo | Pollutes the project; breaks multi-clone sharing rules |
| Per-session log files | Feature 02: one log per config agent id with in-line session markers |
| Resume ACP sessions from the `sessions` file | Feature 02 deletes that file on shutdown and at the next start |
| Fail startup when lock JSON is corrupt | The process already holds the flock; the contents are rewritten |
| Size-cap agent logs | Feature 02 keeps logs for the life of the state directory |

## Consequences for design

- `orkie.state` exposes a small store API: `acquire_lock`, `load_snapshot`, `load_claims`, `load_spawn_failures`, `save_*`, `append_log`, `delete_sessions`.
- `delete_sessions` runs at startup for leftovers and at shutdown. There is no resume path that reloads sessions and clears `working`.
- Dashboard and orchestration share the same store instance; no second writer format.
- Tests use a temporary home/state root via injectable base path.
- Crash mid-write of a replaced document: atomic replace limits corruption; the next cycle reloads the last good snapshot and claims.
