---
name: adr-audit
description: |-
  Audit Orkie ADRs in spec/adr/ for gaps, ambiguities, inconsistencies, and
  underspecifications. Compare ADRs against each other and against upstream feature
  specs — ADRs are downstream of features and must agree with them. Use proactively
  when the user asks to audit, review, or validate ADRs, architecture decisions,
  tech stack locks, or ADR–feature alignment — for one ADR, a named aspect, or a
  full-scope pass.

  Examples:
  - user: "Audit the ADRs" → full-scope ADR peer review plus feature agreement check
  - user: "adr-audit on worktrees" → review ADR 008 against peers and feature 05
  - user: "Do ADRs still match the feature specs?" → downstream agreement audit
  - user: "Review ADR 007 against intake and state" → cross-ADR + feature consistency
  - user: "Find underspecified consequences for design" → scan Consequences sections
---

# ADR Audit

Review architecture decision records under `spec/adr/`. ADRs sit **downstream of features** and **upstream of design**: they must satisfy and agree with `spec/feature/`; they must not invent product behavior features never required.

## Scope

1. If the user names an ADR, ID, theme, or aspect → audit that slice plus every peer ADR and owning feature needed to judge agreement.
2. If none is named → **full-scope**: all **current** ADRs (`spec/adr/*.md`, not `superseded/`) plus feature coverage matrices.

Always load [references/principles.md](references/principles.md) before scoring issues.

## Workflow

1. **Orient** — Read `spec/adr/README.md` (catalog, coverage criteria, principles, naming/supersession). Skim `spec/feature/README.md` and `dependencies.md` for upstream context.
2. **Within-ADR quality** — For each in-scope current ADR, check Status / Context / Decision / Reasoning / Rejected alternatives / Consequences for design against the principles reference.
3. **Cross-ADR review** — Compare peers for conflicting decisions, overlapping ownership, broken supersession links, catalog drift, and tech-stack contradictions (esp. vs ADR 002).
4. **Upstream feature agreement** — For each in-scope ADR:
   - Owning features still require the decision (no orphan architecture)
   - Decision and consequences do not contradict stories/AC
   - No configurability, roles, or flows invented beyond feature demand
   - Feature coverage matrix rows remain accurate
5. **Classify and resolve** — Emit the report below. Prefer resolutions that keep ADRs lean, extend an existing ADR when the boundary fits, and fix features first when product intent is wrong.

## Issue types (label each issue with one)

| Label | Meaning |
|-------|---------|
| `gap` | Required decision, coverage, or consequence is missing |
| `ambiguity` | Multiple architectural readings are plausible |
| `inconsistency` | ADR↔ADR or ADR↔feature disagreement |
| `underspec` | Decision exists but Consequences (or Decision detail) are too thin for design |

## Severity

| Severity | Use when |
|----------|----------|
| `blocker` | ADR contradicts features; two current ADRs conflict on a locked choice; missing ADR coverage for a feature path that cannot be designed |
| `significant` | Incomplete consequences, stale catalog/coverage, speculative knobs, weak feature citation |
| `minor` | Naming, section polish, link hygiene, superseded-path mistakes with low design risk |

## Report format

```markdown
# ADR audit: <scope>

## Summary
<2–4 sentences: overall readiness and dominant risk themes>

## Issues

### <group name>
Grouped by theme (e.g. Bootstrap sequence, Connector privileges, Supersession hygiene).

#### [<severity>] <short title>
- **Type:** gap | ambiguity | inconsistency | underspec
- **Where:** `path` (section) [+ conflicting feature/ADR paths]
- **Finding:** what is wrong or missing
- **Impact:** why this severity
- **Resolution:** concrete edit advice; if product intent is wrong, say **fix feature first**, then ADR; balance elegance with usability (fewest moving parts, knobs only when features demand them)

## Clean areas
Brief list of aspects checked that look sound.

## Upstream / downstream notes
- Feature fixes needed before ADR edits (if any)
- Design concerns spotted but not audited here → `design-audit`
```

Order issues: blockers first, then significant, then minor. Within a severity, keep groups together.

## Constraints

- Treat only current files under `spec/adr/` as normative; use `superseded/` only for history/link checks.
- Prefer citing paths and sections over long quotes.
- Do not rewrite ADRs/features unless the user asks; deliver the audit report.
- Do not deep-audit `spec/design/` here; one-line pointers are enough.
