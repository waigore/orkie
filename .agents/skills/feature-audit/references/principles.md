# Feature spec principles (audit checklist)

Source of truth for process: `spec/feature/README.md`. Use this list while auditing; do not invent extra product rules.

## Layer role

- Features own product behavior: intent, actors’ use cases, stories, acceptance criteria, and product-level policy the product depends on (e.g. worktree policy when stories require it).
- Implementable module APIs, sequences, data schemas, UI chrome, and config *shape for code* belong in `spec/design/` after features and ADRs — flag feature files that drift into that depth as `underspec`/`ambiguity` only if product behavior is unclear; otherwise note as minor structure drift.

## Document shape (every numbered feature)

1. Description — product intent
2. Use cases — which users from `users.md` care; what they need
3. User stories — Given / When / Then
4. Acceptance criteria — checklist for done

Named subsections are fine when that feature owns the detail (schema tables, state layout, worktrees, privileges, etc.).

## Companion docs

| Doc | Role |
|-----|------|
| `vocabulary.md` | Shared terms; link, do not restate full definitions in feature files |
| `users.md` | Shared actors; feature files keep use cases only |
| `dependencies.md` | Cross-feature graph + per-feature depends-on; mermaid and table must agree |

Canonical homes (link, don’t fork):

| Concern | Home |
|---------|------|
| Config schema, prompt variables, session caps | `01-project-bootstrap-and-config.md` |
| On-disk state fields and log layout | `02-local-state.md` |
| Required GitHub privileges | `03-connector-interface-and-github.md` |
| Worktree policy | `05-agent-orchestration.md` |

## Update / consistency rules

- Change behavior in the **owning** feature file.
- Add/rename actors in `users.md`; features only describe use cases for those actors.
- Keep cross-links current (privileges ↔ 03, state fields ↔ 02, etc.).
- Adjust `dependencies.md` when reliance starts/stops; keep mermaid and by-feature table aligned.
- New features: next number, same section order, reading-order row, vocabulary/user rows if needed, dependency edges.
- Prefer stories + acceptance criteria over implementation detail.
- **Interactive vs non-interactive:** prompts only where the operator can answer; non-interactive must fail hard with no prompt (see features 01 and 08).

## Cross-feature audit prompts

- Does every story’s actor exist in `users.md`?
- Is every non-obvious term aligned with `vocabulary.md`?
- If A relies on B, is that edge in `dependencies.md`?
- Is a single concern claimed by two features without a clear owner?
- Do acceptance criteria conflict across features for the same operator-visible outcome?
- Are privilege/state/config/worktree facts only authoritative in their canonical home?
