# Feature: CLI and Dashboard

## Description

Orkie is a long-running process started from the command line. An operator either points Orkie at a project directory (a Git repo with `.orkie/config.yaml`) or starts it from inside that directory so bootstrap can run. After start, Orkie runs continuously (intake, orchestration, and the optional babysitter) and serves a basic local web UI dashboard at `http://127.0.0.1:8765`. The process prints that URL at startup. The dashboard shows the GitHub repository name, the branch of the checkout where Orkie was started, live sessions, and spawn failures waiting for the next poll. It can interrupt or kill a session. Killing an issue session releases its claim. Interrupt cancels the current turn and leaves the claim in place. v1 has no follow-up prompt box. The process can be stopped from a terminal with Ctrl-C (SIGINT), or by systemd with SIGTERM. Shutdown is graceful: stop new work, terminate agent subprocesses, release issue claim labels, flush local state, and stop the dashboard. If agents are still running after 30 seconds, Orkie kills their process groups. A second SIGINT or SIGTERM during shutdown skips that wait. Exit status is 0 when every held claim label was released, and 1 when a release failed. Project-related runtime state remains under the per-user path described in [02-local-state.md](02-local-state.md). A second live process for the same GitHub repository refuses to start.

## Users and use cases

- **Operator**: Starts Orkie from a shell against a project and leaves it running. Stops it with Ctrl-C when done.
- **Dashboard user**: Monitors sessions and spawn failures, and interrupts or kills a session without stopping the whole Orkie process.
- **Developer setting up a project**: Reads bootstrap errors and connector warnings from CLI output before relying on the dashboard.
- **Host administrator**: Runs Orkie as a systemd service using the same long-running process and graceful shutdown path.

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

**Given** bootstrap succeeded and port 8765 is free on the loopback interface  
**When** the process enters the continuous loop  
**Then** it binds `127.0.0.1:8765` only, prints `http://127.0.0.1:8765` to the CLI, and serves the dashboard there with no authentication beyond loopback

### Fail when the dashboard port is taken

**Given** `127.0.0.1:8765` is already in use  
**When** Orkie tries to bind the dashboard  
**Then** startup fails with a message that names that address, and the orchestration loop does not keep running without a dashboard

### Show project, sessions, and spawn failures

**Given** the dashboard is open for a running project  
**When** the page loads or refreshes  
**Then** it shows the GitHub repository name and the branch of the checkout where Orkie was started (or `detached` when HEAD is detached). It lists each live session's config id, config name, session id, bound issue or PR number, working status, and accessible logs. It also lists each spawn-failure record: config id, config name, issue or PR number, redacted error, and that retry waits until the next poll. A spawn failure is not shown as a working session

### Spawn failure stays visible across the wait

**Given** a spawn has failed and the next poll has not run  
**When** the operator opens or refreshes the dashboard  
**Then** that failure is still listed. When the next poll retries it, the row is replaced by a live session on success, updated with the new error on another failure, or removed if the work item is no longer eligible

### Kill a session from the dashboard

**Given** one or more sessions are working  
**When** the operator kills a specific session in the dashboard  
**Then** Orkie terminates that session via ACP (see [04-acp-agent-runtime.md](04-acp-agent-runtime.md)). An issue session's claim is released. The dashboard shows that session as not working. Other sessions keep running

### Interrupt a session from the dashboard

**Given** a session is working  
**When** the operator interrupts that session  
**Then** Orkie cancels the current ACP turn. The session stays working, its issue claim stays, and the dashboard does not offer a way to send a follow-up prompt

### Missing config is offered on the CLI

**Given** `.orkie/config.yaml` is missing in the target project  
**When** the operator starts Orkie  
**Then** the CLI offers to create the default config (accept continues bootstrap; reject exits without starting the loop) as specified in [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md)

### Bootstrap failures stay on the CLI

**Given** YAML is invalid, the operator rejected default config creation, `GITHUB_TOKEN` is missing, or the claim label cannot be created  
**When** bootstrap cannot complete  
**Then** the CLI reports the failure clearly and does not present a healthy dashboard for a project that never bootstrapped

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
**Then** it stops new intake cycles and new spawns, terminates ACP sessions, removes claim labels it still holds, and flushes local state. A label removal that fails stays in the persisted claim record so the next start can fulfill it (see [02-local-state.md](02-local-state.md) and [05-agent-orchestration.md](05-agent-orchestration.md)). The process exits 0 when every held claim label was released, and exits 1 when any release failed

### Refuse a second live process

**Given** an Orkie process is running for a GitHub repository and holds the lock in that project's state directory  
**When** another Orkie start resolves the same `owner/name`  
**Then** the new process exits with an error that names the repository and does not spawn or serve a dashboard. If the lock's recorded pid is not running, the new process takes the lock and starts

### Run from a documented systemd unit

**Given** an operator wants Orkie to start at boot or stay supervised independently of a login shell  
**When** they copy the documented unit below and start it  
**Then** Orkie runs in the foreground as a long-running service, honors SIGTERM for stop and restart, does not require a TTY after bootstrap, and does not prompt for default config in non-interactive service mode. Missing config is a failure in that mode. The Orkie repository does not ship a `.service` file

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

- [ ] The CLI command is `orkie`. It accepts an explicit project directory or defaults to the current working directory.
- [ ] Successful start runs bootstrap, then the continuous intake and orchestration loop.
- [ ] A local web UI dashboard is served on `127.0.0.1:8765` while Orkie is running. Startup prints `http://127.0.0.1:8765`. There is no authentication beyond loopback. If that address is in use, startup fails and names it.
- [ ] The dashboard displays the GitHub repository name, the start checkout's branch (or `detached`), each live session's config id, session id, bound work item, status, and logs, and each spawn failure waiting for the next poll.
- [ ] A spawn-failure row shows config id, config name, issue or PR number, a redacted error, and that retry waits until the next poll. It is not presented as a working session. The row updates or clears when that poll retries or the work item is no longer eligible.
- [ ] Dashboard kill uses ACP terminate, releases an issue claim, and leaves other sessions running.
- [ ] Dashboard interrupt cancels the current ACP turn, keeps the session working, and keeps the claim. v1 has no follow-up prompt control.
- [ ] Runtime state for the project remains under `~/.local/share/orkie/<owner>--<repo>/` ([02-local-state.md](02-local-state.md)).
- [ ] The CLI surfaces the missing-config offer and bootstrap failures, including a missing `GITHUB_TOKEN`, a missing required tracker capability, and a claim label that cannot be created.
- [ ] Connector privilege warnings that do not fail bootstrap are visible on the CLI.
- [ ] A second live process for the same GitHub repository refuses to start. A lock whose holder pid is not running does not block startup.
- [ ] SIGINT and SIGTERM share one graceful shutdown: stop new work, stop the dashboard and intake, terminate ACP subprocesses, release claim labels, and flush local state.
- [ ] Shutdown waits at most 30 seconds, then kills remaining agent process groups. A second SIGINT or SIGTERM skips the wait.
- [ ] Shutdown exits 0 when every held claim label was released, and exits 1 when a release failed. A failed release remains recorded for fulfillment on the next start.
- [ ] The feature spec documents a systemd unit. The repository does not ship a `.service` file. Interactive default-config prompting is for an interactive CLI only.
