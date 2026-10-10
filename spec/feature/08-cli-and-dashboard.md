# Feature: CLI and Dashboard

## Description

Orkie is a long-running process started from the command line. An operator either points Orkie at a project directory (a Git repo with `.orkie/config.yaml`) or starts it from inside that directory so bootstrap can run. After start, Orkie runs continuously (intake, orchestration, and the optional babysitter) and serves a basic local web UI dashboard on loopback. The default address is `http://127.0.0.1:8765`. The port defaults to `8765` from config (`dashboard_port`) and may be overridden by a CLI flag. The process prints the bound URL at startup.

The dashboard has two simple views:

- **Agent view**: spawned agents (sessions) and which issue or PR each is working on, plus status and logs. The log panel reads `logs/<agent_id>.log` filtered by `session_id=`, so permission grants appear there.
- **Issue view**: intake issues that have a local claim (and which config agent owns them) versus intake issues that do not. A live session id is shown when one is working.

It can interrupt or kill a session. Killing an issue session ends it by the ACP delete path and drops its local claim so the next poll does not respawn that issue from the old claim. Interrupt cancels the current turn and leaves the claim in place. v1 has no follow-up prompt box. Spawn failures (including three-strike claim drops) are visible in both views as appropriate.

The process can be stopped from a terminal with Ctrl-C (SIGINT), or by a supervisor with SIGTERM. There are two shutdown modes. Both delete live ACP sessions, delete session records, attempt worktree removal, keep local claims, and exit 0. A worktree that cannot be removed is logged and does not change the exit code.

- **Normal shutdown** deletes each live session now: `session/delete` when the agent advertised it, then SIGKILL if that process has not exited within 5 seconds (see [04-acp-agent-runtime.md](04-acp-agent-runtime.md#session-end)).
- **Graceful shutdown** cancels each live session, sends the fixed wrap-up prompt, waits 20 seconds, then runs the same delete path.

Ctrl-C on an interactive process prompts when any agent session is live, and the operator chooses graceful or normal. No live session means normal shutdown immediately, with no prompt. SIGTERM, and SIGINT when the process is not interactive, are normal shutdown with no prompt. A second SIGINT or SIGTERM during the prompt or during the 20 second wait SIGKILLs remaining agent process groups.

Project-related runtime state remains under the per-user path described in [02-local-state.md](02-local-state.md). A second live process for the same GitHub repository refuses to start.

**Non-interactive principle:** When stdin and stdout are not both TTYs (systemd, pipes, CI), Orkie never prompts. Any condition that would need operator consent or an interactive choice is a hard failure, except shutdown, which uses normal shutdown. Interactive mode may prompt (default config offer; required connector privilege gaps; the Ctrl-C shutdown choice). See [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md) and [03-connector-interface-and-github.md](03-connector-interface-and-github.md#required-privileges).

## Use cases

Actors are defined in [users.md](users.md).

- **Operator**: Starts Orkie from a shell against a project and leaves it running; stops it with Ctrl-C when done; reads bootstrap errors and connector warnings from CLI output before relying on the dashboard.
- **Dashboard user**: Monitors agents and issues, permission grants, spawn failures, and interrupts or kills a session without stopping the whole Orkie process.
- **Host administrator**: Runs Orkie as a systemd service using the same long-running process. The service is non-interactive, so stop and restart use normal shutdown.

## User stories

### Start from an explicit project path

**Given** a Git project with `.orkie/config.yaml` at a known filesystem path  
**When** the operator runs Orkie with that path as the target  
**Then** Orkie uses that directory as the project root, runs bootstrap, and enters the continuous loop if bootstrap succeeds

### Start from the current working directory

**Given** the operator's shell is inside a configured Orkie project  
**When** the operator starts Orkie without an explicit path  
**Then** Orkie treats the current directory as the project root and bootstraps the same way

### Continuous autonomous loop after start

**Given** bootstrap succeeded  
**When** the CLI process remains running  
**Then** intake and orchestration run continuously without a further CLI command per issue

### Serve a local web dashboard

**Given** bootstrap succeeded and the chosen loopback port is free  
**When** the process enters the continuous loop  
**Then** it binds `127.0.0.1:<port>` only, prints `http://127.0.0.1:<port>` to the CLI, and serves the dashboard there with no authentication beyond loopback. `<port>` is the CLI override if given, otherwise `dashboard_port` from config (default `8765`)

### Override the dashboard port on the CLI

**Given** the operator starts Orkie with `--port <n>`  
**When** the dashboard binds  
**Then** that port is used instead of `dashboard_port` from config

### Fail when the dashboard port is taken

**Given** the chosen `127.0.0.1:<port>` is already in use  
**When** Orkie tries to bind the dashboard  
**Then** startup fails with a message that names that address, and the orchestration loop does not keep running without a dashboard

### Agent view shows spawned work and permission grants

**Given** the dashboard agent view is open  
**When** the page loads or refreshes  
**Then** it lists each working session: config id, config name, session id, bound issue or PR number, working status, and the last lines of `logs/<agent_id>.log` filtered by that `session_id=`. Those lines include permission grants. It also surfaces spawn-failure records for that agent (attempt number, redacted error, and whether a three-strike drop happened)

### Issue view shows local claims

**Given** the dashboard issue view is open  
**When** the page loads or refreshes  
**Then** it shows the GitHub repository name and the branch of the checkout where Orkie was started (or `detached`). It lists intake issues that have a local claim, with that claim's config agent id and, when a session is working, that session id. It lists intake issues without a claim separately. An issue that has any spawn-failure row with `attempt` 3 is flagged as a warning in whichever list it appears in (after a three-strike drop the issue is unclaimed)

### Spawn failure stays visible across retries

**Given** a spawn has failed and fewer than three consecutive failures have occurred for that issue  
**When** the operator opens or refreshes the dashboard  
**Then** that failure is listed with the attempt number. After a successful spawn the failure clears. After the third failure the claim drop is flagged and warned so the operator can see that Orkie gave up on that claim

### Kill a session from the dashboard

**Given** one or more sessions are working  
**When** the operator kills a specific session in the dashboard  
**Then** Orkie ends that session by the ACP delete path (see [04-acp-agent-runtime.md](04-acp-agent-runtime.md)). An issue session's local claim is dropped. The dashboard shows that session as gone. Other sessions keep running. Killing a babysitter session drops no issue claim

### Interrupt a session from the dashboard

**Given** a session is working  
**When** the operator interrupts that session  
**Then** Orkie cancels the current ACP turn and logs a pending permission as `permission cancelled`. The session stays working, an issue claim stays if present, and the dashboard does not offer a way to send a follow-up prompt

### Missing config is offered on the interactive CLI only

**Given** `.orkie/config.yaml` is missing in the target project and the process is interactive  
**When** the operator starts Orkie  
**Then** the CLI offers to create the default config (accept continues bootstrap; reject exits without starting the loop) as specified in [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md)

### Non-interactive start never prompts

**Given** Orkie is started non-interactive (stdin and stdout are not both TTYs), including under systemd  
**When** config is missing, a required connector privilege is missing, or any other bootstrap error needs operator input  
**Then** Orkie fails hard with a clear error and does not prompt

### Bootstrap failures stay on the CLI

**Given** YAML is invalid, the operator rejected default config creation, `GITHUB_TOKEN` is missing, or a required tracker capability is missing  
**When** bootstrap cannot complete  
**Then** the CLI reports the failure clearly and does not present a healthy dashboard for a project that never bootstrapped. Required privilege handling follows [03-connector-interface-and-github.md](03-connector-interface-and-github.md#required-privileges)

### Ctrl-C asks how to stop when agents are live

**Given** Orkie is running in an interactive terminal and at least one agent session is live  
**When** the operator presses Ctrl-C (SIGINT)  
**Then** Orkie prompts before shutdown proceeds:

```text
Live agent sessions are still running. Shut down how?
  [g] graceful — ask agents to wrap up (20s), then delete sessions
  [n] normal — delete sessions now
```

An explicit `g` starts graceful shutdown. An explicit `n` starts normal shutdown. Any other input asks again. A second SIGINT or SIGTERM during the prompt SIGKILLs remaining agent process groups

### Ctrl-C with no live agent is normal shutdown

**Given** Orkie is running in an interactive terminal and no agent session is live  
**When** the operator presses Ctrl-C  
**Then** Orkie starts normal shutdown immediately and does not prompt

### Stop via SIGTERM for service managers

**Given** Orkie is running under systemd or another process supervisor  
**When** the supervisor sends SIGTERM  
**Then** Orkie starts normal shutdown and does not prompt. Non-interactive SIGINT does the same

### Both shutdown modes keep claims and exit 0

**Given** Orkie has live sessions and saved claims  
**When** either shutdown mode finishes  
**Then** it has stopped new intake cycles and new spawns, ended ACP sessions by that mode, deleted session records, attempted worktree removal, and left `claims`, `snapshot`, `spawn_failures`, and agent logs on disk. The process exits 0. A worktree removal failure is logged and does not change the exit code. A second SIGINT or SIGTERM during the graceful 20 second wait SIGKILLs remaining agent process groups

### Refuse a second live process

**Given** an Orkie process is running for a GitHub repository and holds the lock in that project's state directory  
**When** another Orkie start resolves the same `owner/name`  
**Then** the new process exits with an error that names the repository and does not spawn or serve a dashboard. If the lock's recorded pid is not running, the new process takes the lock and starts

### Run from a documented systemd unit

**Given** an operator wants Orkie to start at boot or stay supervised independently of a login shell  
**When** they copy the documented unit below and start it  
**Then** Orkie runs in the foreground as a long-running service, honors SIGTERM as normal shutdown, is non-interactive, and does not prompt for default config, privilege remediation, or a shutdown choice. Missing config or missing required privileges are hard failures. The Orkie repository does not ship a `.service` file

```ini
[Unit]
Description=Orkie
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/project
Environment=GITHUB_TOKEN=replace-with-a-token
ExecStart=orkie /path/to/project
Restart=on-failure

[Install]
WantedBy=default.target
```

## Acceptance criteria

- [ ] The CLI command is `orkie`. It accepts an explicit project directory or defaults to the current working directory. It accepts optional `--port <n>` to override `dashboard_port`.
- [ ] Successful start runs bootstrap, then the continuous intake and orchestration loop.
- [ ] A local web UI dashboard is served on `127.0.0.1:<port>` while Orkie is running. Default port is `8765` (`dashboard_port`); CLI override wins. Startup prints the URL. There is no authentication beyond loopback. If that address is in use, startup fails and names it.
- [ ] The dashboard provides an agent view (working sessions, bound work, logs, spawn failures) and an issue view (intake split by local claim, claim `agent_id`, live session id when working, three-strike warnings on claimed or unclaimed when any spawn-failure row for that issue has `attempt` 3).
- [ ] Agent logs come from `logs/<agent_id>.log` filtered by `session_id=` ([02-local-state.md](02-local-state.md)). Permission grants are visible in that panel. There is no separate permissions page.
- [ ] Dashboard kill uses the ACP delete path, drops an issue claim, and leaves other sessions running.
- [ ] Dashboard interrupt cancels the current ACP turn, logs a pending permission as `permission cancelled`, keeps the session working, and keeps any issue claim. v1 has no follow-up prompt control.
- [ ] Runtime state for the project remains under `~/.local/share/orkie/<owner>--<repo>/` ([02-local-state.md](02-local-state.md)).
- [ ] Interactive means stdin and stdout are both TTYs. There is no override flag. Non-interactive starts never prompt; errors fail hard. Interactive starts may offer default config, prompt on required privilege gaps, and prompt on Ctrl-C when an agent is live.
- [ ] The CLI surfaces bootstrap failures, including a missing `GITHUB_TOKEN` and required tracker capability gaps per [03-connector-interface-and-github.md](03-connector-interface-and-github.md#required-privileges).
- [ ] Connector privilege warnings that do not fail bootstrap are visible on the CLI.
- [ ] A second live process for the same GitHub repository refuses to start. A lock whose holder pid is not running does not block startup.
- [ ] SIGTERM and non-interactive SIGINT are normal shutdown. Interactive Ctrl-C with a live agent prompts for graceful or normal and requires an explicit `g` or `n`. Interactive Ctrl-C with no live agent is normal shutdown.
- [ ] Normal shutdown deletes sessions immediately (5 second process-exit window, then SIGKILL). Graceful shutdown cancels, sends the fixed wrap-up prompt, waits 20 seconds, then uses that delete path. A second SIGINT or SIGTERM during the prompt or the 20 second wait SIGKILLs remaining agent process groups.
- [ ] Both modes keep local claims, delete session records, and exit 0. Worktree removal failure is logged and does not change the exit code.
- [ ] The feature spec documents a systemd unit. The repository does not ship a `.service` file. Under that unit, stop is normal shutdown.
