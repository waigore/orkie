# ADR 008: Git worktrees

## Status

Superseded by [008-1](../008-1-git-worktrees.md).

## Context

Feature [05](../../feature/05-agent-orchestration.md#worktrees) requires a dedicated git worktree per session so concurrent agents do not share a checkout. The babysitter ([07](../../feature/07-pr-babysitter.md)) uses the same policy. Design needs location, base revision, tooling, and cleanup triggers.

## Decision

### Tooling

Use the **`git` CLI** via `subprocess` (`orkie.worktree`). No pygit2/GitPython in v1 ([002](002-tech-stack-and-dependencies.md)). `git` must be on PATH; missing git fails spawn with a spawn-failure record.

### Location

`~/.local/share/orkie/<owner>--<repo>/worktrees/<session_id>/`  
(same state root as [004](004-local-state-format-and-process-lock.md)).

### Base

- Prefer the branch of the project checkout where Orkie was started.
- If detached HEAD, use that commit as the worktree base.
- Record the human-facing branch name (or `detached`) for the dashboard issue view header (feature 08).

### Create / remove

| Moment | Action |
|--------|--------|
| Before ACP spawn | `git worktree add <path> <base>` (or equivalent that checks out base at path) |
| Session ends (agent exit, kill, shutdown, lost eligibility stop) | `git worktree remove --force` (or remove + prune) and delete path if needed |
| Spawn fails after worktree create | Remove worktree before returning failure |

Store `worktree_path` on the session record when created.

### Agent cwd

ACP child `cwd` is the worktree path ([006](006-acp-agent-runtime.md)). Orkie does not share the primary project checkout as a writable agent workspace for sessions.

## Reasoning

- CLI git is universal in Orkie's target environment and avoids native library deps.
- State-dir worktrees keep the operator's clone clean and make cleanup owned by Orkie.
- Per-session paths match 1:0–1 session identity.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| All agents share the project checkout | Race on files and branches |
| Worktrees inside the project `.git/worktrees` only with ad-hoc paths under `/tmp` | Harder lifecycle; easier to orphan |
| pygit2 / GitPython | Extra deps; git CLI is enough |
| Persistent worktree reused across session ids | Vocabulary: new session id per spawn; cleanup on end |

## Consequences for design

- `orkie.orchestration` calls `worktree.create` then `acp.spawn`, and `worktree.remove` on every terminal transition.
- Shutdown walks all session records/paths and removes worktrees after ACP terminate.
- Tests can stub `orkie.worktree` to temp dirs without a real git repo when unit-testing orchestration alone; integration tests may use a temp git repo.
