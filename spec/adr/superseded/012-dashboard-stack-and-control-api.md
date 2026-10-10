# ADR 012: Dashboard stack and control API

## Status

Superseded by [012-1](../012-1-dashboard-stack-and-control-api.md).

## Context

Feature [08](../../feature/08-cli-and-dashboard.md) requires a loopback web UI with agent and issue views, log display, spawn-failure visibility, and interrupt/kill controls. Feature [04](../../feature/04-acp-agent-runtime.md) defines ACP interrupt vs kill. Design needs an HTTP stack, page model, and control API without a heavy web framework ([002](002-tech-stack-and-dependencies.md)).

## Decision

### Stack

- **stdlib** `http.server.ThreadingHTTPServer` bound to `127.0.0.1` only.
- Port: CLI `--port` if set, else `dashboard_port` (default 8765).
- HTML generated in `orkie.dashboard` with string templates and `html.escape`. No SPA, no Jinja2, no auth beyond loopback.
- Runs on a **background thread** ([001](001-process-model-and-module-layout.md)). Startup prints `http://127.0.0.1:<port>/`. Bind failure aborts bootstrap ([003](003-config-load-and-bootstrap-sequence.md)).

### Pages (v1)

| Path | View |
|------|------|
| `GET /` | Redirect or simple index linking to views |
| `GET /agents` | Agent view: working sessions (config id/name, session id, issue or PR, working), logs from `logs/<agent_id>.log` (filterable by session markers), spawn failures |
| `GET /issues` | Issue view: repo name; base branch or `detached`; claimed intake (owner agent, working session id if any) vs unclaimed; three-strike warnings when relevant |

Refresh: full page reload / simple meta refresh or manual refresh is enough in v1 (no WebSocket).

### Control API

| Method / path | Action |
|---------------|--------|
| `POST /sessions/<session_id>/interrupt` | ACP cancel current turn; session stays working; issue claim stays |
| `POST /sessions/<session_id>/kill` | ACP terminate via orchestration; issue claim released if any |

- CSRF: loopback-only v1 accepts simple form posts; no follow-up prompt endpoint.
- Handlers call into orchestration/ACP on the shared runtime. A single runtime lock guards the session table, the shared state-store handles, and the orchestration control callbacks, so request threads cannot corrupt the main loop.
- After shutdown begins, controls fail closed.

### Data sources

- Working status and bindings: in-memory session table + state store.
- Logs: read `logs/<agent_id>.log` ([004](004-local-state-format-and-process-lock.md)).
- Spawn failures: `spawn_failures` records.
- Never render `GITHUB_TOKEN`.

## Reasoning

- Two read-mostly views plus two POSTs do not justify FastAPI/Flask.
- ThreadingHTTPServer matches the threaded edge model and keeps deps at zero for HTTP.
- Routing kill through orchestration preserves claim invariants ([007](007-orchestration-cycle-and-claim-session-state-machine.md)).

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| FastAPI/Starlette/Flask | Extra stack for loopback ops UI |
| WebSockets / live push in v1 | Manual refresh meets monitoring needs |
| Dashboard auth (tokens, basic auth) | Feature: loopback only |
| Follow-up prompt box | Out of scope in features 04/08 |
| Serving dashboard without bind success | Feature: fail if port taken; no headless-without-UI mode in v1 |

## Consequences for design

- `orkie.dashboard` receives references to config, state store, and orchestration control callbacks at start.
- Interrupt does not clear claims; kill does for issue sessions; babysitter kill clears only the session ([010](010-pr-babysitter-lifecycle.md)).
- Offline tests can drive handlers with a fake orchestration double and temporary log files.
