# ADR 012: Dashboard stack and control API

## Status

Accepted

Supersedes [012-2](superseded/012-2-dashboard-stack-and-control-api.md).

## Context

Feature [08](../feature/08-cli-and-dashboard.md) requires a loopback web UI with agent and issue views, log display including permission grants, spawn-failure visibility, and interrupt/kill controls. Feature [04](../feature/04-acp-agent-runtime.md) defines ACP interrupt vs kill. Design needs an HTTP stack, page model, and control API without a heavy web framework ([002-2](002-2-tech-stack-and-dependencies.md)). Markup and CSS must stay maintainable as pages grow.

## Decision

### Stack

- **stdlib** `http.server.ThreadingHTTPServer` bound to `127.0.0.1` only.
- Port: CLI `--port` if set, else `dashboard_port` (default 8765).
- HTML via **Jinja2** templates under `orkie/templates/` (`PackageLoader`, autoescape on). Handlers build frozen view models, then render a named template. No SPA, no auth beyond loopback.
- CSS and other static assets live under `orkie/static/` and are served at `GET /static/<path>` (files only, no directory listing). Path resolution must stay under the package static root (reject `..` and absolute escapes). v1 ships `dashboard.css`; templates link it from the base layout.
- Runs on a **background thread** ([001-2](001-2-process-model-and-module-layout.md)). Startup prints `http://127.0.0.1:<port>/`. Bind failure aborts bootstrap ([003-4](003-4-config-load-and-bootstrap-sequence.md)).
- Full page reload. No live push.

### Pages (v1)

| Path | View |
|------|------|
| `GET /` | Index linking to the two views |
| `GET /agents` | Agent view: working sessions (config id, name, session id, issue or PR, working), logs from `logs/<agent_id>.log` filtered by `session_id=` (including permission-grant lines), spawn failures |
| `GET /issues` | Issue view: repo name; base branch or `detached` from memory ([008-2](008-2-git-worktrees.md)); intake issues that have a local claim, with that claim's `agent_id` and the live session id when one is working; intake issues without a claim; three-strike warnings on either list when any spawn-failure row for that issue has `attempt` 3 (after a three-strike drop the issue is unclaimed) |
| `GET /static/<path>` | Packaged static file (e.g. `dashboard.css`) |

There is no separate permissions page. Grants are lines in the agent log.

Templates use a shared `base.html` (nav, intake error banner, stylesheet link) and page templates that extend it. Shared fragments live under `orkie/templates/partials/`.

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
- Logs: read `logs/<agent_id>.log` and filter by `session_id=` ([004-3](004-3-local-state-format-and-process-lock.md)).
- Spawn failures: in-memory spawn-failure records. A successful spawn clears the records for that issue or PR, so the view follows the store.
- Claimed vs unclaimed intake: the latest in-memory intake snapshot joined to process-local claims. The owner is the claim's `agent_id`. The session id comes from the live session table.
- The last intake error, held in memory ([009-3](009-3-intake-poll-and-delta.md)).
- Never render `GITHUB_TOKEN`.

## Reasoning

- Two read-mostly views plus two POSTs do not justify FastAPI or Flask.
- ThreadingHTTPServer matches the threaded edge model; adding a static-file branch keeps HTTP deps at zero beyond Jinja2 for markup.
- Jinja templates and external CSS separate handlers, view models, markup, and presentation so new pages and assets extend without rewriting chrome in Python.
- Routing interrupt and kill through orchestration preserves claim rules ([007-3](007-3-orchestration-cycle-and-claim-session-state-machine.md)).
- The cycle lock is the one entry from the dashboard thread into the sync core.
- Permission grants are already agent-log lines, so the agent view is the place to read them.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| FastAPI/Starlette/Flask | Extra stack for a loopback ops UI |
| Inline `<style>` or CSS in Python strings | Harder to maintain and extend than a packaged stylesheet |
| CDN stylesheets | Dashboard must work offline from the installed package |
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
- Templates live under `orkie/templates/`; static assets under `orkie/static/`; both ship as package data ([002-2](002-2-tech-stack-and-dependencies.md)).
- Interrupt does not drop a claim. Kill of an issue session does. Babysitter kill clears only that session ([010-2](010-2-pr-babysitter-lifecycle.md)).
- Offline tests can drive handlers with a fake orchestration double and temporary log files, and assert static CSS responses.
