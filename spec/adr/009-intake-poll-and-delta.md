# ADR 009: Intake poll and delta

## Status

Superseded by [009-1](009-1-intake-poll-and-delta.md).

## Context

Feature [06](../feature/06-work-intake-and-issue-monitoring.md) defines intake eligibility, polling, snapshot comparison, and failure behavior. Feature [02](../feature/02-local-state.md) defines snapshot fields. Orchestration ([007](007-orchestration-cycle-and-claim-session-state-machine.md)) consumes the delta. Design needs fetch shape, delta algorithm, and handoff.

## Decision

### Ownership

`orkie.intake` runs on the main loop thread at `poll_interval_seconds` (default 60, minimum 15 from config). It calls only the `Connector` interface ([005](005-connector-interface-and-github-client.md)), never GitHub HTTP directly.

### Eligibility

An issue is an **intake issue** when:

- connector reports it as an open non-PR issue, and
- its labels intersect configured `issue_labels` (at least one), and
- the claim label is **not** used as an intake demarcation label (config validation already forbids claim ∈ issue_labels).

Pull requests are never intake issues (babysitter owns PRs).

### Fetch

- Request open issues only; do not download closed-issue history.
- Complete pagination required; incomplete page set → failed poll.
- Snapshot fields: `fetched_at` + `issues[]` with number, title, body, url, state, labels (including claim label when present).

### Delta algorithm

Compare previous snapshot (or empty on first run) to new intake set:

| Delta kind | Meaning |
|------------|---------|
| entered | Now eligible, was not |
| left | Was eligible, now not (closed, unlabeled, missing, etc.) |
| labels_changed | Still eligible (or tracked for claim) but label set changed |
| claim_label_present | Per issue: whether `claim_label` is on the issue (for reconcile) |

First successful fetch: store baseline and still run orchestration the same tick (no “wait one cycle” warm-up).

### Failure

On connector/network/auth/rate-limit/partial-page failure:

- Do not replace `snapshot` on disk.
- Do not mutate claims from intake.
- Surface error to logs and dashboard.
- Retry next interval.

### Handoff

Return a structured `IntakeDelta` + current intake issue list to orchestration for the same tick ([007](007-orchestration-cycle-and-claim-session-state-machine.md) steps 3+).

Shutdown sets a flag so intake does not start a new fetch after SIGINT/SIGTERM ([011](011-cli-signals-and-process-lifecycle.md)).

## Reasoning

- Open-only fetch meets large-history repos in feature 06.
- Explicit delta kinds keep trigger and claim reconciliation testable without re-deriving ad hoc diffs in orchestration.
- Preserving last good snapshot avoids claim thrash during outages.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Webhooks instead of poll | Features specify poll_interval; webhooks need public URL and host complexity |
| Full issue dump each cycle | Explicitly forbidden for large closed histories |
| Intake embeds GitHub HTTP | Breaks connector boundary |
| Delay first-cycle spawn until second poll | Feature 06: first run uses the same spawn rules |

## Consequences for design

- Snapshot persistence is intake's job after a successful fetch; claim persistence remains orchestration's job.
- Unit tests feed two snapshots into the delta function and assert entered/left/label/claim flags.
- Babysitter PR list refresh is orchestration/babysitter on the same interval, not part of issue snapshot ([010](010-pr-babysitter-lifecycle.md)).
