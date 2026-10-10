# UI

| Features | ADRs |
|----------|------|
| [01](../feature/01-project-bootstrap-and-config.md), [03](../feature/03-connector-interface-and-github.md), [08](../feature/08-cli-and-dashboard.md) | [011](../adr/011-1-cli-signals-and-process-lifecycle.md), [012](../adr/012-1-dashboard-stack-and-control-api.md) |

Operator surfaces: the CLI and the loopback dashboard. No SPA, no auth beyond loopback, no follow-up prompt box in v1.

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

Interactive iff `stdin` and `stdout` are both TTYs. Otherwise non-interactive (never prompts).

### Output

| Event | Stream | Content |
|-------|--------|---------|
| Successful dashboard bind | stdout | `http://127.0.0.1:<port>/` (trailing slash optional; include host and port) |
| Bootstrap / validation errors | stderr | Actionable message naming path, field, repo, or privilege |
| Required privilege gaps (interactive) | stderr + prompt | List each missing capability; offer retry after fix or abort |
| Live lock refusal | stderr | Names `owner/name` and that another Orkie is running |
| Port in use | stderr | Names `127.0.0.1:<port>` |
| Three-strike claim release | stderr | Warning naming issue number and agent |
| Intake fetch errors (running) | stderr | Error text; dashboard also shows last error |
| Warn-only privilege gaps | stderr | None expected in v1 (empty warn set) |

### Interactive prompts

| Prompt | When | Accept | Reject |
|--------|------|--------|--------|
| Create default `.orkie/config.yaml`? | Config missing + interactive | Write feature-01 scaffold; continue bootstrap | Exit non-zero; write nothing |
| Retry privilege check / abort? | Required privilege missing + interactive | Re-probe after operator fixes token/perms; abort exits | — |

Non-interactive: both situations are hard failures with no prompt.

### Signals

| Signal | Effect |
|--------|--------|
| First SIGINT or SIGTERM | Start graceful shutdown |
| Second during grace | Immediate kill of remaining agent process groups |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Clean exit after shutdown with every stopped issue-session claim label removed; or clean paths that define success |
| non-zero | Bootstrap failure; or shutdown where at least one claim-label removal failed (exit **1**) |

### systemd

Documented sample unit lives in feature [08](../feature/08-cli-and-dashboard.md). Not shipped in the Orkie repo. Always non-interactive.

---

## Dashboard

### Stack and bind

- `http.server.ThreadingHTTPServer` on `127.0.0.1` only
- Port: CLI `--port` if set, else `dashboard_port` (default `8765`)
- HTML via string templates + `html.escape`
- Full page reload (no WebSockets)
- Background thread; bind failure aborts bootstrap

### Navigation

Shared chrome on every page:

| Element | Behavior |
|---------|----------|
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
| POST | `/sessions/<session_id>/interrupt` | Cancel current ACP turn |
| POST | `/sessions/<session_id>/kill` | Terminate session (+ release issue claim) |

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

**Purpose:** Working sessions, logs, spawn failures, interrupt/kill.

### Working sessions table

One row per live working session (from in-memory table ∩ disk `working` true; prefer in-memory handles as source of truth while running).

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

Highlight rows with `released == true` as warnings (“claim released after three spawn failures” for issues).

**Empty state:** “No spawn failures recorded.”

### CTAs

| Control | Label | Effect |
|---------|-------|--------|
| Interrupt | “Interrupt” | POST interrupt; claim stays; session stays working |
| Kill | “Kill” | POST kill; issue claim removed; row disappears on refresh |

No follow-up prompt field.

---

## Page: Issue view (`GET /issues`)

**Purpose:** Intake claim status for operators.

### Header

| Element | Content |
|---------|---------|
| Repository | `owner/name` |
| Start checkout | Branch name or `detached` (in-memory from bootstrap) |
| Claim label | Config `claim_label` (display only) |

### Claimed intake

Intake issues from the latest snapshot whose labels include `claim_label`.

| Column | Content |
|--------|---------|
| Number | Issue number (link to `url` if present) |
| Title | Title |
| Labels | Comma-separated |
| Owner | If a working session is bound to this issue: `agent_id` + `session_id`; else “labeled, not working” |
| Warning | If spawn-failure for this issue has `released == true` and still relevant (no later successful spawn): show three-strike warning |

### Unclaimed intake

Intake issues from the snapshot without `claim_label`.

| Column | Content |
|--------|---------|
| Number | Issue number (link) |
| Title | Title |
| Labels | Comma-separated |

### Empty states

- No snapshot yet: “No intake snapshot yet.”
- Snapshot empty: “No intake issues.”

Babysitter PRs are **not** listed on this page (agent view only).

### CTAs

None for claim/release (orchestration owns labels). Optional link “Open agent view” → `/agents`. Refresh is the browser reload.

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
