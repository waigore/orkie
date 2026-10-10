# Feature: Work Intake and Issue Monitoring

## Description

Orkie continuously monitors the project's intake issues through the connector, on `poll_interval_seconds` (default 60). An **intake issue** is an open GitHub issue that is not a pull request and that has at least one label in the configured `issue_labels`. The Orkie `claim_label` is never an intake demarcation label (see [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md)). Pull requests are left to the babysitter, including pull requests that happen to carry an issue label.

Each cycle compares the remote intake set to the locally stored snapshot, computes a delta, and feeds that delta to orchestration. Startup also reads claim labels so recovered claims can be fulfilled before new matches (see [05-agent-orchestration.md](05-agent-orchestration.md)). For repositories with very large closed-issue histories, intake does not download that history.

## Use cases

Actors are defined in [users.md](users.md).

- **Continuous Orkie process** / **Intake**: Polls the tracker and keeps a local view of intake issues and claim labels.
- **Orchestration**: Consumes eligibility, trigger fields, and claim-label presence to spawn, fulfill, or stop sessions.
- **Operator**: Expects polling to stay on the open intake set when the project has many thousands of closed issues.

## User stories

### Poll intake issues on a regular interval

**Given** Orkie has completed bootstrap and entered the continuous loop  
**When** the intake timer fires  
**Then** Orkie fetches the current open non-PR issues and the fields needed for eligibility, triggers, and prompts

### Issue labels demarcate intake from other work

**Given** `issue_labels` lists one or more labels, for example an epic label and a subissue label  
**When** intake builds the eligible set  
**Then** an open non-PR issue is eligible when it has at least one of those labels. An issue with several of them is still one intake issue. Issues with none of them are ignored. Pull requests are ignored

### Compare remote state to local known state

**Given** local state holds a previous intake snapshot  
**When** a new fetch completes  
**Then** Orkie derives a delta of issues entering the eligible set, issues leaving it, and label changes, for orchestration

### Startup uses remote claim labels

**Given** the process has just started and sessions are not working  
**When** the first fetch returns issue labels  
**Then** intake reports which open non-PR issues still have the claim label, so orchestration can fulfill, release, or leave them under the rules in [05-agent-orchestration.md](05-agent-orchestration.md)

### Drive spawn decisions from eligibility and caps

**Given** an eligible issue that matches a configured trigger and is not claimed  
**When** intake hands the cycle to orchestration  
**Then** orchestration may spawn one session for that issue if caps allow, or stop a session whose issue left the eligible set or no longer matches its trigger

### Avoid full historical issue dumps

**Given** a repository with a very large number of closed or historical issues  
**When** intake runs a normal poll cycle  
**Then** Orkie does not download the closed-issue corpus. It obtains the open issue set and derives the intake subset locally

### First run uses the same spawn rules

**Given** local state has no prior issue snapshot for this project on this user and machine  
**When** the first successful intake cycle completes  
**Then** Orkie stores the baseline snapshot and applies claim fulfillment and new-match spawn rules on that cycle. It does not wait for a second cycle to invent a baseline

### Closed or no-longer-matching issues update the plan

**Given** an issue was eligible and claimed  
**When** a later poll shows it closed, missing the demarcation labels, or no longer matching the owner's trigger  
**Then** the delta includes that change so orchestration can stop the session and release the claim

### Connector failures do not corrupt local baseline silently

**Given** a poll cycle fails because of a network error, auth error, rate limit, incomplete page set, or other connector outage  
**When** intake cannot refresh remote data  
**Then** Orkie preserves the last good snapshot, does not add or remove claim labels, surfaces the error to logs and the dashboard, and retries on a later cycle

## Acceptance criteria

- [ ] Intake runs continuously after bootstrap on `poll_interval_seconds`, default 60, minimum 15.
- [ ] An intake issue is open, is not a pull request, and has at least one configured `issue_labels` entry.
- [ ] Each successful cycle obtains issues through the connector interface and compares them to the local snapshot.
- [ ] The delta reports eligibility changes and label changes needed by `any` and `labels` triggers.
- [ ] The cycle also reports whether the claim label is present on open issues, including open issues that are not intake, so orchestration can remove those labels.
- [ ] Intake does not download the full closed-issue history on a normal poll.
- [ ] A partial multi-page fetch is a failed poll. It does not replace the last good snapshot.
- [ ] Failed polls leave the snapshot unchanged, do not add or remove claim labels, and are visible to the operator.
- [ ] Intake does not implement GitHub-specific HTTP. It uses the connector (see [03-connector-interface-and-github.md](03-connector-interface-and-github.md)).
- [ ] Process shutdown stops the intake poll loop so it does not start a new cycle after SIGINT or SIGTERM (see [08-cli-and-dashboard.md](08-cli-and-dashboard.md)).
