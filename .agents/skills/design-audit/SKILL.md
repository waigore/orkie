---
name: design-audit
description: |-
  Audit Orkie design specs in spec/design/ for gaps, ambiguities, inconsistencies,
  and underspecifications. Compare design docs against each other, against ADRs, and
  against feature specs — design is downstream of both and must agree with them. Use
  proactively when the user asks to audit, review, or validate design docs, components,
  sequences, data, UI, config shape, or readiness to implement — for one file/aspect
  or a full-scope pass.

  Examples:
  - user: "Audit the design specs" → full-scope design review vs peers, ADRs, and features
  - user: "design-audit on sequences" → review sequences.md against components/data and upstream
  - user: "Is design ready to implement ACP?" → aspect audit with no-guesswork checklist
  - user: "Check design against ADR 007" → downstream agreement for orchestration
  - user: "Find underspecified interfaces in components.md" → signature/lifecycle gap scan
---

# Design Audit

Review implementable design under `spec/design/`. Design sits **downstream of features and ADRs**: it must satisfy both, reopen neither product intent nor locked architecture, and be detailed enough that v1 code needs no guesswork.

## Scope

1. If the user names a design file, package, theme, or aspect → audit that slice plus peer design files and the cited features/ADRs needed to judge agreement.
2. If none is named → **full-scope**: all design catalog files (`README`, `config`, `components`, `data`, `sequences`, `ui`) and their coverage matrices.

Always load [references/principles.md](references/principles.md) before scoring issues.

## Workflow

1. **Orient** — Read `spec/design/README.md` (principles, layers, coverage, locked choices, update rules). Use ADR and feature catalogs to map ownership.
2. **Within-design quality** — For each in-scope file, check completeness against the no-guesswork bar: public signatures, fields, routes, poll steps, error paths, wire messages as required for v1.
3. **Cross-design review** — Compare design files for conflicting shapes, ownership gaps, sequence steps that call undefined APIs, data fields with no writer/reader, UI/actions with no control path, config keys with no consumer.
4. **Upstream ADR agreement** — Decisions match current ADRs (not `superseded/`); package map and libraries align with 001/002; no reopened alternatives; coverage matrix accurate.
5. **Upstream feature agreement** — Stories/AC still held; no extra product behavior; component sections cite owning stories; interactive vs non-interactive respected where design surfaces prompts.
6. **Classify and resolve** — Emit the report below. Prefer resolutions that extend existing sections, cite feature/ADR instead of restating, and fix the highest correct layer (feature → ADR → design).

## Issue types (label each issue with one)

| Label | Meaning |
|-------|---------|
| `gap` | Implementable detail or coverage link is missing |
| `ambiguity` | Multiple implementation readings are plausible |
| `inconsistency` | Design↔design, design↔ADR, or design↔feature disagreement |
| `underspec` | Topic is mentioned but not specified enough to code without guessing |

## Severity

| Severity | Use when |
|----------|----------|
| `blocker` | Contradicts feature or current ADR; missing detail that blocks correct v1 implementation of a core path |
| `significant` | Incomplete interfaces/sequences/schemas, coverage drift, or conflicts that will cause rework |
| `minor` | Clarity, naming, matrix polish, redundant restatement with low implementation risk |

## Report format

```markdown
# Design audit: <scope>

## Summary
<2–4 sentences: implementability readiness and dominant risk themes>

## Issues

### <group name>
Grouped by theme (e.g. Intake failure path, ACP wire protocol, Dashboard control API).

#### [<severity>] <short title>
- **Type:** gap | ambiguity | inconsistency | underspec
- **Where:** `path` (section) [+ conflicting feature/ADR/design paths]
- **Finding:** what is wrong or missing
- **Impact:** why this severity / what implementers would guess wrong
- **Resolution:** concrete edit advice; if behavior/architecture is wrong, say **fix feature and/or ADR first**; balance elegance with usability (fewest components/knobs; match ADR package map)

## Clean areas
Brief list of aspects checked that look sound.

## Upstream notes
Feature or ADR fixes that should precede design edits (if any).
```

Order issues: blockers first, then significant, then minor. Within a severity, keep groups together.

## Constraints

- Features and current ADRs outrank design on conflicts.
- Prefer citing paths and sections over long quotes.
- Do not rewrite specs unless the user asks; deliver the audit report.
- Locked design choices in `spec/design/README.md` are normative for v1 unless the user is explicitly revisiting them — then flag disagreement with features/ADRs still.
