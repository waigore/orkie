# ADR 008: Git worktrees

## Status

Accepted

Supersedes [008-1](superseded/008-1-git-worktrees.md).

## Context

Feature [05](../feature/05-agent-orchestration.md#worktrees) requires a dedicated git worktree per session so concurrent agents do not share a checkout, and requires each new worktree to start at the latest commit of the branch on `origin`. The babysitter ([07](../feature/07-pr-babysitter.md)) uses the same policy. Clones of one GitHub repository on one machine share the state directory ([02](../feature/02-local-state.md)). Design needs location, sync-before-create, tooling, and cleanup that still works when a later process starts from the other clone.

## Decision

### Tooling

Use the **`git` CLI** via `subprocess` (`orkie.worktree`). No pygit2/GitPython in v1 ([002-2](002-2-tech-stack-and-dependencies.md)). `git` must be on PATH; missing git fails spawn with a spawn-failure record.

### Location

`~/.local/share/orkie/<owner>--<repo>/worktrees/<session_id>/`

(same state root as [004-3](004-3-local-state-format-and-process-lock.md)).

### Base (sync before create)

Remote `origin` is source of truth. Before each worktree create (once per spawn):

1. `git fetch origin`
2. Resolve the branch: the start checkout's current branch name, or — when HEAD is detached — the remote default branch from `refs/remotes/origin/HEAD` (strip the `origin/` prefix). Missing remote or default-branch ref fails the sync.
3. If not already on that branch, `git checkout <branch>`
4. `git reset --hard origin/<branch>` (discards local unpushed or diverged commits and dirty tracked state on the start checkout)
5. Create a **detached** worktree at the resulting `HEAD` commit

Hold the human-facing branch name and tip commit in memory for the dashboard issue view header (feature 08). Update that memory after each successful sync. It is not a state-file field. `"detached"` may appear only before the first successful sync; after sync the name is always a branch.

Existing live session worktrees are not moved; they stay on their spawn-time tip.

### Create / remove

| Moment | Action |
|--------|--------|
| Before ACP spawn | Sync to `origin` as above, then add a detached worktree at the synced tip |
| Sync fails | Do not create a worktree; return failure for the spawn-failure path |
| Session ends (agent exit, kill, shutdown, lost eligibility stop) | Remove the worktree |
| Spawn fails after worktree create | Remove the worktree before returning failure |

Store `worktree_path` on the session record when created.

Removal reads the owning git directory from the worktree itself. A later process, started from another clone of the same repository after a crash, uses that directory. If the owning checkout is gone, delete the worktree directory best-effort and continue. Cleanup failure does not block startup or shutdown. No checkout path is added to the state model.

### Agent cwd

ACP child `cwd` is the worktree path ([006-2](006-2-acp-agent-runtime.md)). Orkie does not share the primary project checkout as a writable agent workspace for sessions.

## Reasoning

- CLI git is universal in Orkie's target environment and avoids native library deps.
- State-dir worktrees keep agent file work off the operator's primary working tree while Orkie still uses that tree as the git directory for fetch/reset.
- Hard-reset to `origin/<branch>` matches the product rule that agents always start on the latest remote tip; preserving local commits would hand agents stale or divergent specs.
- A detached worktree at the tip does not fight the branch already checked out in the starting clone.
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
| Freeze bootstrap HEAD for the process lifetime | Agents would miss remote updates to code and specs |
| Fast-forward only / preserve local commits | Diverges from remote-as-truth; agents would not see the latest tip |
| Sync once per poll cycle only | A later spawn in the same cycle could still start stale after a remote push |

## Consequences for design

- `orkie.worktree.create` syncs then adds the worktree; sync failure raises before any worktree path is left behind.
- `orkie.orchestration` calls `worktree.create` then `acp.spawn`, refreshes in-memory tip/branch after create, and `worktree.remove` on every terminal transition.
- Bootstrap still calls `resolve_base` for an initial dashboard value; that value is not frozen for the process after syncs.
- Shutdown walks session worktree paths and removes them after ACP delete ([011-3](011-3-cli-signals-and-process-lifecycle.md)). Startup removes leftovers the same way.
- Tests can stub `orkie.worktree` to temp dirs without a real git repo when unit-testing orchestration alone; integration tests may use a temp git repo with a file remote.
