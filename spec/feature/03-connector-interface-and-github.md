# Feature: Connector Interface and GitHub

## Description

Platform access goes through an abstract connector interface that bridges Orkie's local task state with an external task and issue tracker. GitHub is the first concrete implementation. The GitHub connector reads intake issues (status, labels, and the fields needed for prompts), pull requests, and repository metadata needed for intake and the optional PR babysitter. It can create a label and add or remove issue labels so Orkie can claim work visibly (see [05-agent-orchestration.md](05-agent-orchestration.md)). It does not read or write issue comments in v1.

The GitHub token is the `GITHUB_TOKEN` environment variable. It is never read from `.orkie/`. Bootstrap behavior for missing required privileges depends on interactive vs non-interactive mode (see [Required privileges](#required-privileges)). Any other privilege gap produces a warning, and bootstrap may continue. The repository is `connector.repo` when set, otherwise the `origin` remote when that remote is GitHub, otherwise the only GitHub remote.

## Use cases

Actors are defined in [users.md](users.md).

- **Operator**: Supplies `GITHUB_TOKEN` and gets a hard failure or an interactive prompt when the token is missing or lacks a required capability, and a warning for any other privilege gap.
- **Orchestration** / **Intake**: Use the connector only through the abstract interface.
- **Future integrator**: Implements another connector against the same interface without rewriting core orchestration.

## Required privileges

Required privileges are those without which Orkie cannot perform a feature that is enabled for this run. Derive and keep this list current from the feature specs that need the capability. Each row cites its source.

| Capability | When required | Source features |
|------------|---------------|-----------------|
| Token present (`GITHUB_TOKEN` non-empty) | Always (GitHub connector) | This feature; [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md) |
| Read open issues (number, title, body, URL, state, labels) | Always | [06-work-intake-and-issue-monitoring.md](06-work-intake-and-issue-monitoring.md), [05-agent-orchestration.md](05-agent-orchestration.md) |
| Add issue label | Always (claim) | [05-agent-orchestration.md](05-agent-orchestration.md) |
| Remove issue label | Always (release claim) | [05-agent-orchestration.md](05-agent-orchestration.md) |
| Create repository label | Always when the configured `claim_label` does not already exist | [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md), [05-agent-orchestration.md](05-agent-orchestration.md) |
| Read open pull requests (number, title, URL, head, base, draft, mergeable state) | Only when `babysitter.enabled` is true | [07-pr-babysitter.md](07-pr-babysitter.md) |

**Interactive bootstrap:** If a required privilege is missing, Orkie reports each missing capability and prompts the operator (for example retry after fixing the token, or abort). It does not continue into the orchestration loop until requirements are met or the operator aborts.

**Non-interactive bootstrap:** If a required privilege is missing, bootstrap fails hard with a message that names each missing capability. No prompt.

**Warn-only:** Any other privilege Orkie probes that is not in the table above produces a warning naming the gap. Bootstrap may continue after that warning in both modes.

When a new feature needs tracker access, add a row here and cite that feature so this table stays the single checklist for bootstrap verification.

## User stories

### Abstract connector bridges task state and tracker

**Given** Orkie needs issue and repository data for a project  
**When** intake or orchestration requests tracker data or a label change  
**Then** calls go through the connector interface rather than embedding GitHub-specific APIs in the orchestrator core

### GitHub connector reads intake issues

**Given** a project configured to use the GitHub connector and a usable token  
**When** Orkie requests open issues for intake  
**Then** the connector returns open issues that are not pull requests, including number, title, body, URL, state, and labels

### GitHub connector reads pull requests for the babysitter

**Given** the PR babysitter is enabled  
**When** orchestration asks for open pull requests  
**Then** the connector returns each open PR's number, title, URL, head branch, base branch, draft flag, and mergeable state

### GitHub connector applies and removes the claim label

**Given** orchestration needs to claim or unclaim an issue  
**When** it asks the connector to add or remove the configured claim label  
**Then** the GitHub connector updates that issue's labels

### GitHub connector creates the claim label when it is missing

**Given** the resolved claim label does not exist in the repository  
**When** bootstrap ensures the label exists  
**Then** the connector creates it. If creation is denied, that is a missing required privilege and follows [Required privileges](#required-privileges)

### Token comes from `GITHUB_TOKEN`

**Given** Orkie is bootstrapping a GitHub-backed project  
**When** credentials are resolved  
**Then** the token is read from `GITHUB_TOKEN` and not from `.orkie/` files

### Required tracker access follows interactive rules

**Given** a token that cannot read issues, cannot add or remove labels, cannot create a missing claim label, or cannot read pull requests while the babysitter is enabled  
**When** bootstrap verifies connector privileges  
**Then** interactive mode prompts with each missing required capability named; non-interactive mode fails hard with the same names

### Other privilege gaps warn

**Given** a token that is missing some other permission Orkie does not require for the enabled features  
**When** bootstrap runs connector privilege verification  
**Then** Orkie emits a clear warning naming those capabilities. Bootstrap may continue after that warning

### Resolve the GitHub repository

**Given** bootstrap is preparing the GitHub connector  
**When** it chooses `owner/name`  
**Then** it uses `connector.repo` when that field is set. Otherwise it uses `origin` when `origin` is a GitHub remote. Otherwise it uses the only GitHub remote. If none of those apply, bootstrap fails and tells the operator to set `connector.repo`

### Missing token is surfaced at bootstrap

**Given** `GITHUB_TOKEN` is unset or empty  
**When** bootstrap attempts to initialize the GitHub connector  
**Then** that is a missing required privilege and follows [Required privileges](#required-privileges)

### Core remains usable with GitHub alone

**Given** only the GitHub connector is implemented  
**When** a project uses GitHub as its tracker  
**Then** bootstrap, intake, orchestration, and the optional PR babysitter can run without any other connector present

### Future connectors plug into the same contract

**Given** a new task-tracker host  
**When** a concrete connector implements the abstract interface  
**Then** orchestration and intake can use it by project config selection without rewriting agent spawn or local task-state logic

## Acceptance criteria

- [ ] The connector interface covers open non-PR issues (number, title, body, URL, state, labels), label create, label add, label remove, open pull requests (number, title, URL, head branch, base branch, draft, mergeable state), and repository identity (`owner/name`). Issue comments are out of scope for v1.
- [ ] The GitHub connector is a concrete implementation of that interface.
- [ ] Orchestration and intake depend on the interface. GitHub SDK types do not leak into core modules.
- [ ] GitHub authentication uses `GITHUB_TOKEN`.
- [ ] [Required privileges](#required-privileges) is the checklist for bootstrap verification, with citations kept current when features change.
- [ ] Missing required privileges: interactive bootstrap prompts and names each gap; non-interactive bootstrap fails hard and names each gap.
- [ ] Other insufficient privileges produce a warning that names the capability gaps. Bootstrap may continue after that warning.
- [ ] The repository is `connector.repo` when set, else a GitHub `origin`, else the sole GitHub remote. Ambiguous or missing remotes fail bootstrap and name `connector.repo`.
- [ ] Non-GitHub connectors are out of scope for v1 beyond the interface contract. GitHub alone is enough to run Orkie.
