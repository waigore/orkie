# ADR 009: Intake poll and delta

## Status

Superseded by [009-3-intake-poll-and-delta](../009-3-intake-poll-and-delta.md).

Was Accepted.


## Context

Feature [06](../feature/06-work-intake-and-issue-monitoring.md) defines intake eligibility, polling, snapshot comparison, and failure behavior. Feature [02](../feature/02-local-state.md) defines snapshot fields. Orchestration ([007-2](007-2-orchestration-cycle-and-claim-session-state-machine.md)) consumes the delta. `left` is how an issue left intake. Design needs fetch shape, delta algorithm, and handoff.

## Decision

### Ownership

`orkie.intake` runs on the main loop thread at `poll_interval_seconds` (default 60, minimum 15 from config). It calls only the `Connector` interface ([005-2](005-2-connector-interface-and-github-client.md)), never GitHub HTTP directly.

### Eligibility

An issue is an **intake issue** when:

- the connector reports it as an open non-PR issue, and
- its labels intersect configured `issue_labels` (at least one).

Pull requests are never intake issues (the babysitter owns PRs).

### Fetch

- Request open issues only; do not download closed-issue history.
- Complete pagination required; an incomplete page set is a failed poll.
- Snapshot fields, stored only for intake issues: `fetched_at` + `issues[]` with number, title, body, url, state, labels. Those labels are the project's labels.

### Delta algorithm

Compare the previous snapshot (or empty on first run) to the new intake set:

| Delta kind | Meaning |
|------------|---------|
| entered | Now eligible, was not |
| left | Was eligible, now not (closed, unlabeled, missing, and so on) |
| labels_changed | Still eligible but the label set changed |

`left` names issues that left intake. Orchestration drops claims by scanning every saved claim against the current intake set and config ([007-2](007-2-orchestration-cycle-and-claim-session-state-machine.md) step 4), not by consuming `left` alone. Closed issues stay unscanned.

First successful fetch: store the baseline and still run orchestration the same tick (no “wait one cycle” warm-up).

### Failure

On connector, network, auth, rate-limit, or partial-page failure of the issue fetch:

- Do not replace `snapshot` on disk.
- Do not drop or create claims because of this fetch.
- Surface the error to stderr and the dashboard. The last error is held in memory for the dashboard. No new state file.
- Retry next interval.

Local session-exit handling still runs on that tick ([007-2](007-2-orchestration-cycle-and-claim-session-state-machine.md)).

### Handoff

Return a structured `IntakeDelta` and the current intake issue list to orchestration for the same tick. The delta has no claim-label set.

Shutdown sets a flag so intake does not start a new fetch after shutdown has begun ([011-2](011-2-cli-signals-and-process-lifecycle.md)).

## Reasoning

- Open-only fetch meets large-history repos in feature 06.
- The snapshot stays the intake set feature 02 defines.
- Explicit delta kinds keep trigger evaluation testable. Orchestration step 4 re-checks every claim against the current intake set so a missing config agent is not stuck waiting for a label delta.
- Preserving the last good snapshot avoids rewriting the baseline during an outage. Leaving claims untouched on a failed fetch keeps assignments stable while sessions can still exit.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Webhooks instead of poll | Features specify poll_interval; webhooks need a public URL and host complexity |
| Full issue dump each cycle | Explicitly forbidden for large closed histories |
| Intake embeds GitHub HTTP | Breaks the connector boundary |
| Delay first-cycle spawn until the second poll | Feature 06: the first run uses the same spawn rules |
| A `claim_labeled` delta field | Claims are local. The delta does not report a GitHub label as a claim |
| Skip session-exit handling when the issue fetch fails | Exit is local. It does not depend on a successful fetch |
| Drop claims when the fetch fails | Feature 06: a failed fetch does not change claims |

## Consequences for design

- Snapshot persistence is intake's job after a successful fetch. Claim changes remain orchestration's job.
- Unit tests feed two snapshots into the delta function and assert entered, left, and label changes.
- Babysitter PR list refresh is the babysitter step on the same interval, not part of the issue snapshot ([010-2](010-2-pr-babysitter-lifecycle.md)).
