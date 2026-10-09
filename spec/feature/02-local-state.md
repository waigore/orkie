# Feature: Local State

## Description

Orkie persists project-related runtime state outside the Git repository, in a per-user, tool-owned location: `~/.local/share/orkie/<owner>--<repo>/`, where `<owner>` and `<repo>` are the resolved GitHub repository. This state includes the known intake-issue snapshot used for delta comparison, claim records, session records, spawn-failure records, a process lock, and logs needed by the dashboard.

A **claim record** says which config agent owns which issue. A **session record** says whether a live ACP session is actually working on that claim. Those are different facts. After a process start, no session is working until orchestration spawns one. Claim labels on the tracker are the restart signal for which claims still exist. Local claim records supply the config agent id those labels do not carry (see [05-agent-orchestration.md](05-agent-orchestration.md)).

Because state is per user and machine, starting Orkie under a different OS account or on a different machine uses a separate state tree and does not share prior local knowledge. Two clones of the same GitHub repository on one machine share this directory. A second live Orkie for that project refuses to start (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md)).

## Users and use cases

- **Operator**: Runs Orkie continuously and expects claim records to survive polls and crashes without rewriting the project repo.
- **Operator on another machine or account**: Accepts a fresh local state. Remote claim labels left by a crashed process on another machine have no local owner there.
- **Dashboard user**: Views session status and logs sourced from local state and live ACP sessions.

## User stories

### Store state under the per-user Orkie directory

**Given** a successfully bootstrapped project whose GitHub repository is `owner/repo`  
**When** Orkie needs to persist the issue snapshot, claim records, session records, spawn failures, or logs  
**Then** data is written under `~/.local/share/orkie/owner--repo/` and not into the project's Git working tree as the primary state store

### Isolate state by account and machine

**Given** the same Git project cloned on two machines (or used by two OS accounts)  
**When** Orkie runs on each  
**Then** each run uses its own `~/.local/share/orkie/<owner>--<repo>/` tree. Changes on one do not appear on the other

### Track claims separately from working sessions

**Given** orchestration has claimed an issue for a config agent and spawned a session  
**When** local state is updated  
**Then** the claim record stores the issue number and config agent id, and the session record stores the session id, that same config agent id and issue, and that the session is working

### A restart clears working state and keeps claim records

**Given** claim records and session records were persisted before the process stopped  
**When** Orkie starts again for the same project by the same user on the same machine  
**Then** it reloads the snapshot and claim records, and it treats every session as not working until a new spawn. It does not treat a stored working flag as evidence that a process is still alive

### Persist a claim when it is made

**Given** orchestration applies the claim label for an issue  
**When** the claim is established  
**Then** the claim record, including the config agent id, is persisted then, not deferred until process shutdown, so a later crash can still tell who owned the claim

### Retain agent logs for the dashboard

**Given** one or more sessions are or were active  
**When** an operator opens the local web dashboard  
**Then** available status and log information for those sessions can be read from local state, supplemented by live ACP data where supported

### Keep a bounded, redacted session log

**Given** a session produces log output  
**When** Orkie stores that log  
**Then** it keeps the newest 1 MB for that session, drops older bytes, and stores no copy of the `GITHUB_TOKEN` value

### Record a spawn failure until the next poll

**Given** a spawn attempt for a config agent and an issue, or for the babysitter and a PR, fails  
**When** local state is updated  
**Then** a spawn-failure record stores the config id, config name, issue or PR number, and a redacted error. The dashboard can read that record until the next poll retries the spawn or the work item is no longer eligible

### Graceful shutdown clears claims in the stored snapshot

**Given** Orkie is shutting down via SIGINT or SIGTERM and has released its claim labels (see [05-agent-orchestration.md](05-agent-orchestration.md))  
**When** the shutdown flush runs  
**Then** persisted claim records for labels that were released are gone, and no session is stored as working

### Failed label release keeps the owner record

**Given** graceful shutdown could not remove one or more claim labels  
**When** the shutdown flush runs  
**Then** those claim records keep the config agent id and are stored as not working, so the next start can fulfill the surviving remote labels

## Acceptance criteria

- [ ] Default local state root is `~/.local/share/orkie/<owner>--<repo>/`, using the resolved GitHub owner and repository name.
- [ ] Project id is stable for that GitHub repository and is shared by clones of it on the same machine and OS account.
- [ ] Local state holds the intake snapshot, claim records (issue number and config agent id), session records (session id, config agent id, bound issue or PR, working flag), spawn-failure records, the process lock, and agent status and log artifacts needed by the dashboard.
- [ ] Each session log keeps its newest 1 MB. Stored logs and spawn-failure errors do not contain the `GITHUB_TOKEN` value.
- [ ] Claim records and working flags are separate. Process start marks every session not working.
- [ ] A new or updated claim record is persisted when the claim is established.
- [ ] The Git project tree is not the primary store for orchestration runtime state.
- [ ] State is not shared across OS users or machines. This isolation is documented.
- [ ] After a restart on the same user and machine, Orkie reloads the last persisted snapshot and claim records.
- [ ] Graceful shutdown flushes local state before exit so the next start sees the post-release claim records.
- [ ] Intake, orchestration, and the dashboard share one consistent layout under the project state directory.
