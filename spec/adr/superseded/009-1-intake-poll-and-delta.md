## Status

Superseded by [009-2](../009-2-intake-poll-and-delta.md).

Supersedes [009](009-intake-poll-and-delta.md).

## Context

Feature [06](../feature/06-work-intake-and-issue-monitoring.md) defines intake eligibility, polling, snapshot comparison, and failure behavior. Feature [02](../feature/02-local-state.md) defines snapshot fields. Orchestration ([007-1](007-1-orchestration-cycle-and-claim-session-state-machine.md)) consumes the delta and the claim-label set. Design needs fetch shape, delta algorithm, and handoff.

## Decision

### Ownership

`orkie.intake` runs on the main loop thread at `poll_interval_seconds` (default 60, minimum 15 from config). It calls only the `Connector` interface ([005-1](005-1-connector-interface-and-github-client.md)), never GitHub HTTP directly.

### Eligibility

An issue is an **intake issue** when:

- the connector reports it as an open non-PR issue, and
- its labels intersect configured `issue_labels` (at least one), and
- the claim label is **not** used as an intake demarcation label (config validation already forbids the claim label appearing in `issue_labels`).

Pull requests are never intake issues (the babysitter owns PRs).

### Fetch

- Request open issues only; do not download closed-issue history.
- Complete pagination required; an incomplete page set is a failed poll.
- Snapshot fields, stored only for intake issues: `fetched_at` + `issues[]` with number, title, body, url, state, labels (including the claim label when present).

### Delta algorithm

Compare the previous snapshot (or empty on first run) to the new intake set:

| Delta kind | Meaning |
|------------|---------|
| entered | Now eligible, was not |
| left | Was eligible, now not (closed, unlabeled, missing, and so on) |
| labels_changed | Still eligible but the label set changed |
| claim_labeled | Open issues that carry `claim_label`, including issues that are not intake |

`claim_labeled` is not written into the snapshot. It is how orchestration sees a claim label on an issue that has left the intake set, and how it reconciles labels after restart. Closed issues stay unscanned.

First successful fetch: store the baseline and still run orchestration the same tick (no “wait one cycle” warm-up).

### Failure

On connector, network, auth, rate-limit, or partial-page failure of the issue fetch:

- Do not replace `snapshot` on disk.
- Do not add or remove claim labels from this fetch.
- Surface the error to stderr and the dashboard. The last error is held in memory for the dashboard. No new state file.
- Retry next interval.

Local session-exit handling still runs on that tick ([007-1](007-1-orchestration-cycle-and-claim-session-state-machine.md)).

### Handoff

Return a structured `IntakeDelta`, the current intake issue list, and the `claim_labeled` issues to orchestration for the same tick.

Shutdown sets a flag so intake does not start a new fetch after SIGINT/SIGTERM ([011-1](011-1-cli-signals-and-process-lifecycle.md)).

## Reasoning

- Open-only fetch meets large-history repos in feature 06.
- The snapshot stays the intake set feature 02 defines. Claim labels on other open issues are a handoff, not a second stored corpus.
- Explicit delta kinds keep trigger and label reconciliation testable.
- Preserving the last good snapshot avoids rewriting the baseline during an outage. Leaving labels untouched on a failed fetch keeps the tracker stable while sessions can still exit.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Webhooks instead of poll | Features specify poll_interval; webhooks need a public URL and host complexity |
| Full issue dump each cycle | Explicitly forbidden for large closed histories |
| Intake embeds GitHub HTTP | Breaks the connector boundary |
| Delay first-cycle spawn until the second poll | Feature 06: the first run uses the same spawn rules |
| Store non-intake claim-labeled issues in the snapshot | The snapshot is the intake set. Orchestration only needs them for the current tick |
| Skip session-exit handling when the issue fetch fails | Exit is local. It does not depend on a successful fetch |

## Consequences for design

- Snapshot persistence is intake's job after a successful fetch. Label changes remain orchestration's job.
- Unit tests feed two snapshots into the delta function and assert entered, left, and label changes, and they assert `claim_labeled` includes a non-intake open issue.
- Babysitter PR list refresh is the babysitter step on the same interval, not part of the issue snapshot ([010-1](010-1-pr-babysitter-lifecycle.md)).
