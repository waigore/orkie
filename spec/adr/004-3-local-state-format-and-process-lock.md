# ADR 004: Local state format and process lock

## Status

Accepted

Supersedes [004-2](superseded/004-2-local-state-format-and-process-lock.md).

## Context

Feature [02](../feature/02-local-state.md) defines the per-user state root, what survives a process, and log layout. ADR [013](013-minimize-persisted-state.md) requires that only data with a real post-restart need is persisted. Orchestration, intake, dashboard, and shutdown share this store ([05](../feature/05-agent-orchestration.md), [08](../feature/08-cli-and-dashboard.md)).

## Decision

### Root

`Path.home() / ".local" / "share" / "orkie" / f"{owner}--{repo}"` on every platform (including macOS). Create parents as needed. Never use the Git project tree as the primary store.

### On disk

| Path | Lifetime | Format |
|------|----------|--------|
| `lock` | Only while this process holds the instance lock | JSON object: `pid` (int), `started_at` (UTC ISO-8601 string). Separate file. Checked by every starter. Removed on normal shutdown after the flock is released path completes (see below) |
| `logs/<agent_id>.log` | Survives stop and start | Append-only text; UTF-8; each line includes `session_id=` and `issue=` or `pr=` when known |
| `worktrees/<session_id>/` | Life of a live session; leftovers removed at the next start | Directory. Not JSON. Owning git directory discovered from the worktree ([008-2](008-2-git-worktrees.md)) |

No SQLite, no pickle, no YAML for runtime state. No on-disk `claims`, `snapshot`, `sessions`, or `spawn_failures` documents.

Startup may unlink leftover `claims` / `snapshot` / `sessions` / `spawn_failures` files from older Orkie versions (ignore errors). Do not parse them.

### In memory (process-local)

Held on the shared state store (or equivalent runtime handles) for this process only. Empty at every start:

| Data | Purpose |
|------|---------|
| Intake snapshot | Last good fetch in this process for delta comparison |
| Claims | Assignment of config agent → issue for this process |
| Spawn-failure records | Consecutive attempt history for this process (three-strike budget resets each start) |
| Session records | Optional mirror of live sessions; the live ACP session table is authoritative |

### Process lock

1. Open/create `lock` for read/write (separate file under the state root).
2. Try exclusive `fcntl.flock` (POSIX). Orkie v1 targets Unix-like operators (macOS/Linux; systemd).
3. After the lock is held, read existing JSON if any. If `pid` is alive (`os.kill(pid, 0)` succeeds), release the flock and refuse start. If the pid is dead, missing, or the JSON is corrupt, write this process's `pid` and `started_at` in place, and keep the flock for the process lifetime.
4. On **normal shutdown** (both shutdown modes after cleanup): unlink `lock` while the flock is still held on that FD, then unlock and close. After a clean exit the lock file must not remain. After a crash, a leftover file with a dead pid is treated as stale on the next start (step 3).

Windows is out of scope for v1 locking; document the Unix requirement with the CLI.

### Logs

Append one complete line at a time, serialized per `agent_id`, then flush. Several sessions of one agent share the file. Redact any substring equal to the current `GITHUB_TOKEN` value before write. No rotation or size cap in v1. Permission-grant and permission-cancelled lines use the format in feature 02.

## Reasoning

- ADR 013: claims, snapshot, and spawn failures have no required effect after a blank-slate restart.
- Logs are operator execution history; they are not orchestration restore input.
- A separate lock file with flock + dead-pid takeover implements one live Orkie; removing the file on clean shutdown matches “once Orkie shuts down, the lock should not exist.”
- Replacing the lock file while holding flock would point the path at a new inode; unlink-then-unlock avoids leaving a durable name after exit.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Persist claims / snapshot / spawn failures | ADR 013; feature 02 blank-slate restart |
| Leave `lock` on disk after clean shutdown | Operator expectation: no lock file when Orkie is not running |
| PID-only file without flock | TOCTOU races between two starters |
| flock-only without pid record | Feature 02 requires pid and started_at for refuse messages |
| State inside `.orkie/` or the repo | Pollutes the project; breaks multi-clone sharing rules |
| Per-session log files | Feature 02: one log per config agent id with in-line session markers |
| SQLite single DB | Heavier; unnecessary for log and lock volumes |

## Consequences for design

- `orkie.state` exposes: `acquire_lock`, `release_lock` (unlink lock), in-memory get/set for claims/snapshot/spawn_failures, `append_log`, layout ensure, optional legacy-file scrub.
- There is no disk load of claims/snapshot/spawn_failures at bootstrap and no resume path for sessions.
- Dashboard and orchestration share the same in-memory store instance.
- Tests use a temporary home/state root via injectable base path.
