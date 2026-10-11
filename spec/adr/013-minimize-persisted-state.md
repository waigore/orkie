# ADR 013: Minimize persisted state

## Status

Accepted

## Context

Orkie keeps a per-user state root for each GitHub repository ([02](../feature/02-local-state.md), [004-3](004-3-local-state-format-and-process-lock.md)). Earlier revisions persisted claims, the intake snapshot, spawn-failure history, and a sessions document across process stop and crash. That forced restore, sync, and “fulfill after restart” paths in orchestration and intake ([007](007-3-orchestration-cycle-and-claim-session-state-machine.md), [009](009-3-intake-poll-and-delta.md)).

Most of that data only coordinates work inside one live Orkie process. Persisting it did not improve product outcomes after a blank-slate restart; it added complexity.

## Decision

**General principle.** Before adding or keeping any on-disk runtime data, examine critically whether it must outlive the process. Prefer process-local (in-memory) data when a fresh start can rebuild from the remote tracker, config, and a new orchestration cycle. Persist only when the data is required for Orkie’s function after restart, or is operator-facing history that must survive (today: the process lock while running, agent logs, and live worktree directories).

Apply this when:

- proposing new state files or fields
- reviewing existing local-state layout
- deciding restore, migration, or “recover after crash” behavior

Do not invent restore/sync scenarios for data that a blank-slate restart does not need.

**What this implies for v1 local state** (detail in [004-3](004-3-local-state-format-and-process-lock.md) and feature [02](../feature/02-local-state.md)):

| Data | Persistence |
|------|-------------|
| Process lock | On disk only while this process holds it; removed on normal shutdown |
| Agent logs | On disk (execution history for the dashboard) |
| Worktrees | On disk for the life of a live session; leftovers removed at start |
| Claims, intake snapshot, spawn failures, session records | In memory for this process only; empty after every start |

## Reasoning

- Fewer durable documents mean fewer corrupt-file bootstrap failures and no cross-restart claim or three-strike restore logic.
- A restart that re-fetches intake and re-claims under current config matches operator expectation that stopping Orkie clears in-flight assignment coordination.
- Logs remain durable because they are history for humans, not orchestration restore input.
- The principle is standing guidance for future ADRs and design, not a one-off layout tweak.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Persist claims so the next start fulfills the same agent assignment | Continuity of `agent_id` across restarts is not required; re-claim under current triggers is enough |
| Persist snapshot to avoid a full intake sweep after restart | A full remote sweep on start is acceptable and simpler |
| Persist spawn failures so three-strike survives restart | Attempt budget is per process lifetime by product choice |
| Persist everything that is “nice to see” on the dashboard after restart | Dashboard can show live process state; only logs need durable history |

## Consequences for design

- Feature [02](../feature/02-local-state.md) and ADR [004-3](004-3-local-state-format-and-process-lock.md) list only lock, logs, and worktrees as on-disk concerns.
- Orchestration and intake treat claims, snapshot, and spawn failures as process-local store fields with no load-from-disk bootstrap path.
- New durable state requires an explicit argument under this ADR, then an update to feature 02 and ADR 004.
