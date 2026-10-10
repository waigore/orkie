---
name: feature-audit
description: |-
  Audit Orkie feature specs in spec/feature/ for gaps, ambiguities, inconsistencies,
  and underspecifications. Compare features against each other and against companion
  docs (vocabulary, users, dependencies). Use proactively when the user asks to audit,
  review, or validate feature specs, stories, acceptance criteria, or product behavior
  docs — for one feature, a named aspect, or a full-scope pass.

  Examples:
  - user: "Audit the feature specs" → full-scope cross-feature review with severity-ranked issues
  - user: "feature-audit on orchestration" → review feature 05 and its cross-links to peers
  - user: "Are the feature specs consistent on worktrees?" → targeted aspect audit across features
  - user: "Review feature 01 against the rest" → peer consistency check for bootstrap/config
  - user: "Find gaps in acceptance criteria" → scan stories/AC for underspec and conflicts
---

# Feature Audit

Review product behavior specs under `spec/feature/`. Features are the upstream layer; this audit does **not** judge ADRs or design (use `adr-audit` / `design-audit` for those).

## Scope

1. If the user names a feature, file, theme, or aspect → audit that slice and every peer touchpoint needed to judge consistency.
2. If none is named → **full-scope**: all numbered features plus companion docs.

Always load [references/principles.md](references/principles.md) before scoring issues.

## Workflow

1. **Orient** — Read `spec/feature/README.md`, then `vocabulary.md`, `users.md`, `dependencies.md` as needed. For full-scope, walk features in reading order; for a slice, open the owning file and every linked peer.
2. **Within-file quality** — For each in-scope feature, check Description / Use cases / User stories / Acceptance criteria against the principles reference (structure, ownership, interactive vs non-interactive, stories+AC over implementation detail).
3. **Cross-feature review** — Compare peers for:
   - Contradictory behavior or vocabulary
   - Duplicate ownership of the same detail
   - Missing depends-on edges vs actual reliance
   - Stale or one-way links (privileges, state fields, config, worktrees)
   - Actors used in stories but missing from `users.md`
   - Terms used with conflicting meaning vs `vocabulary.md`
4. **Classify and resolve** — Emit the report below. Suggest a fix per issue that balances technical elegance with usability (prefer clear ownership, link-not-copy, and operator-safe defaults).

## Issue types (label each issue with one)

| Label | Meaning |
|-------|---------|
| `gap` | Required behavior or ownership is missing |
| `ambiguity` | Multiple readings are plausible |
| `inconsistency` | Specs disagree with each other |
| `underspec` | Intent is present but not implementable/testable enough at the feature layer |

## Severity

| Severity | Use when |
|----------|----------|
| `blocker` | Implementation or planning cannot proceed safely; contradictory product rules; missing ownership for a core path |
| `significant` | Likely wrong or incomplete behavior; missing cross-links/deps that will confuse design/ADR work |
| `minor` | Clarity, structure, naming, or polish; low risk of wrong product behavior |

## Report format

```markdown
# Feature audit: <scope>

## Summary
<2–4 sentences: overall readiness and dominant risk themes>

## Issues

### <group name>
Grouped by theme (e.g. Worktrees, Config ownership, Intake vs orchestration).

#### [<severity>] <short title>
- **Type:** gap | ambiguity | inconsistency | underspec
- **Where:** `path` (section/anchor if useful) [+ conflicting `path`…]
- **Finding:** what is wrong or missing
- **Impact:** why this severity
- **Resolution:** concrete edit advice (which file owns the fix; what to add/change/remove; link vs restate)

## Clean areas
Brief list of aspects checked that look sound (avoid false confidence padding).

## Out of scope
Note ADR/design concerns spotted but not audited here; point to `adr-audit` / `design-audit` if relevant.
```

Order issues: blockers first, then significant, then minor. Within a severity, keep groups together.

## Constraints

- Prefer citing file paths and section names over long quotes.
- Do not rewrite specs unless the user asks; the deliverable is the audit report.
- Do not treat `spec/adr/` or `spec/design/` as sources of product truth in this skill.
- When a resolution needs an ADR/design change, say so in one line and leave detail to the downstream audit skills.
