# Feature: PR Babysitter

## Description

Orkie optionally runs one PR babysitter. It is turned on or off by `babysitter.enabled` in `.orkie/config.yaml`. When it is off, Orkie does not manage pull requests. When it is on, the babysitter is one config identity and at most one ACP session at a time. That session is bound to one blocked pull request, then exits or is killed before another PR is assigned, so PR context does not accumulate in one session.

The babysitter does not take issue claims, does not use the claim label, and does not count against issue session caps. It uses ACP, full permissions, a config prompt, and its own git worktree. Connector data tells Orkie which PR to assign. The agent itself pushes and comments through its own tools. Orkie does not merge pull requests.

How the worktree is created, which base it uses, and when it is removed are design details, as for other agents.

## Users and use cases

- **Project maintainer**: Enables the babysitter and supplies a prompt that works on the single assigned PR.
- **Team with merge-ready discipline**: Lets the babysitter take blocked PRs one at a time.
- **Team that manages PRs manually**: Leaves the babysitter off so Orkie only handles intake issues.

## Definitions

- **Merge-ready**: the pull request is open and its connector mergeable state is `clean`.
- **Blocked**: the pull request is open, the mergeable state is known, and the state is not `clean`. Drafts, conflicts, failing or pending required checks, missing reviews, and branches that are behind are blocked when GitHub reports them that way.
- **Not selectable yet**: the mergeable state is `unknown`. Orkie waits for a later poll rather than assigning that PR.

Orkie selects the selectable blocked PR with the lowest PR number. The session prompt receives only that PR's variables from [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md).

## User stories

### Enable babysitter from project config

**Given** `babysitter.enabled` is true and the babysitter config identity is valid  
**When** Orkie is in the continuous loop and at least one selectable blocked PR exists  
**Then** orchestration may spawn one babysitter session for the selected PR

### Disable means no PR management

**Given** the babysitter is off  
**When** pull requests exist in the repository  
**Then** Orkie does not spawn the babysitter and does not take PR lifecycle actions

### One session, one PR

**Given** the babysitter is enabled  
**When** a babysitter session is spawned  
**Then** it is bound to exactly one selected PR. Orkie does not assign a second PR to that session. The project prompt should tell the agent to work only on `__PRNO__`. If the prompt sends the agent onto other PRs, tracking of those extra PRs is undefined

### Next PR is a new session

**Given** a babysitter session has exited or been killed  
**When** a later poll still sees a selectable blocked PR and no babysitter session is working  
**Then** orchestration may spawn a new session, with a new session id, for the PR selected on that cycle. The previous session's context is not reused

### Idle when nothing is blocked

**Given** the babysitter is enabled  
**When** every open PR is merge-ready or not selectable yet  
**Then** Orkie does not spawn a babysitter session just to wait

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
**Then** the session stops via ACP and is not working. No issue claim is involved. A later poll may spawn a new session if a blocked PR remains

### Shutdown stops the babysitter

**Given** a babysitter session is working  
**When** Orkie shuts down via SIGINT or SIGTERM  
**Then** that session is terminated with other ACP sessions and is not left running

## Acceptance criteria

- [ ] `babysitter.enabled` is the on/off control. When off, Orkie performs no PR lifecycle management.
- [ ] When on, there is one babysitter config identity and at most one working session.
- [ ] A session is bound to one selectable blocked PR: open, mergeable state known, and not `clean`. Ties go to the lowest PR number.
- [ ] The prompt receives only that PR's variables. A new PR assignment is a new session.
- [ ] Merge-ready means open and mergeable state `clean`. Orkie does not merge PRs.
- [ ] The babysitter does not use the issue claim label and does not consume issue session caps.
- [ ] PR reads come from the connector ([03-connector-interface-and-github.md](03-connector-interface-and-github.md)).
- [ ] The babysitter uses the ACP runtime, config identity, session identity, and a dedicated worktree ([04-acp-agent-runtime.md](04-acp-agent-runtime.md), [05-agent-orchestration.md](05-agent-orchestration.md)).
- [ ] Dashboard kill and process shutdown stop the babysitter session ([08-cli-and-dashboard.md](08-cli-and-dashboard.md)).
- [ ] While the current session has not exited, Orkie does not rotate it to another PR. The project prompt decides when the agent exits.
