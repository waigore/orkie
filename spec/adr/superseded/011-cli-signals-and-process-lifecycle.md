# ADR 011: CLI, signals, and process lifecycle

## Status

Superseded by [011-1](011-1-cli-signals-and-process-lifecycle.md).

## Context

Feature [08](../../feature/08-cli-and-dashboard.md) defines the `orkie` command, continuous loop, interactive vs non-interactive behavior, single-instance refusal, and graceful shutdown. Feature [01](../../feature/01-project-bootstrap-and-config.md) shares the interactive principle. Design needs CLI surface, signal handling, and shutdown sequence.

## Decision

### CLI

- Console script: `orkie`.
- Library: **stdlib `argparse`** ([002](002-tech-stack-and-dependencies.md)).
- Arguments:
  - optional positional `project` directory (default: cwd)
  - optional `--port N` overriding `dashboard_port`
- No subcommands in v1 (run is the only mode).

### Process lifecycle

```text
parse args -> bootstrap ([003](003-config-load-and-bootstrap-sequence.md))
  -> start dashboard thread ([012](012-dashboard-stack-and-control-api.md))
  -> main loop sleep/poll until shutdown_event
  -> graceful shutdown -> exit
```

### Signals

- Handle **SIGINT** and **SIGTERM** with the same graceful shutdown path.
- Handlers are installed on the process main thread, which is also the main loop thread ([001](001-process-model-and-module-layout.md)); a handler only sets flags, and the loop thread runs the shutdown sequence.
- First signal: set `shutdown_event`; begin shutdown.
- Second SIGINT/SIGTERM during grace: set an immediate-kill flag; the grace wait polls it and kills remaining agent process groups at once, skipping the rest of the wait.

### Graceful shutdown sequence

1. Stop new intake cycles and new spawns.
2. Dashboard controls fail closed; no v1 control starts work ([012](012-dashboard-stack-and-control-api.md)).
3. Terminate ACP sessions ([006](006-acp-agent-runtime.md)).
4. Wait up to **30 seconds** for termination and claim-label release; then kill remaining agent process groups. A second signal during the wait skips it and kills at once.
5. Release issue claim labels still held; persist claims/sessions per feature 02 (failed label removal keeps local owner record, not working).
6. Remove session worktrees ([008](008-git-worktrees.md)).
7. Shut down the dashboard HTTP server and join its thread.
8. Flush state; release process lock flock ([004](004-local-state-format-and-process-lock.md)).
9. Exit **0** if every held claim label was released; **1** if any release failed.

### Single instance

Enforced by state lock ([004](004-local-state-format-and-process-lock.md)). Refuse start with an error naming `owner/name` when another live pid holds the lock.

### Interactive

Detection and prompt rules live in [003](003-config-load-and-bootstrap-sequence.md). CLI prints bootstrap errors and warn-only privilege gaps to stderr/stdout. Systemd unit is documented in feature 08 only; not shipped in-repo.

## Reasoning

- argparse matches a two-flag CLI without extra deps.
- One shutdown path for Ctrl-C and systemd avoids divergent cleanup bugs.
- Exit 1 on failed claim release makes supervisors and operators notice stuck remote labels.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Click/Typer | Unnecessary dependency for v1 flags |
| Subcommands (`orkie run`, `orkie status`) | Feature: one long-running process is the product |
| Separate shutdown for SIGTERM vs SIGINT | Feature requires the same path |
| Infinite wait for agents | 30s then kill is specified |

## Consequences for design

- `orkie.cli` owns signal handlers and exit codes; orchestration exposes `request_shutdown` / `release_all_claims`.
- Tests simulate shutdown_event without real signals where possible; one test may use `os.kill` in integration.
- Dashboard bind failure aborts before the loop (bootstrap step), so shutdown rules apply only after a successful start.
