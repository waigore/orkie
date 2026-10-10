# Feature: PR Babysitter

## Description

Orkie optionally runs one PR babysitter. It is turned on or off by `babysitter.enabled` in `.orkie/config.yaml`. When it is off, Orkie does not manage pull requests. When it is on, the babysitter is one config identity and at most one ACP session at a time (the babysitter limit). That session is bound to one selectable blocked pull request.

**The orchestrator is hands-off on babysitter completion.** The babysitter agent may stop whenever it determines the bound PR work is done or no longer needs attention. Orkie does not stop a working babysitter because the bound PR changed state, including becoming merge-ready, closing, or merging. After the babysitter session is not working, if the spawn trigger still holds (at least one selectable blocked PR exists) and no babysitter session is active, orchestration may spawn a new babysitter session for the PR selected on that cycle. A PR that has failed to spawn three times in a row is skipped until a poll on which it is not selectable. The next lowest selectable PR is selected instead.

The babysitter does not take issue claims, does not use the claim label, and does not count against issue session caps. It uses ACP, full permissions, a config prompt, and its own git worktree. Connector data tells Orkie which PR to assign. The agent itself pushes and comments through its own tools. Orkie does not merge pull requests.

Worktrees follow the minimal policy in [05-agent-orchestration.md](05-agent-orchestration.md#worktrees).

Terms such as merge-ready and selectable blocked are defined in [vocabulary.md](vocabulary.md). Orkie selects the selectable blocked PR with the lowest PR number. The session prompt receives only that PR's variables from [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md). `__PR_MERGE_STATE__` is the connector mergeable state string as returned by the connector.

**Babysitter ↔ PR mapping is 1:0–1**, same as issue agents: one session, one PR; at most one babysitter session working at a time.

## Use cases

Actors are defined in [users.md](users.md).

- **Project maintainer**: Enables the babysitter and supplies a prompt for one assigned PR at a time, or leaves it off so Orkie only handles intake issues.
- **Continuous Orkie process** / **Orchestration**: When enabled, keeps at most one babysitter session on a selectable blocked non-draft PR.

## User stories

### Enable babysitter from project config

**Given** `babysitter.enabled` is true and the babysitter config identity is valid  
**When** Orkie is in the continuous loop, at least one selectable blocked PR exists, and no babysitter session is working  
**Then** orchestration may spawn one babysitter session for the selected PR

### Disable means no PR management

**Given** the babysitter is off  
**When** pull requests exist in the repository  
**Then** Orkie does not spawn the babysitter and does not take PR lifecycle actions

### One session, one PR

**Given** the babysitter is enabled  
**When** a babysitter session is spawned  
**Then** it is bound to exactly one selected PR. Orkie does not assign a second PR to that session. The project prompt should tell the agent to work only on `__PRNO__`

### Agent decides when to stop; orchestrator may spawn again

**Given** a babysitter session has exited or been killed  
**When** a later poll still sees a selectable blocked PR and no babysitter session is working  
**Then** orchestration may spawn a new session, with a new session id, for the PR selected on that cycle. The previous session's context is not reused. Orkie does not stop a still-working babysitter because that PR's state changed

### Idle when nothing is selectable and blocked

**Given** the babysitter is enabled  
**When** every open PR is merge-ready, a draft, or not selectable yet  
**Then** Orkie does not spawn a babysitter session just to wait

### Drafts are excluded

**Given** an open draft pull request  
**When** orchestration selects a babysitter target  
**Then** that draft is not selectable, regardless of mergeable state

### Poll on the intake interval

**Given** the babysitter is enabled  
**When** the intake interval fires  
**Then** orchestration refreshes open PR state through the connector on that same interval

### Use connector PR data

**Given** the babysitter needs the next PR  
**When** orchestration refreshes PR context  
**Then** number, title, URL, head branch, base branch, draft flag, and mergeable state come through the connector. Orkie does not merge, and it does not add a connector write API for PR comments or pushes. Those happen, if at all, through the agent session

### Same agent runtime model as other agents

**Given** the babysitter is spawned  
**When** it runs  
**Then** it uses ACP, receives its config identity and a new session id, gets the substituted prompt and full permissions, and uses its own git worktree

### Operator can kill the babysitter

**Given** a babysitter session is working  
**When** an operator kills it from the dashboard  
**Then** the session stops via ACP and is not working. No issue claim is involved. A later poll may spawn a new session if a selectable blocked PR remains

### Interrupt leaves the babysitter working

**Given** a babysitter session is working  
**When** an operator interrupts it from the dashboard  
**Then** Orkie cancels the current ACP turn. The session stays working. No issue claim is involved

### Shutdown stops the babysitter

**Given** a babysitter session is working  
**When** Orkie shuts down via SIGINT or SIGTERM  
**Then** that session is terminated with other ACP sessions and is not left running

## Acceptance criteria

- [ ] `babysitter.enabled` is the on/off control. When off, Orkie performs no PR lifecycle management.
- [ ] When on, there is one babysitter config identity and at most one working session (the babysitter limit).
- [ ] A session is bound to one selectable blocked PR: open, not draft, mergeable state known, and not `clean`. Ties go to the lowest PR number. Drafts are never selected. A PR with three consecutive spawn failures is skipped until a poll on which it is not selectable; the next lowest selectable PR is used.
- [ ] The prompt receives only that PR's variables. A new PR assignment is a new session.
- [ ] Merge-ready means open, not draft, and mergeable state `clean`. Orkie does not merge PRs.
- [ ] The babysitter does not use the issue claim label and does not consume issue session caps.
- [ ] The orchestrator does not stop the babysitter for PR state changes, including close or merge. Stopping is an agent (or kill/shutdown) decision. After the session is not working, Orkie may spawn again when a selectable blocked PR exists.
- [ ] PR reads come from the connector ([03-connector-interface-and-github.md](03-connector-interface-and-github.md)).
- [ ] The babysitter uses the ACP runtime, config identity, session identity, and a dedicated worktree ([04-acp-agent-runtime.md](04-acp-agent-runtime.md), [05-agent-orchestration.md](05-agent-orchestration.md#worktrees)).
- [ ] Dashboard kill, interrupt, and process shutdown behave as in [08-cli-and-dashboard.md](08-cli-and-dashboard.md).
