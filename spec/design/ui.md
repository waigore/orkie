# UI

| Features | ADRs |
|----------|------|
| [01](../feature/01-project-bootstrap-and-config.md), [03](../feature/03-connector-interface-and-github.md), [08](../feature/08-cli-and-dashboard.md) | [011](../adr/011-2-cli-signals-and-process-lifecycle.md), [012](../adr/012-3-dashboard-stack-and-control-api.md) |

Operator surfaces: the CLI and the loopback dashboard. No SPA, no auth beyond loopback, no follow-up prompt box in v1. Permission grants are lines in the agent log, not a separate page.

---

## CLI

### Invocation

```text
orkie [project] [--port N]
```

| Argument | Meaning |
|----------|---------|
| `project` | Optional path to the Git project root (default: cwd) |
| `--port N` | Override `dashboard_port` from config |

No subcommands. Console script entry: `orkie` → `orkie.cli:main`.

### Interactive detection

Interactive iff `stdin` and `stdout` are both TTYs. Otherwise non-interactive (never prompts). No override flag.

### Output

| Event | Stream | Content |
|-------|--------|---------|
| Successful dashboard bind | stdout | `http://127.0.0.1:<port>/` (trailing slash optional; include host and port) |
| Bootstrap / validation errors | stderr | Actionable message naming path, field, repo, or privilege |
| Required privilege gaps (interactive) | stderr + prompt | List each missing capability; offer retry after fix or abort |
| Live lock refusal | stderr | Names `owner/name` and that another Orkie is running |
| Port in use | stderr | Names `127.0.0.1:<port>` |
| Three-strike claim drop | stderr | Warning naming issue number and agent |
| Intake fetch errors (running) | stderr | Error text; dashboard also shows last error |
| Worktree removal failure | stderr | Path and error; does not change the exit code |
| Warn-only privilege gaps | stderr | None expected in v1 (empty warn set) |

### Interactive prompts

| Prompt | When | Accept | Reject |
|--------|------|--------|--------|
| Create default `.orkie/config.yaml`? | Config missing + interactive | Write feature-01 scaffold; continue bootstrap | Exit non-zero; write nothing |
| Retry privilege check / abort? | Required privilege missing + interactive | Re-probe after operator fixes token/perms; abort exits | — |
| Shutdown choice | Interactive Ctrl-C and at least one agent session is live | Explicit `g` → graceful; explicit `n` → normal. Any other input asks again | — |

The shutdown prompt is:

```text
Live agent sessions are still running. Shut down how?
  [g] graceful — ask agents to wrap up (20s), then delete sessions
  [n] normal — delete sessions now
```

Signal handlers only set flags. The main thread prints this prompt and reads the answer. A second SIGINT or SIGTERM during the prompt SIGKILLs remaining agent process groups.

Non-interactive: missing config and missing privileges are hard failures with no prompt. SIGINT and SIGTERM are normal shutdown with no prompt.

### Signals

| Signal | Effect |
|--------|--------|
| SIGTERM | Normal shutdown. No prompt |
| SIGINT, non-interactive | Normal shutdown. No prompt |
| SIGINT, interactive, no live agent session | Normal shutdown. No prompt |
| SIGINT, interactive, live agent session | Main thread prompts for graceful or normal |
| Second SIGINT or SIGTERM during the prompt or the graceful 20 second wait | SIGKILL remaining agent process groups |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Shutdown finished local cleanup. Claims remain. Session records are deleted. A worktree that could not be removed is logged and does not change this code |
| non-zero | Bootstrap failure (invalid config, missing required privilege, lock held, port in use, corrupt state JSON, and the other bootstrap failures) |

### systemd

Documented sample unit lives in feature [08](../feature/08-cli-and-dashboard.md). Not shipped in the Orkie repo. Always non-interactive, so stop is normal shutdown.

---

## Dashboard

### Stack and bind

- `http.server.ThreadingHTTPServer` on `127.0.0.1` only
- Port: CLI `--port` if set, else `dashboard_port` (default `8765`)
- HTML via **Jinja2** templates under `orkie/templates/` (`PackageLoader`, autoescape on)
- CSS and other assets under `orkie/static/`, served at `GET /static/<path>` (v1: `dashboard.css` linked from the base layout)
- Full page reload (no WebSockets)
- Background thread; bind failure aborts bootstrap

### Navigation

Shared chrome on every HTML page (Jinja `base.html`):

| Element | Behavior |
|---------|----------|
| Stylesheet | `<link rel="stylesheet" href="/static/dashboard.css">` |
| Product name | `Orkie` link to `GET /` |
| Nav: Agents | `GET /agents` |
| Nav: Issues | `GET /issues` |
| Repo subtitle | `owner/name` when known |
| Intake error banner | If last intake error set, show redacted message + “as of last failed poll” |

No authentication UI.

### Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Index |
| GET | `/agents` | Agent view |
| GET | `/issues` | Issue view |
| GET | `/static/<path>` | Packaged static file (CSS in v1); 404 if missing; reject path traversal |
| POST | `/sessions/<session_id>/interrupt` | Cancel current ACP turn |
| POST | `/sessions/<session_id>/kill` | Delete session and drop an issue claim |

Controls are HTML forms (`method="post"`). CSRF: none (loopback-only). After POST: `303` redirect to `Referer` if same-origin path is `/agents` or `/issues`, else `/agents`.

| Control result | HTTP |
|----------------|------|
| Success | 303 redirect |
| Unknown session | 404 text/plain or simple HTML |
| Shutting down / fail closed | 503 |
| Lock acquisition — block until main cycle releases (no timeout in v1); then run one control |

Never render `GITHUB_TOKEN`.

---

## Page: Index (`GET /`)

**Purpose:** One composition pointing at the two views.

| Element | Content |
|---------|---------|
| Heading | Orkie |
| Line | Repository `owner/name` |
| Line | Dashboard URL reminder |
| CTAs | Link “Agent view” → `/agents`; link “Issue view” → `/issues` |

No session table on the index.

---

## Page: Agent view (`GET /agents`)

**Purpose:** Working sessions, logs (including permission grants), spawn failures, interrupt/kill.

### Working sessions table

One row per live session in the in-memory table.

| Column | Source |
|--------|--------|
| Config id | `agent_id` |
| Config name | config `name` for that id (agents or babysitter) |
| Session id | Orkie `session_id` |
| Bound work | `issue #<n>` or `PR #<n>` |
| Status | `working` |
| Actions | Interrupt form; Kill form |

**Empty state:** “No working sessions.”

### Per-session log panel

For each working session (or a selected session via in-page anchor `#session-<id>`):

- Read `logs/<agent_id>.log`
- Show lines containing `session_id=<session_id>` (last 200 lines after filter, newest at bottom)
- Those lines include `permission grant` and `permission cancelled`
- Empty: “No log lines for this session yet.”

### Spawn failures section

List records from `spawn_failures` for all agents (newest first).

| Column | Field |
|--------|-------|
| Agent | `agent_name` (`agent_id`) |
| Work | issue or PR number |
| Attempt | `attempt` |
| Released | yes/no from `released` |
| Error | `error` |
| At | `at` |

Highlight rows with `released == true` as warnings (“local claim dropped after three spawn failures” for issues).

**Empty state:** “No spawn failures recorded.”

### CTAs

| Control | Label | Effect |
|---------|-------|--------|
| Interrupt | “Interrupt” | POST interrupt; claim stays; session stays working; a pending permission is logged as `permission cancelled` |
| Kill | “Kill” | POST kill; ACP delete path; issue claim dropped; row disappears on refresh. Babysitter kill drops no issue claim |

No follow-up prompt field.

---

## Page: Issue view (`GET /issues`)

**Purpose:** Local claim status for operators.

### Header

| Element | Content |
|---------|---------|
| Repository | `owner/name` |
| Start checkout | Branch name or `detached` (in-memory from bootstrap) |

### Claimed intake

Intake issues from the latest snapshot that have a row in `claims`.

| Column | Content |
|--------|---------|
| Number | Issue number (link to `url` if present) |
| Title | Title |
| Labels | Comma-separated project labels |
| Owner | Claim `agent_id`. When a live session is bound to this issue, also that `session_id`. Otherwise “queued” |
| Warning | If any spawn-failure row for this issue has `attempt == 3`: three-strike warning |

### Unclaimed intake

Intake issues from the snapshot with no claim row. After a three-strike drop the issue appears here.

| Column | Content |
|--------|---------|
| Number | Issue number (link) |
| Title | Title |
| Labels | Comma-separated |
| Warning | If any spawn-failure row for this issue has `attempt == 3`: three-strike warning (“local claim dropped after three spawn failures”) |

### Empty states

- No snapshot yet: “No intake snapshot yet.”
- Snapshot empty: “No intake issues.”

Babysitter PRs are **not** listed on this page (agent view only).

### CTAs

None for claim or drop (orchestration owns claims). Optional link “Open agent view” → `/agents`. Refresh is the browser reload.

---

## Refresh model

Full page reload only. No auto-refresh meta tag required in v1 (operator reloads). If a meta refresh is added later, default interval should not be shorter than `poll_interval_seconds`; v1 ships without auto-refresh.

---

## Mapping to components

| UI action | Module |
|-----------|--------|
| CLI parse / signals / exit | `orkie.cli` |
| Pages and POST handlers | `orkie.dashboard` |
| Interrupt / kill | `dashboard` → `orchestration` → `acp` |
| Tables’ data | `state` store + live session table + config + intake `last_error` |
