# ADR 010: PR babysitter lifecycle

## Status

Superseded by [010-1](010-1-pr-babysitter-lifecycle.md).

## Context

Feature [07](../feature/07-pr-babysitter.md) defines an optional single babysitter session bound to one selectable blocked PR. It must not use issue claims or issue session caps, and Orkie must not merge PRs. Orchestration ([007](007-orchestration-cycle-and-claim-session-state-machine.md)) needs a clear step after issue work.

## Decision

### Gating

- When `babysitter.enabled` is false: no PR list fetch required for orchestration; no babysitter spawn; privilege “read PRs” not required ([003](003-config-load-and-bootstrap-sequence.md), [005](005-connector-interface-and-github-client.md)).
- When true: one config identity; at most one working babysitter session.

### Selection (each cycle, if no babysitter session working)

From `connector.list_open_pull_requests()`:

| Class | Rule |
|-------|------|
| Selectable blocked | Open, not draft, mergeable state known and not `clean` |
| Merge-ready | Open, not draft, mergeable state `clean` (never selected) |
| Not selectable yet | Draft, or mergeable state `unknown` / missing |

Pick the selectable blocked PR with the **lowest PR number**. Idle (no spawn) when none exist.

### Spawn

- New `session_id`; bind `pr_number` only (no issue claim label).
- Substitute only PR prompt variables from feature 01.
- Dedicated worktree ([008](008-git-worktrees.md)); full ACP permissions ([006](006-acp-agent-runtime.md)).
- Does not consume issue session caps.

### Stop and respawn

- Orkie does **not** stop a working babysitter because mergeable state became `clean` or checks changed.
- Agent exit, dashboard kill, or process shutdown end the session.
- After not working: if a selectable blocked PR still exists, a later cycle may spawn a **new** session (new id) for the PR selected that cycle. Prior context is not reused.
- Spawn failures: same three-attempt visibility as issue agents for dashboard; no claim release; after three failures leave PR unassigned until eligibility clears and attempts reset per feature 05/07.

### What Orkie does not do

- Merge PRs.
- Connector write APIs for PR comments or pushes (agent tools do that inside the session).
- Issue claim labels for babysitter work.

## Reasoning

- Lowest-number selection is deterministic and matches feature 07.
- Hands-off completion keeps orchestration simple and avoids fighting the agent.
- Cap/claim isolation prevents babysitter work from starving or inflating issue concurrency.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Stop babysitter when PR becomes merge-ready | Feature: agent decides stop |
| Multiple babysitter sessions | Feature: at most one |
| Claim label on PRs | Feature: babysitter outside issue claims |
| Orkie merges via connector | Explicitly out of scope |

## Consequences for design

- Orchestration cycle step 8 implements this ADR after issue claim/spawn.
- Dashboard shows babysitter rows in agent view with PR number; issue view unchanged.
- Kill/interrupt paths share ACP controls; kill does not touch claim labels.
