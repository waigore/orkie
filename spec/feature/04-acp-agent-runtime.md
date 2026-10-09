# Feature: ACP Agent Runtime

## Description

Orkie talks to coding agents through the Agent Client Protocol (ACP). Agents are spawned, prompted, monitored, interrupted, and killed via ACP rather than through proprietary one-off integrations. OpenCode and Grok Build are first-class targets. Any ACP-compatible agent should work in principle. Orkie grants agents full permissions for unimpeded work. Behavioral limits are left to project prompts and settings. Session status and logs exposed by ACP feed the local web dashboard and human interrupt paths.

Each spawn creates a new **session identity**. The session is bound to one config identity from `.orkie/config.yaml` and to exactly one issue or one pull request. The prompt delivered to the session already has the variables from [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md) substituted.

## Users and use cases

- **Orchestrator**: Spawns an agent with a substituted prompt in a dedicated worktree and drives the session over ACP.
- **Dashboard operator**: Views session status and logs, and kills a session using ACP-supported controls.
- **Project maintainer**: Chooses an ACP-compatible agent command in config. OpenCode or Grok Build are the documented first-class commands. Others are allowed.

## User stories

### Spawn an agent over ACP

**Given** orchestration has decided to run a config agent against one issue, or the babysitter against one PR  
**When** Orkie starts that work  
**Then** Orkie generates a new session id, establishes an ACP session with the configured command, and delivers the substituted prompt

### Prefer OpenCode and Grok Build

**Given** project config names OpenCode or Grok Build as the agent command  
**When** Orkie spawns the agent  
**Then** the ACP runtime uses the documented command for that agent and treats it as a supported first-class target

Documented commands:

- OpenCode: `opencode acp`
- Grok Build: `grok agent --always-approve stdio`

### Support any ACP-compatible agent in principle

**Given** project config points at another ACP-compatible command  
**When** Orkie spawns and drives that agent  
**Then** the same ACP client path is used. Orkie does not require a proprietary non-ACP API for core agent control

### Full permissions for unimpeded work

**Given** an agent session is started for project work  
**When** permissions are negotiated or granted via ACP  
**Then** Orkie grants full permissions so the agent is not blocked by an Orkie-imposed capability sandbox. Project prompts define behavioral expectations

### Kill via ACP

**Given** an active ACP session  
**When** an operator kills that session from the dashboard (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md))  
**Then** Orkie terminates it through ACP, the session record is not working, and an issue claim held by that session is released (see [05-agent-orchestration.md](05-agent-orchestration.md))

### Interrupt leaves the session working

**Given** an active ACP session  
**When** an operator interrupts that session from the dashboard  
**Then** Orkie cancels the current ACP turn. The session stays working, and an issue claim held by that session stays in place. v1 does not send a follow-up prompt from the dashboard

### The agent process receives the GitHub token

**Given** Orkie spawns an ACP agent  
**When** the child process is started  
**Then** its environment includes `GITHUB_TOKEN`. Session logs and spawn errors stored by Orkie do not include that value

### Surface status and logs

**Given** one or more ACP sessions are active or recently active  
**When** the dashboard or orchestration needs status or log output  
**Then** Orkie obtains status and logs through ACP where available and persists or relays them for local display (see [02-local-state.md](02-local-state.md)). Display includes the config id and the session id

### Shutdown terminates remaining agent subprocesses

**Given** one or more ACP sessions are still active  
**When** the Orkie process receives SIGINT or SIGTERM and enters graceful shutdown (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md))  
**Then** Orkie cancels or terminates those sessions via ACP, and their subprocesses, so they do not outlive the Orkie process

### Session exit is observed

**Given** an ACP session ends on its own  
**When** the runtime reports that exit  
**Then** the session is not working. If it held an issue claim, orchestration releases that claim. The project prompt decides whether the agent exits or keeps running

### Fail clearly when the agent cannot start

**Given** the configured ACP command is missing or fails to start  
**When** Orkie attempts to spawn the session  
**Then** the failure is stored as a spawn-failure record with the config id, the issue or PR number, and a redacted error. No claim label is left behind, no session is working, and the dashboard shows the failure and that the same spawn is not retried until the next poll (see [05-agent-orchestration.md](05-agent-orchestration.md) and [08-cli-and-dashboard.md](08-cli-and-dashboard.md))

## Acceptance criteria

- [ ] Agent spawn, prompt delivery, status, and kill go through ACP.
- [ ] OpenCode (`opencode acp`) and Grok Build (`grok agent --always-approve stdio`) are documented first-class commands.
- [ ] `command` in config selects the ACP agent. Orkie does not hard-code only those two implementations.
- [ ] Each spawn generates a session id. The session is tied to one config id and one issue or one PR.
- [ ] The delivered prompt is the config template after variable substitution.
- [ ] Orkie grants full agent permissions for project work and does not add a restrictive Orkie-side permission sandbox.
- [ ] Dashboard kill maps to ACP terminate and releases an issue claim held by that session.
- [ ] Dashboard interrupt cancels the current ACP turn, leaves the session working, and leaves its issue claim in place. The dashboard has no follow-up prompt control in v1.
- [ ] The ACP child environment includes `GITHUB_TOKEN`. Stored logs and spawn errors omit that value.
- [ ] Agent status and logs needed by the dashboard are obtainable via ACP and/or mirrored into local state, with config id and session id.
- [ ] Spawn failures are stored for the dashboard, do not leave a claim label or a working session, and name the config agent and work item.
- [ ] A session that exits is not working. Claim release for that exit is owned by orchestration.
- [ ] Orchestration owns worktree allocation (see [05-agent-orchestration.md](05-agent-orchestration.md)). The ACP runtime receives the worktree path as the agent's workspace. Where worktrees live, which base they use, and when they are removed are design details and are not part of this feature spec.
- [ ] Process-wide graceful shutdown terminates remaining ACP agent subprocesses. They do not remain running after Orkie exits.
