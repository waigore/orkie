# ADR 010: PR babysitter lifecycle

## Status

Accepted

Supersedes [010-1](superseded/010-1-pr-babysitter-lifecycle.md).

## Context

Feature [07](../feature/07-pr-babysitter.md) defines an optional single babysitter session bound to one selectable blocked PR. It does not take a local issue claim and does not consume issue session caps, and Orkie must not merge PRs. Orchestration ([007-2](007-2-orchestration-cycle-and-claim-session-state-machine.md)) needs a clear step after issue work.

## Decision

### Gating

- When `babysitter.enabled` is false: no PR list fetch for orchestration; no babysitter spawn; the “read PRs” privilege is not required ([003-2](003-2-config-load-and-bootstrap-sequence.md), [005-2](005-2-connector-interface-and-github-client.md)).
- When true: one config identity; at most one working babysitter session.

### Selection (each cycle, if no babysitter session is working)

From `connector.list_open_pull_requests()`:

| Class | Rule |
|-------|------|
| Selectable blocked | Open, not draft, mergeable state known and not `clean` |
| Merge-ready | Open, not draft, mergeable state `clean` (never selected) |
| Not selectable yet | Draft, or mergeable state `unknown` or missing |

Skip a PR that has three consecutive spawn failures. Those failures clear on a poll where that PR is not selectable, and on a successful spawn. Pick the selectable blocked PR with the **lowest PR number** among the rest. Idle (no spawn) when none remain.

A failed PR fetch skips this step only. It does not change claims or issue sessions. This step still runs when the issue fetch failed, as long as the PR fetch succeeded ([007-2](007-2-orchestration-cycle-and-claim-session-state-machine.md)).

### Spawn

- New `session_id` minted by orchestration; bind `pr_number` only. No local issue claim.
- Substitute every feature-01 token. Issue tokens are empty ([003-2](003-2-config-load-and-bootstrap-sequence.md)).
- Dedicated worktree ([008-1](008-1-git-worktrees.md)); implicit permission grants ([006-1](006-1-acp-agent-runtime.md)).
- Does not consume issue session caps.

### Stop and respawn

- Orkie does **not** stop a working babysitter because the PR changed state. That includes mergeable state becoming `clean`, checks changing, the PR closing, or the PR merging.
- Agent exit, dashboard kill, or process shutdown end the session. Dashboard kill deletes only that session.
- After it is not working: if a selectable blocked PR still exists, a later cycle may spawn a **new** session (new id) for the PR selected that cycle. Prior context is not reused.
- Process shutdown ends the babysitter by the same mode as other sessions ([011-2](011-2-cli-signals-and-process-lifecycle.md)).

### What Orkie does not do

- Merge PRs.
- Connector write APIs for PR comments or pushes (agent tools do that inside the session).
- A local issue claim for babysitter work.

## Reasoning

- Lowest-number selection is deterministic and matches feature 07. Skipping a PR that has failed three times lets the next lowest selectable PR run, and clearing those failures when the PR leaves the selectable set matches feature 07.
- Hands-off completion keeps orchestration from fighting the agent, including after the PR closes or merges.
- Cap and claim isolation keeps babysitter work from starving or inflating issue concurrency.
- Issue tokens are emptied rather than left as literal placeholders, matching feature 01.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Stop the babysitter when the PR becomes merge-ready, closes, or merges | Feature: the agent, kill, or shutdown decides stop |
| Multiple babysitter sessions | Feature: at most one |
| A local issue claim for babysitter work | Feature: the babysitter is outside issue claims |
| Orkie merges via the connector | Explicitly out of scope |
| Substitute only PR tokens and leave issue tokens untouched | Feature 01 replaces every token; the unused ones are empty |
| A new state file for babysitter attempts | Spawn-failure records already store the attempt history |
| Skip the babysitter whenever the issue fetch fails | PR fetch failure is the only skip. The two fetches are independent |

## Consequences for design

- Orchestration cycle step 8 implements this ADR after issue claim and spawn.
- Dashboard shows babysitter rows in the agent view with the PR number. The issue view is unchanged.
- Kill and interrupt share ACP controls through orchestration. Kill of a babysitter does not drop an issue claim.
