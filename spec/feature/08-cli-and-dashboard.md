# Feature: CLI and Dashboard

## Description

Orkie is a long-running process started from the command line. An operator either points Orkie at a project directory (a Git repo with `.orkie/config.yaml`) or starts it from inside that directory so bootstrap can run. After start, Orkie runs continuously (intake, orchestration, and the optional babysitter) and serves a basic local web UI dashboard on loopback. The default address is `http://127.0.0.1:8765`. The port defaults to `8765` from config (`dashboard_port`) and may be overridden by a CLI flag. The process prints the bound URL at startup.

The dashboard has two simple views:
- **Agent view**: spawned agents (sessions) and which issue or PR each is working on, plus status and logs.
- **Issue view**: intake issues that are claimed (and which agent owns them) versus still unclaimed.

It can interrupt or kill a session. Killing an issue session releases its claim. Interrupt cancels the current turn and leaves the claim in place. v1 has no follow-up prompt box. Spawn failures (including three-strike claim releases) are visible in both views as appropriate.

The process can be stopped from a terminal with Ctrl-C (SIGINT), or by systemd with SIGTERM. Shutdown is graceful: stop new work, terminate agent subprocesses, release issue claim labels, flush local state, and stop the dashboard. If agents are still running after 30 seconds, Orkie kills their process groups. A second SIGINT or SIGTERM during shutdown skips that wait. Exit status is 0 when every held claim label was released, and 1 when a release failed. Project-related runtime state remains under the per-user path described in [02-local-state.md](02-local-state.md). A second live process for the same GitHub repository refuses to start.

**Non-interactive principle:** When Orkie is started without a TTY (systemd, pipes, CI), it never prompts. Any condition that would need operator consent or an interactive choice is a hard failure. Interactive mode may prompt (default config offer; required connector privilege gaps). See [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md) and [03-connector-interface-and-github.md](03-connector-interface-and-github.md#required-privileges).

## Use cases

Actors are defined in [users.md](users.md).

- **Operator**: Starts Orkie from a shell against a project and leaves it running; stops it with Ctrl-C when done; reads bootstrap errors and connector warnings from CLI output before relying on the dashboard.
- **Dashboard user**: Monitors agents and issues, spawn failures, and interrupts or kills a session without stopping the whole Orkie process.
- **Host administrator**: Runs Orkie as a systemd service using the same long-running process and graceful shutdown path, always non-interactive.

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

### Agent view shows spawned work

**Given** the dashboard agent view is open  
**When** the page loads or refreshes  
**Then** it lists each working session: config id, config name, session id, bound issue or PR number, working status, and accessible logs from `logs/<agent_id>.log` with session ids marked in the log lines. It also surfaces spawn-failure records for that agent (attempt number, redacted error, and whether a three-strike release happened)

### Issue view shows claims and unclaimed intake

**Given** the dashboard issue view is open  
**When** the page loads or refreshes  
**Then** it shows the GitHub repository name and the branch of the checkout where Orkie was started (or `detached`). It lists intake issues that carry the claim label and, when a session is working on one, that session's config agent id and session id. It lists intake issues without the claim label separately. Spawn failures that removed a claim label are flagged as warnings on the affected issue when still relevant

### Spawn failure stays visible across retries

**Given** a spawn has failed and fewer than three consecutive failures have occurred for that issue  
**When** the operator opens or refreshes the dashboard  
**Then** that failure is listed with the attempt number. After a successful spawn the failure clears. After the third failure the claim release is flagged and warned so the operator can see that Orkie gave up on that claim

### Kill a session from the dashboard

**Given** one or more sessions are working  
**When** the operator kills a specific session in the dashboard  
**Then** Orkie terminates that session via ACP (see [04-acp-agent-runtime.md](04-acp-agent-runtime.md)). An issue session's claim is released. The dashboard shows that session as not working. Other sessions keep running

### Interrupt a session from the dashboard

**Given** a session is working  
**When** the operator interrupts that session  
**Then** Orkie cancels the current ACP turn. The session stays working, an issue claim stays if present, and the dashboard does not offer a way to send a follow-up prompt

### Missing config is offered on the interactive CLI only

**Given** `.orkie/config.yaml` is missing in the target project and the process is interactive  
**When** the operator starts Orkie  
**Then** the CLI offers to create the default config (accept continues bootstrap; reject exits without starting the loop) as specified in [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md)

### Non-interactive start never prompts

**Given** Orkie is started non-interactive (no TTY), including under systemd  
**When** config is missing, a required connector privilege is missing, or any other bootstrap error needs operator input  
**Then** Orkie fails hard with a clear error and does not prompt

### Bootstrap failures stay on the CLI

**Given** YAML is invalid, the operator rejected default config creation, `GITHUB_TOKEN` is missing, or a required tracker capability is missing  
**When** bootstrap cannot complete  
**Then** the CLI reports the failure clearly and does not present a healthy dashboard for a project that never bootstrapped. Required privilege handling follows [03-connector-interface-and-github.md](03-connector-interface-and-github.md#required-privileges)

### Stop safely from the terminal with Ctrl-C

**Given** Orkie is running in a foreground terminal  
**When** the operator presses Ctrl-C (SIGINT)  
**Then** Orkie begins graceful shutdown. It waits up to 30 seconds for ACP termination and claim-label release, then kills any remaining agent process groups. A second SIGINT or SIGTERM during that wait kills those process groups immediately. The process does not leave agent processes behind

### Stop via SIGTERM for service managers

**Given** Orkie is running under systemd or another process supervisor  
**When** the supervisor sends SIGTERM  
**Then** Orkie uses the same graceful shutdown path as Ctrl-C

### Graceful shutdown releases claims and persists state

**Given** Orkie has live sessions and claim labels applied  
**When** graceful shutdown runs  
**Then** it stops new intake cycles and new spawns, terminates ACP sessions, removes the claim label for each issue session it stops, and flushes local state. A label removal that fails leaves the label on the issue so the next start can reconcile it from the tracker (see [02-local-state.md](02-local-state.md) and [05-agent-orchestration.md](05-agent-orchestration.md)). The process exits 0 when every such label was removed, and exits 1 when any removal failed

### Refuse a second live process

**Given** an Orkie process is running for a GitHub repository and holds the lock in that project's state directory  
**When** another Orkie start resolves the same `owner/name`  
**Then** the new process exits with an error that names the repository and does not spawn or serve a dashboard. If the lock's recorded pid is not running, the new process takes the lock and starts

### Run from a documented systemd unit

**Given** an operator wants Orkie to start at boot or stay supervised independently of a login shell  
**When** they copy the documented unit below and start it  
**Then** Orkie runs in the foreground as a long-running service, honors SIGTERM for stop and restart, is non-interactive, and does not prompt for default config or privilege remediation. Missing config or missing required privileges are hard failures. The Orkie repository does not ship a `.service` file

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
- [ ] The dashboard provides an agent view (working sessions, bound work, logs, spawn failures) and an issue view (claimed vs unclaimed intake, owners, three-strike warnings).
- [ ] Agent logs come from `logs/<agent_id>.log` with session ids marked in-line ([02-local-state.md](02-local-state.md)).
- [ ] Dashboard kill uses ACP terminate, releases an issue claim, and leaves other sessions running.
- [ ] Dashboard interrupt cancels the current ACP turn, keeps the session working, and keeps any issue claim. v1 has no follow-up prompt control.
- [ ] Runtime state for the project remains under `~/.local/share/orkie/<owner>--<repo>/` ([02-local-state.md](02-local-state.md)).
- [ ] Non-interactive starts never prompt; errors fail hard. Interactive starts may offer default config and prompt on required privilege gaps.
- [ ] The CLI surfaces bootstrap failures, including a missing `GITHUB_TOKEN` and required tracker capability gaps per [03-connector-interface-and-github.md](03-connector-interface-and-github.md#required-privileges).
- [ ] Connector privilege warnings that do not fail bootstrap are visible on the CLI.
- [ ] A second live process for the same GitHub repository refuses to start. A lock whose holder pid is not running does not block startup.
- [ ] SIGINT and SIGTERM share one graceful shutdown: stop new work, stop the dashboard and intake, terminate ACP subprocesses, release claim labels, and flush local state.
- [ ] Shutdown waits at most 30 seconds, then kills remaining agent process groups. A second SIGINT or SIGTERM skips the wait.
- [ ] Shutdown exits 0 when every claim label for a stopped issue session was removed, and exits 1 when a removal failed. A failed removal leaves the label on the issue for reconciliation on the next start.
- [ ] The feature spec documents a systemd unit. The repository does not ship a `.service` file.
