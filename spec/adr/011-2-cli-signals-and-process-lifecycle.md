# ADR 011: CLI, signals, and process lifecycle

## Status

Accepted

Supersedes [011-1](superseded/011-1-cli-signals-and-process-lifecycle.md).

## Context

Feature [08](../feature/08-cli-and-dashboard.md) defines the `orkie` command, continuous loop, interactive vs non-interactive behavior, single-instance refusal, and two shutdown modes. Feature [01](../feature/01-project-bootstrap-and-config.md) shares the interactive principle. Design needs CLI surface, signal handling, and the shutdown sequence.

## Decision

### CLI

- Console script: `orkie`.
- Library: **stdlib `argparse`** ([002-2](002-2-tech-stack-and-dependencies.md)).
- Arguments:
  - optional positional `project` directory (default: cwd)
  - optional `--port N` overriding `dashboard_port`
- No subcommands in v1 (run is the only mode).

### Process lifecycle

```text
parse args -> bootstrap ([003-3](003-3-config-load-and-bootstrap-sequence.md))
  -> start dashboard thread ([012-3](012-3-dashboard-stack-and-control-api.md))
  -> main loop sleep/poll until shutdown_event
  -> normal or graceful shutdown -> exit 0
```

### Signals

- Handlers are installed on the process main thread, which is also the main loop thread ([001-2](001-2-process-model-and-module-layout.md)). A handler only sets flags. The main thread runs the prompt and the shutdown sequence.
- **SIGTERM**, and **SIGINT** when the process is not interactive: set `shutdown_event` for normal shutdown. No prompt.
- **SIGINT** when interactive and no agent session is live: normal shutdown. No prompt.
- **SIGINT** when interactive and at least one agent session is live: set a prompt flag. The main thread leaves the poll loop, asks for graceful or normal using the prompt text in feature 08, then runs that mode. Only an explicit `g` or `n` is accepted. From the moment the prompt flag is set, orchestration does not drop local claims on observed agent exits (same rule as after `shutdown_event`).
- A second SIGINT or SIGTERM during the prompt, or during the graceful 20 second wait, sets an immediate-kill flag. Remaining agent process groups are SIGKILLed.

### Normal shutdown

1. Stop new intake cycles and new spawns.
2. Dashboard controls fail closed ([012-3](012-3-dashboard-stack-and-control-api.md)).
3. End every live ACP session by the delete path ([006-1](006-1-acp-agent-runtime.md)).
4. Remove session worktrees ([008-1](008-1-git-worktrees.md)). A removal failure is logged and does not change the exit code.
5. Shut down the dashboard HTTP server and join its thread.
6. Delete session records. Leave `claims`, `snapshot`, `spawn_failures`, and agent logs. Release the process-lock flock ([004-2](004-2-local-state-format-and-process-lock.md)).
7. Exit **0**.

An agent exit observed after `shutdown_event` or the interactive shutdown-prompt flag is set — including during this sequence — does not drop its local claim.

### Graceful shutdown

1. Stop new intake cycles and new spawns.
2. Dashboard controls fail closed.
3. For each live session: `session/cancel`, then the fixed wrap-up prompt from feature 04. Pending permission requests are answered `cancelled`.
4. Wait **20 seconds**. Idle status does not end the wait early. A second signal SIGKILLs remaining process groups and continues cleanup.
5. End every remaining session by the delete path in normal shutdown step 3, then the same worktree, dashboard, state, and exit steps.

Claims are kept in both modes. Claim drop on agent exit is suppressed from the moment shutdown begins (`shutdown_event` or the prompt flag), not only inside the cleanup steps below. There is no label removal and no exit 1 for a tracker write.

### Single instance

Enforced by the state lock ([004-2](004-2-local-state-format-and-process-lock.md)). Refuse start with an error naming `owner/name` when another live pid holds the lock.

### Interactive

Detection lives in [003-3](003-3-config-load-and-bootstrap-sequence.md): stdin and stdout are both TTYs. The CLI prints bootstrap errors and warn-only privilege gaps to stderr or stdout. The systemd unit is documented in feature 08 only; it is not shipped in-repo. Under that unit the process is non-interactive, so SIGTERM is normal shutdown.

## Reasoning

- argparse matches a two-flag CLI without extra deps.
- Two shutdown modes match feature 08. SIGTERM stays non-interactive so a service stop does not wait on a prompt.
- The prompt runs on the main thread because that is where the operator's answer is read. Handlers only set flags.
- Exit 0 matches feature 08: local cleanup is the success condition. A worktree that cannot be removed is logged.
- Keeping claims lets the next start spawn again. Session records are deleted because sessions are not resumed.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Click/Typer | Unnecessary dependency for v1 flags |
| Subcommands (`orkie run`, `orkie status`) | Feature: one long-running process is the product |
| One shutdown path for SIGTERM and interactive Ctrl-C | Feature 08: Ctrl-C with a live agent prompts; SIGTERM is normal shutdown |
| Read the shutdown choice inside the signal handler | Handlers only set flags. The prompt blocks |
| 30 second `session/close` grace | Feature 04: delete path, 5 second process exit, and a separate 20 second wrap-up |
| Exit 1 when a GitHub label cannot be removed | There is no label removal. Exit is 0 after local cleanup |
| Drop local claims on process shutdown | Feature 05: shutdown keeps claims. Dashboard kill is the path that drops one |

## Consequences for design

- `orkie.cli` owns signal flags, the shutdown prompt, and the exit code. The poll loop stops on `shutdown_event` or the prompt flag. Orchestration exposes session end for both modes and does not drop claims once either flag is set.
- Tests simulate the flags without real signals where possible; one test may use `os.kill` in integration.
- Dashboard bind failure aborts before the loop (bootstrap step), so shutdown rules apply only after a successful start.
