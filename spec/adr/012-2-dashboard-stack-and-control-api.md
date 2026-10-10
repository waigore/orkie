# ADR 012: Dashboard stack and control API

## Status

Accepted

Supersedes [012-1](superseded/012-1-dashboard-stack-and-control-api.md).

## Context

Feature [08](../feature/08-cli-and-dashboard.md) requires a loopback web UI with agent and issue views, log display including permission grants, spawn-failure visibility, and interrupt/kill controls. Feature [04](../feature/04-acp-agent-runtime.md) defines ACP interrupt vs kill. Design needs an HTTP stack, page model, and control API without a heavy web framework ([002-1](002-1-tech-stack-and-dependencies.md)).

## Decision

### Stack

- **stdlib** `http.server.ThreadingHTTPServer` bound to `127.0.0.1` only.
- Port: CLI `--port` if set, else `dashboard_port` (default 8765).
- HTML generated in `orkie.dashboard` with string templates and `html.escape`. No SPA, no Jinja2, no auth beyond loopback.
- Runs on a **background thread** ([001-2](001-2-process-model-and-module-layout.md)). Startup prints `http://127.0.0.1:<port>/`. Bind failure aborts bootstrap ([003-2](003-2-config-load-and-bootstrap-sequence.md)).
- Full page reload. No live push.

### Pages (v1)

| Path | View |
|------|------|
| `GET /` | Index linking to the two views |
| `GET /agents` | Agent view: working sessions (config id, name, session id, issue or PR, working), logs from `logs/<agent_id>.log` filtered by `session_id=` (including permission-grant lines), spawn failures |
| `GET /issues` | Issue view: repo name; base branch or `detached` from memory ([008-1](008-1-git-worktrees.md)); intake issues that have a local claim, with that claim's `agent_id` and the live session id when one is working; intake issues without a claim; three-strike warnings on either list when any spawn-failure row for that issue has `attempt` 3 (after a three-strike drop the issue is unclaimed) |

There is no separate permissions page. Grants are lines in the agent log.

### Control API

| Method / path | Action |
|---------------|--------|
| `POST /sessions/<session_id>/interrupt` | Orchestration cancels the current ACP turn and answers a pending permission as `cancelled`. The session stays working. A local claim stays |
| `POST /sessions/<session_id>/kill` | Orchestration runs the ACP delete path. An issue session's local claim is dropped. A babysitter kill drops no issue claim |

- CSRF: loopback-only v1 accepts form posts. No follow-up prompt endpoint.
- Handlers call orchestration, which calls ACP ([001-2](001-2-process-model-and-module-layout.md)). They take the cycle lock for that one action.
- After shutdown begins, controls fail closed (HTTP 503).

### Data sources

- Working status and bindings: in-memory session table and the state store.
- Logs: read `logs/<agent_id>.log` and filter by `session_id=` ([004-2](004-2-local-state-format-and-process-lock.md)).
- Spawn failures: `spawn_failures` records. A successful spawn clears the records for that issue or PR, so the view follows the store.
- Claimed vs unclaimed intake: the latest intake snapshot joined to local claims. The owner is the claim's `agent_id`. The session id comes from the live session table.
- The last intake error, held in memory ([009-2](009-2-intake-poll-and-delta.md)).
- Never render `GITHUB_TOKEN`.

## Reasoning

- Two read-mostly views plus two POSTs do not justify FastAPI or Flask.
- ThreadingHTTPServer matches the threaded edge model and keeps HTTP deps at zero.
- Routing interrupt and kill through orchestration preserves claim rules ([007-2](007-2-orchestration-cycle-and-claim-session-state-machine.md)).
- The cycle lock is the one entry from the dashboard thread into the sync core.
- Permission grants are already agent-log lines, so the agent view is the place to read them.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| FastAPI/Starlette/Flask | Extra stack for a loopback ops UI |
| WebSockets or live push in v1 | A full page reload meets monitoring needs |
| Dashboard auth (tokens, basic auth) | Feature: loopback only |
| Follow-up prompt box | Out of scope in features 04 and 08 |
| A permissions page | Feature 08: grants are visible in the agent log |
| Serving the dashboard without a successful bind | Feature: fail if the port is taken |
| Dashboard calls ACP directly | Claim drop would leave orchestration |
| A queue in addition to the cycle lock | One lock covers cycle and controls |
| Issue view keyed by a GitHub label | The owner is the local claim |

## Consequences for design

- `orkie.dashboard` receives references to config, the state store, and orchestration control callbacks at start.
- Interrupt does not drop a claim. Kill of an issue session does. Babysitter kill clears only that session ([010-2](010-2-pr-babysitter-lifecycle.md)).
- Offline tests can drive handlers with a fake orchestration double and temporary log files.
