# Feature: Connector Interface and GitHub

## Description

Platform access goes through an abstract connector interface that bridges Orkie's local task state with an external task and issue tracker. GitHub is the first concrete implementation. The GitHub connector reads intake issues, issue labels, issue comments, pull requests, and repository metadata needed for intake and the optional PR babysitter. It can create a label and add or remove issue labels so Orkie can claim work visibly (see [05-agent-orchestration.md](05-agent-orchestration.md)).

The GitHub token is the `GITHUB_TOKEN` environment variable. It is never read from `.orkie/`. Bootstrap fails when the token is missing, when the claim label cannot be created, when the token cannot read issues or add and remove labels, and when the babysitter is enabled but the token cannot read pull requests. Any other privilege gap produces a warning, and bootstrap may continue. The repository is `connector.repo` when set, otherwise the `origin` remote when that remote is GitHub, otherwise the only GitHub remote.

## Users and use cases

- **Operator**: Supplies `GITHUB_TOKEN` and gets a hard failure when the token is missing or lacks a required capability, and a warning for any other privilege gap.
- **Orchestrator and intake loop**: Use the connector only through the abstract interface.
- **Future integrator**: Implements another connector against the same interface without rewriting core orchestration.

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
**Then** the connector creates it. If creation is denied, bootstrap fails and the message names the label and says label-creation permission is required

### Token comes from `GITHUB_TOKEN`

**Given** Orkie is bootstrapping a GitHub-backed project  
**When** credentials are resolved  
**Then** the token is read from `GITHUB_TOKEN` and not from `.orkie/` files

### Required tracker access fails bootstrap

**Given** a token that cannot read issues, cannot add or remove labels, or cannot read pull requests while the babysitter is enabled  
**When** bootstrap verifies connector privileges  
**Then** bootstrap fails with a message that names each missing required capability

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
**Then** bootstrap fails with a clear message that names `GITHUB_TOKEN`

### Core remains usable with GitHub alone

**Given** only the GitHub connector is implemented  
**When** a project uses GitHub as its tracker  
**Then** bootstrap, intake, orchestration, and the optional PR babysitter can run without any other connector present

### Future connectors plug into the same contract

**Given** a new task-tracker host  
**When** a concrete connector implements the abstract interface  
**Then** orchestration and intake can use it by project config selection without rewriting agent spawn or local task-state logic

## Acceptance criteria

- [ ] The connector interface covers open non-PR issues (number, title, body, URL, state, labels), issue comments, label create, label add, label remove, open pull requests (number, title, URL, head branch, base branch, draft, mergeable state), and repository identity (`owner/name`).
- [ ] The GitHub connector is a concrete implementation of that interface.
- [ ] Orchestration and intake depend on the interface. GitHub SDK types do not leak into core modules.
- [ ] GitHub authentication uses `GITHUB_TOKEN`.
- [ ] Absence or emptiness of `GITHUB_TOKEN` fails bootstrap with a message that names it.
- [ ] If the claim label is missing and cannot be created, bootstrap fails with a message that names the label and the missing label-creation permission.
- [ ] Bootstrap fails when the token cannot read issues or add and remove labels. It also fails when the babysitter is enabled and the token cannot read pull requests. The error names each missing capability.
- [ ] Other insufficient privileges produce a warning that names the capability gaps. Bootstrap may continue after that warning.
- [ ] The repository is `connector.repo` when set, else a GitHub `origin`, else the sole GitHub remote. Ambiguous or missing remotes fail bootstrap and name `connector.repo`.
- [ ] Non-GitHub connectors are out of scope for v1 beyond the interface contract. GitHub alone is enough to run Orkie.
