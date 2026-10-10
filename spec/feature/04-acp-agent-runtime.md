# Feature: ACP Agent Runtime

## Description

Orkie talks to coding agents through the Agent Client Protocol (ACP), protocol version 2. Agents are spawned, prompted, monitored, interrupted, and killed via ACP rather than through proprietary one-off integrations. OpenCode, Grok Build, and Cursor are first-class targets. Any ACP-compatible agent should work in principle.

Orkie runs autonomously. While a session is running, every ACP permission request is granted by Orkie. The operator is not asked. Each grant is written to that agent's log so the dashboard can show it (see [02-local-state.md](02-local-state.md#agent-log-format)). Behavioral limits are left to project prompts and settings.

Each spawn creates a new **session identity**. The session is bound to one config identity from `.orkie/config.yaml` and to exactly one issue or one pull request. The prompt delivered to the session already has the variables from [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md) substituted. The same session id is the worktree directory name, the `__SESSION_ID__` token, and the ACP session. Sessions are not resumed after shutdown or the next start.

## Use cases

Actors are defined in [users.md](users.md).

- **Orchestration**: Spawns an agent with a substituted prompt in a dedicated worktree and drives the session over ACP.
- **Dashboard user**: Views session status, logs, and permission grants, and kills or interrupts a session using ACP-supported controls.
- **Project maintainer**: Chooses an ACP-compatible agent command in config (inline argv or a named preset from [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md)). OpenCode, Grok Build, and Cursor are the documented first-class commands. Others are allowed.

## Permission grants

While a session is running, Orkie answers `session/request_permission` by selecting an option. It never answers `cancelled` as the autonomous policy, including during the initial handshake. Choice order:

1. `allow_always` when that option is present.
2. Otherwise `allow_once` when that option is present.
3. Otherwise the first option whose kind is neither `reject_once` nor `reject_always`.
4. Otherwise the first option, even when every option is a reject kind.

A forced choice of a reject-kind option is still a grant. It is logged and is not a spawn failure.

Each grant is one agent-log line with the timestamp, `session_id=`, `issue=` or `pr=` when known, `optionId`, `kind`, and `title` when present. The line never contains `GITHUB_TOKEN`.

The only `cancelled` permission outcome is when the operator interrupts the session, or when graceful shutdown has sent `session/cancel` and a permission request is still pending. That answer is logged as `permission cancelled`, which is distinct from a grant. Normal shutdown does not wait on a permission prompt; it deletes the session.

## Session end

Dashboard kill and normal shutdown end a live session the same way:

1. If initialize reported `capabilities.session.delete`, send `session/delete`.
2. If the agent process has not exited within 5 seconds, SIGKILL its process group.
3. If initialize did not report `capabilities.session.delete`, SIGKILL the process group immediately and do not send `session/delete`.

The 5 second window is process exit. An empty `session/delete` result does not by itself mean the process has exited. Session transcripts are not retained.

Graceful shutdown, before that delete path, sends `session/cancel` and then one wrap-up prompt to each live session. The wrap-up prompt is this fixed string, owned here, and is not a config knob or a dashboard control:

> Wrap up your current work now. Commit or stash local changes, and open a pull request if the work is ready to share. Do not start new work.

Orkie waits 20 seconds for every session together. An idle status during that wait does not end it early. A protocol error on a session's wrap-up prompt moves that session straight to the delete path. When the 20 seconds end, every remaining session is deleted as in normal shutdown. Pending permission requests during the cancel are answered `cancelled` and logged as `permission cancelled`.

## User stories

### Spawn an agent over ACP

**Given** orchestration has decided to run a config agent against one issue, or the babysitter against one PR  
**When** Orkie starts that work  
**Then** it uses the session id orchestration minted for that spawn, establishes an ACP session with the configured command in the session worktree, and delivers the substituted prompt. Prompt acceptance is the protocol success that carries a message id. Orkie does not wait for the agent to go idle before treating the spawn as started

### Prefer OpenCode, Grok Build, and Cursor

**Given** project config names OpenCode, Grok Build, or Cursor as the agent command (inline argv or the matching built-in `command_ref`)  
**When** Orkie spawns the agent  
**Then** the ACP runtime uses the documented command for that agent and treats it as a supported first-class target

Documented commands:

- OpenCode: `opencode acp` (built-in preset `opencode`)
- Grok Build: `grok agent --always-approve stdio` (built-in preset `grok`)
- Cursor: `agent acp` (built-in preset `cursor`)

Cursor may advertise an ACP auth method (for example `cursor_login`). The operator pre-authenticates outside Orkie (`agent login`, `CURSOR_API_KEY`, or equivalent). Orkie then calls `authenticate` during spawn as in [Fail clearly when the agent cannot start](#fail-clearly-when-the-agent-cannot-start).

### Support any ACP-compatible agent in principle

**Given** project config points at another ACP-compatible command  
**When** Orkie spawns and drives that agent  
**Then** the same ACP client path is used. Orkie does not require a proprietary non-ACP API for core agent control

### Grant permissions without asking the operator

**Given** an agent session is running, including during startup of that session  
**When** the agent asks for a permission through ACP  
**Then** Orkie selects an option by the [Permission grants](#permission-grants) order, logs the grant on that agent's log, and does not prompt the operator. A reject-only option list still gets a selected grant and is not a spawn failure

### Kill via ACP delete

**Given** an active ACP session  
**When** an operator kills that session from the dashboard (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md))  
**Then** Orkie ends it by the [Session end](#session-end) delete path. The session record is removed. An issue claim held by that session is dropped by orchestration (see [05-agent-orchestration.md](05-agent-orchestration.md))

### Interrupt leaves the session working

**Given** an active ACP session  
**When** an operator interrupts that session from the dashboard  
**Then** Orkie cancels the current ACP turn and answers any pending permission request with `cancelled`, logged as `permission cancelled`. The session stays working, and an issue claim held by that session stays in place. v1 does not send a follow-up prompt from the dashboard

### The agent process receives the GitHub token

**Given** Orkie spawns an ACP agent  
**When** the child process is started  
**Then** its environment includes `GITHUB_TOKEN`. Session logs and spawn errors stored by Orkie do not include that value

### Surface status and logs

**Given** one or more ACP sessions are active or recently active  
**When** the dashboard or orchestration needs status or log output  
**Then** Orkie mirrors agent message text and the child stderr into `logs/<agent_id>.log` with a clear session id marker (see [02-local-state.md](02-local-state.md#agent-log-format)). Display includes the config id and the session id. Permission grants appear in that same log

### Normal shutdown deletes remaining agent processes

**Given** one or more ACP sessions are still active  
**When** the process enters normal shutdown (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md))  
**Then** each session is ended by the [Session end](#session-end) delete path so those processes do not outlive Orkie. Claims are left in place by orchestration

### Graceful shutdown asks for wrap-up, then deletes

**Given** one or more ACP sessions are still active  
**When** the process enters graceful shutdown  
**Then** each session receives cancel and the fixed wrap-up prompt, Orkie waits 20 seconds, and then each remaining session is deleted as in normal shutdown. Session data is not retained

### Session exit is observed

**Given** an ACP session ends on its own  
**When** the runtime reports that exit  
**Then** the session is not working. If it held an issue claim and shutdown has not started, orchestration drops that claim. Whether and when the agent exits is an agent decision (guided by the project prompt), not an orchestrator decision. An exit after shutdown has started (`shutdown_event` or the interactive shutdown prompt) does not drop the claim

### Authenticate when the agent advertises auth methods

**Given** ACP `initialize` returns a non-empty `authMethods` list  
**When** Orkie continues the spawn handshake  
**Then** it calls `authenticate` with the first advertised method's id (using pre-existing operator credentials in the environment or CLI login state). An empty `authMethods` list skips `authenticate`. A failed `authenticate` call fails the spawn

### Fail clearly when the agent cannot start

**Given** the configured ACP command is missing, fails to start, rejects ACP protocol version 2, returns an error from `authenticate`, or returns an error for the initial prompt  
**When** Orkie attempts to spawn the session  
**Then** the failure is stored as a spawn-failure record with the config id, the issue or PR number, attempt count, and a redacted error. No session is working. Claim handling (keep through three attempts, then drop the local claim) is owned by orchestration (see [05-agent-orchestration.md](05-agent-orchestration.md)). The dashboard shows the failure. Advertising auth methods alone is not a spawn failure when `authenticate` succeeds

## Acceptance criteria

- [ ] Agent spawn, prompt delivery, status, and kill go through ACP protocol version 2.
- [ ] OpenCode (`opencode acp`), Grok Build (`grok agent --always-approve stdio`), and Cursor (`agent acp`) are documented first-class commands, including the matching built-in presets in [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md).
- [ ] Resolved argv from config (`command` or `command_ref`) selects the ACP agent. Orkie does not hard-code only those three implementations.
- [ ] When `initialize` returns a non-empty `authMethods` list, Orkie calls `authenticate` with the first method id before `session/new`. Empty `authMethods` skips authenticate. Authenticate failure fails the spawn.
- [ ] Each spawn uses one session id minted for that attempt. The session is tied to one config id and one issue or one PR. That id is the worktree name and the prompt's session token. Sessions are not resumed.
- [ ] The delivered prompt is the config template after variable substitution. Acceptance of that prompt is the ACP success that carries a message id. Spawn does not wait for idle. A protocol error on the initial prompt fails the spawn.
- [ ] While a session is running, Orkie grants every permission request by the order in [Permission grants](#permission-grants), including a reject-only option list, and writes each grant to the agent log. The operator is not asked. `cancelled` is reserved for interrupt and for graceful-shutdown cancel, and those answers are logged as `permission cancelled`.
- [ ] Dashboard kill uses the delete path in [Session end](#session-end): `session/delete` when the agent advertised it, then SIGKILL if the process has not exited within 5 seconds. Without that capability, SIGKILL is immediate. Orchestration drops an issue claim held by that session.
- [ ] Dashboard interrupt cancels the current ACP turn, answers pending permissions as `cancelled`, leaves the session working, and leaves its issue claim in place. The dashboard has no follow-up prompt control in v1.
- [ ] The ACP child environment includes `GITHUB_TOKEN`. Stored logs and spawn errors omit that value.
- [ ] Agent message text, child stderr, and permission lines needed by the dashboard are mirrored into `logs/<agent_id>.log`, with config id and session id available to the dashboard.
- [ ] Spawn failures are stored for the dashboard, leave no working session, and name the config agent, work item, and attempt. Claim keep-or-drop after failures is owned by orchestration.
- [ ] A session that exits is not working. Whether the agent stops is an agent decision. Claim drop for that exit, except after shutdown has started, is owned by orchestration.
- [ ] Orchestration owns worktree allocation (see [05-agent-orchestration.md](05-agent-orchestration.md#worktrees)). The ACP runtime receives the worktree path as the agent's workspace.
- [ ] Normal shutdown deletes remaining ACP agent processes by the 5 second delete path. Graceful shutdown sends cancel and the fixed wrap-up prompt, waits 20 seconds, then uses that same delete path. Neither mode retains session data. Agent processes do not remain running after Orkie exits.
