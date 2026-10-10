# ADR 012: Dashboard stack and control API

## Status

Accepted

Supersedes [012](superseded/012-dashboard-stack-and-control-api.md).

## Context

Feature [08](../feature/08-cli-and-dashboard.md) requires a loopback web UI with agent and issue views, log display, spawn-failure visibility, and interrupt/kill controls. Feature [04](../feature/04-acp-agent-runtime.md) defines ACP interrupt vs kill. Design needs an HTTP stack, page model, and control API without a heavy web framework ([002-1](002-1-tech-stack-and-dependencies.md)).

## Decision

### Stack

- **stdlib** `http.server.ThreadingHTTPServer` bound to `127.0.0.1` only.
- Port: CLI `--port` if set, else `dashboard_port` (default 8765).
- HTML generated in `orkie.dashboard` with string templates and `html.escape`. No SPA, no Jinja2, no auth beyond loopback.
- Runs on a **background thread** ([001-1](001-1-process-model-and-module-layout.md)). Startup prints `http://127.0.0.1:<port>/`. Bind failure aborts bootstrap ([003-1](003-1-config-load-and-bootstrap-sequence.md)).
- Full page reload. No live push.

### Pages (v1)

| Path | View |
|------|------|
| `GET /` | Index linking to the two views |
| `GET /agents` | Agent view: working sessions (config id, name, session id, issue or PR, working), logs from `logs/<agent_id>.log` filtered by session markers, spawn failures |
| `GET /issues` | Issue view: repo name; base branch or `detached` from memory ([008-1](008-1-git-worktrees.md)); intake issues with the claim label, and the working session's agent and session id when one is working; intake issues without the label; three-strike warnings when a spawn-failure record says the label was removed |

### Control API

| Method / path | Action |
|---------------|--------|
| `POST /sessions/<session_id>/interrupt` | Orchestration cancels the current ACP turn. The session stays working. An issue label stays |
| `POST /sessions/<session_id>/kill` | Orchestration terminates the session. An issue session's claim label is removed. A babysitter kill does not change issue labels |

- CSRF: loopback-only v1 accepts form posts. No follow-up prompt endpoint.
- Handlers call orchestration, which calls ACP ([001-1](001-1-process-model-and-module-layout.md)). They take the cycle lock for that one action.
- After shutdown begins, controls fail closed.

### Data sources

- Working status and bindings: in-memory session table and the state store.
- Logs: read `logs/<agent_id>.log` ([004-1](004-1-local-state-format-and-process-lock.md)).
- Spawn failures: `spawn_failures` records. A successful spawn clears the records for that issue or PR, so the view follows the store.
- Claimed vs unclaimed intake: the latest intake snapshot and claim-label presence. The owning agent is the working session's agent.
- The last intake error, held in memory ([009-1](009-1-intake-poll-and-delta.md)).
- Never render `GITHUB_TOKEN`.

## Reasoning

- Two read-mostly views plus two POSTs do not justify FastAPI or Flask.
- ThreadingHTTPServer matches the threaded edge model and keeps HTTP deps at zero.
- Routing interrupt and kill through orchestration preserves the label rules ([007-1](007-1-orchestration-cycle-and-claim-session-state-machine.md)).
- The cycle lock is the one entry from the dashboard thread into the sync core.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| FastAPI/Starlette/Flask | Extra stack for a loopback ops UI |
| WebSockets or live push in v1 | A full page reload meets monitoring needs |
| Dashboard auth (tokens, basic auth) | Feature: loopback only |
| Follow-up prompt box | Out of scope in features 04 and 08 |
| Serving the dashboard without a successful bind | Feature: fail if the port is taken |
| Dashboard calls ACP directly | Label removal would leave orchestration |
| A queue in addition to the cycle lock | One lock covers cycle and controls |

## Consequences for design

- `orkie.dashboard` receives references to config, the state store, and orchestration control callbacks at start.
- Interrupt does not remove a claim label. Kill of an issue session does. Babysitter kill clears only that session ([010-1](010-1-pr-babysitter-lifecycle.md)).
- Offline tests can drive handlers with a fake orchestration double and temporary log files.
