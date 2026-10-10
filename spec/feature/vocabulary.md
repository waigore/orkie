# Shared vocabulary

Canonical terms for the feature specs. Feature files should link here instead of restating definitions. When a term's meaning changes, update this file and the owning feature's behavior sections together.

| Term | Meaning | Owning feature |
|------|---------|----------------|
| `.orkie/config.yaml` | Project config. Schema and defaults live in feature 01. | [01](01-project-bootstrap-and-config.md) |
| Config identity | Stable agent or babysitter `id`, plus name, role, command, and prompt. Comes from config. Not a live session. | [01](01-project-bootstrap-and-config.md) |
| Session identity | Generated id for one ACP spawn. Binds one config identity to exactly one issue or one PR. A new spawn is a new session id. | [04](04-acp-agent-runtime.md), [05](05-agent-orchestration.md) |
| ACP | Agent Client Protocol. How Orkie talks to agents for spawn, prompt, status, interrupt, and kill. | [04](04-acp-agent-runtime.md) |
| Connector | Abstract bridge between local task state and an issue tracker host. GitHub is the v1 implementation. | [03](03-connector-interface-and-github.md) |
| Required privilege | Tracker capability without which an enabled Orkie feature cannot run. Missing: interactive prompt or non-interactive hard fail. | [03](03-connector-interface-and-github.md#required-privileges) |
| Warn-only privilege | Probed capability not required for enabled features. Bootstrap may continue after a warning. | [03](03-connector-interface-and-github.md#required-privileges) |
| Intake issue | Open GitHub issue that is not a pull request and has at least one configured `issue_labels` entry. | [06](06-work-intake-and-issue-monitoring.md) |
| Intake snapshot | Last good local copy of the intake set used for delta comparison. | [02](02-local-state.md#intake-snapshot-fields) |
| Intake delta | Issues entering or leaving the eligible set, plus label changes needed for triggers and claim-label presence. | [06](06-work-intake-and-issue-monitoring.md) |
| Claim label | The single Orkie-owned tracker label applied to a claimed issue. Default `orkie:claimed`. Must not appear in `issue_labels`. Does not encode agent or session id. This remote label is the only claim status. | [01](01-project-bootstrap-and-config.md), [05](05-agent-orchestration.md) |
| Working | Whether a session process is actually running. Always false just after process start, until a successful spawn. | [02](02-local-state.md), [05](05-agent-orchestration.md) |
| Spawn failure | Failed ACP start for an issue or babysitter PR. The record history is the consecutive attempt count. Retried on later polls. After three consecutive failures on an issue, Orkie warns, flags the dashboard, and removes the claim label. Does not occupy a session slot. | [05](05-agent-orchestration.md), [02](02-local-state.md#spawn-failure-record-fields) |
| Local state | Per-user runtime data under `~/.local/share/orkie/<owner>--<repo>/` (home directory). | [02](02-local-state.md) |
| Session caps | Per-agent `max_concurrent_sessions` and project `max_concurrent_sessions`. Both default to 1. The babysitter does not consume them. | [01](01-project-bootstrap-and-config.md) |
| Swarm fit | Whether a remote claim label still fits the running sessions and caps. A working session is kept. Labels with no working session that do not fit are removed, highest issue numbers first. | [05](05-agent-orchestration.md) |
| Worktree | Dedicated git worktree for one session. | [05](05-agent-orchestration.md#worktrees) |
| 1:0–1 mapping | One session ↔ at most one issue (or one PR). One issue ↔ at most one Orkie agent. | [05](05-agent-orchestration.md) |
| Babysitter | Optional single config identity; at most one working session; bound to one selectable blocked non-draft PR. Agent decides when to stop. Does not use issue claims or issue session caps. | [07](07-pr-babysitter.md) |
| Merge-ready | Open, non-draft pull request whose connector mergeable state is `clean`. | [07](07-pr-babysitter.md) |
| Selectable blocked | Open, non-draft PR with known mergeable state not `clean`. Drafts are never selected. | [07](07-pr-babysitter.md) |
| Not selectable yet | Mergeable state is `unknown`, or the PR is a draft. Orkie waits for a later poll. | [07](07-pr-babysitter.md) |
| Dashboard | Local web UI on loopback (default port 8765 from `dashboard_port`, overridable with `--port`) with agent view and issue view. No auth beyond loopback. | [08](08-cli-and-dashboard.md) |
| Agent view | Working sessions and which issue or PR each is on, plus status, logs, and spawn failures. | [08](08-cli-and-dashboard.md) |
| Issue view | Intake issues that carry the claim label versus those that do not. The owning agent is the working session's agent, when a session is working. | [08](08-cli-and-dashboard.md) |
| Graceful shutdown | SIGINT or SIGTERM: stop new work, terminate agent subprocesses, release claim labels, persist local state, stop the dashboard. Wait at most 30 seconds, then kill remaining agent process groups. Second signal skips the wait. Exit 1 if a claim release failed. | [08](08-cli-and-dashboard.md) |
| Interactive | A TTY is available for operator prompts. May prompt (default config offer; required connector privilege gaps). | [01](01-project-bootstrap-and-config.md), [08](08-cli-and-dashboard.md) |
| Non-interactive | No TTY (systemd, pipes, CI). Never prompts; any error that would need operator consent fails hard. | [01](01-project-bootstrap-and-config.md), [08](08-cli-and-dashboard.md) |
