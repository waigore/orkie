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

# Feature Audit (facade)

Canonical instructions: [`.agents/skills/feature-audit/SKILL.md`](../../../.agents/skills/feature-audit/SKILL.md).

Read that file and its `references/` as needed, then run the workflow there. Do not invent a parallel process.
