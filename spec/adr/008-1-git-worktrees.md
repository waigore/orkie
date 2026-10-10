# ADR 008: Git worktrees

## Status

Accepted

Supersedes [008](superseded/008-git-worktrees.md).

## Context

Feature [05](../feature/05-agent-orchestration.md#worktrees) requires a dedicated git worktree per session so concurrent agents do not share a checkout. The babysitter ([07](../feature/07-pr-babysitter.md)) uses the same policy. Clones of one GitHub repository on one machine share the state directory ([02](../feature/02-local-state.md)). Design needs location, base revision, tooling, and cleanup that still works when a later process starts from the other clone.

## Decision

### Tooling

Use the **`git` CLI** via `subprocess` (`orkie.worktree`). No pygit2/GitPython in v1 ([002-2](002-2-tech-stack-and-dependencies.md)). `git` must be on PATH; missing git fails spawn with a spawn-failure record.

### Location

`~/.local/share/orkie/<owner>--<repo>/worktrees/<session_id>/`

(same state root as [004-2](004-2-local-state-format-and-process-lock.md)).

### Base

- The worktree is created detached at the commit of the project checkout where Orkie was started.
- If that checkout is on a branch, the commit is that branch's HEAD. The new worktree is not attached to the branch name, because that branch is already checked out in the starting clone.
- If the starting checkout is detached, use that commit.
- Hold the human-facing branch name (or `detached`) in memory for the dashboard issue view header (feature 08). It is not a state-file field.

### Create / remove

| Moment | Action |
|--------|--------|
| Before ACP spawn | Add a detached worktree at the base commit |
| Session ends (agent exit, kill, shutdown, lost eligibility stop) | Remove the worktree |
| Spawn fails after worktree create | Remove the worktree before returning failure |

Store `worktree_path` on the session record when created.

Removal reads the owning git directory from the worktree itself. A later process, started from another clone of the same repository after a crash, uses that directory. If the owning checkout is gone, delete the worktree directory best-effort and continue. Cleanup failure does not block startup or shutdown. No checkout path is added to the state model.

### Agent cwd

ACP child `cwd` is the worktree path ([006-1](006-2-acp-agent-runtime.md)). Orkie does not share the primary project checkout as a writable agent workspace for sessions.

## Reasoning

- CLI git is universal in Orkie's target environment and avoids native library deps.
- State-dir worktrees keep the operator's clone clean and make cleanup owned by Orkie.
- A detached worktree at the start commit does not fight the branch already checked out in the primary clone.
- The worktree already points at its git directory, so shared per-repo state does not need a second record of which clone created it.
- Per-session paths match 1:0–1 session identity.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| All agents share the project checkout | Race on files and branches |
| Worktrees inside the project `.git/worktrees` only with ad-hoc paths under `/tmp` | Harder lifecycle; easier to orphan |
| pygit2 / GitPython | Extra deps; git CLI is enough |
| Persistent worktree reused across session ids | Vocabulary: new session id per spawn; cleanup on end |
| Attach the worktree to the primary branch name | Git refuses while that branch is checked out in the starting clone |
| Store the checkout path in local state | The worktree already identifies its git directory |

## Consequences for design

- `orkie.orchestration` calls `worktree.create` then `acp.spawn`, and `worktree.remove` on every terminal transition.
- Shutdown walks session worktree paths and removes them after ACP delete ([011-2](011-2-cli-signals-and-process-lifecycle.md)). Startup removes leftovers the same way.
- Tests can stub `orkie.worktree` to temp dirs without a real git repo when unit-testing orchestration alone; integration tests may use a temp git repo.
