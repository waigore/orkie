# Shared vocabulary

Canonical terms for the feature specs. Feature files should link here instead of restating definitions. When a term's meaning changes, update this file and the owning feature's behavior sections together.

| Term | Meaning | Owning feature |
|------|---------|----------------|
| `.orkie/config.yaml` | Project config. Schema and defaults live in feature 01. | [01](01-project-bootstrap-and-config.md) |
| Config identity | Stable agent or babysitter `id`, plus name, role, command, and prompt. Comes from config. Not a live session. | [01](01-project-bootstrap-and-config.md) |
| Session identity | Generated id for one ACP spawn. Binds one config identity to exactly one issue or one PR. A new spawn is a new session id. Sessions are not resumed. | [04](04-acp-agent-runtime.md), [05](05-agent-orchestration.md) |
| ACP | Agent Client Protocol. How Orkie talks to agents for spawn, prompt, status, interrupt, and kill. | [04](04-acp-agent-runtime.md) |
| Connector | Abstract bridge between local task state and an issue tracker host. GitHub is the v1 implementation. Reads issues and pull requests. Does not write claim labels. | [03](03-connector-interface-and-github.md) |
| Required privilege | Tracker capability without which an enabled Orkie feature cannot run. Missing: interactive prompt or non-interactive hard fail. | [03](03-connector-interface-and-github.md#required-privileges) |
| Warn-only privilege | Probed capability not required for enabled features. Bootstrap may continue after a warning. | [03](03-connector-interface-and-github.md#required-privileges) |
| Intake issue | Open GitHub issue that is not a pull request and has at least one configured `issue_labels` entry. | [06](06-work-intake-and-issue-monitoring.md) |
| Intake snapshot | Last good local copy of the intake set used for delta comparison. | [02](02-local-state.md#intake-snapshot-fields) |
| Intake delta | Issues entering or leaving the eligible set, plus label changes needed for triggers. | [06](06-work-intake-and-issue-monitoring.md) |
| Claim | Local assignment of one config agent to one issue. Stored in Orkie state. Not a GitHub label. Source of truth for what Orkie will spawn next. At most one claim per issue. | [02](02-local-state.md#claim-record-fields), [05](05-agent-orchestration.md) |
| Queued claim | A saved claim with no working session, waiting because caps are full or spawn has not succeeded yet. Kept across shutdown. | [05](05-agent-orchestration.md) |
| Working | Whether a session process is actually running. No session is working just after process start, until a successful spawn. | [02](02-local-state.md), [05](05-agent-orchestration.md) |
| Spawn failure | Failed ACP start for an issue or babysitter PR. Each attempt is its own record. Retried on later polls. After three consecutive failures on an issue, Orkie warns, flags the dashboard, and drops the local claim. Does not occupy a session slot. | [05](05-agent-orchestration.md), [02](02-local-state.md#spawn-failure-record-fields) |
| Permission grant | Orkie's implicit approval of an ACP permission request. Written to the agent log and shown on the dashboard. The operator is not asked. | [04](04-acp-agent-runtime.md) |
| Local state | Per-user runtime data under `~/.local/share/orkie/<owner>--<repo>/` (home directory). | [02](02-local-state.md) |
| Session caps | Per-agent `max_concurrent_sessions` and project `max_concurrent_sessions`. Both default to 1. They count working issue sessions. The babysitter does not consume them. Claims above the cap stay queued. | [01](01-project-bootstrap-and-config.md) |
| Worktree | Dedicated git worktree for one session. Removed when that session ends. Leftovers are removed on the next start. | [05](05-agent-orchestration.md#worktrees) |
| 1:0–1 mapping | One session ↔ at most one issue (or one PR). One issue ↔ at most one Orkie claim. Another person or tool may still work that GitHub issue. | [05](05-agent-orchestration.md) |
| Babysitter | Optional single config identity; at most one working session; bound to one selectable blocked non-draft PR. Agent decides when to stop. Does not use issue claims or issue session caps. | [07](07-pr-babysitter.md) |
| Merge-ready | Open, non-draft pull request whose connector mergeable state is `clean`. | [07](07-pr-babysitter.md) |
| Selectable blocked | Open, non-draft PR with known mergeable state not `clean`. Drafts are never selected. | [07](07-pr-babysitter.md) |
| Not selectable yet | Mergeable state is `unknown`, or the PR is a draft. Orkie waits for a later poll. | [07](07-pr-babysitter.md) |
| Dashboard | Local web UI on loopback (default port 8765 from `dashboard_port`, overridable with `--port`) with agent view and issue view. No auth beyond loopback. | [08](08-cli-and-dashboard.md) |
| Agent view | Working sessions and which issue or PR each is on, plus status, logs (including permission grants), and spawn failures. | [08](08-cli-and-dashboard.md) |
| Issue view | Intake issues that have a local claim versus those that do not. The owner is the claim's config agent. A live session id is shown when one is working. | [08](08-cli-and-dashboard.md) |
| Normal shutdown | Delete each live ACP session, then SIGKILL that process group if it has not exited within 5 seconds. Delete session records and worktrees. Keep claims. Exit 0. Used for SIGTERM, non-interactive SIGINT, and Ctrl-C when no agent is live. | [08](08-cli-and-dashboard.md) |
| Graceful shutdown | Cancel each live session, send one fixed wrap-up prompt, wait 20 seconds, then run normal shutdown's delete path. Keep claims. Offered on interactive Ctrl-C when an agent is live. | [08](08-cli-and-dashboard.md) |
| Interactive | stdin and stdout are both TTYs. May prompt (default config offer; required connector privilege gaps; Ctrl-C shutdown choice when an agent is live). No override flag. | [01](01-project-bootstrap-and-config.md), [08](08-cli-and-dashboard.md) |
| Non-interactive | No TTY (systemd, pipes, CI). Never prompts; any error that would need operator consent fails hard. SIGINT and SIGTERM use normal shutdown. | [01](01-project-bootstrap-and-config.md), [08](08-cli-and-dashboard.md) |
