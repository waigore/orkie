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

# Design Audit (facade)

Canonical instructions: [`.agents/skills/design-audit/SKILL.md`](../../../.agents/skills/design-audit/SKILL.md).

Read that file and its `references/` as needed, then run the workflow there. Do not invent a parallel process.
