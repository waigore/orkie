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

# ADR Audit (facade)

Canonical instructions: [`.agents/skills/adr-audit/SKILL.md`](../../../.agents/skills/adr-audit/SKILL.md).

Read that file and its `references/` as needed, then run the workflow there. Do not invent a parallel process.
