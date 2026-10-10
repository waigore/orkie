# Orkie Feature Specs

Feature-level product specs for architecture planning. Use them to agree behavior before implementation. This README only explains how to read and change the set.

## Companion docs

| Doc | Role |
|-----|------|
| [vocabulary.md](vocabulary.md) | Shared terms. Link here; do not restate full definitions in feature files. |
| [users.md](users.md) | Shared actors. Feature files keep use cases only; user definitions live here. |
| [dependencies.md](dependencies.md) | Cross-feature dependency graph and per-feature depends-on list. |

Canonical detail that other specs should link to (not copy):

| Concern | Home |
|---------|------|
| Config schema, prompt variables, session caps | [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md) |
| On-disk state fields and log layout | [02-local-state.md](02-local-state.md#state-layout) |
| Required GitHub privileges | [03-connector-interface-and-github.md](03-connector-interface-and-github.md#required-privileges) |
| Worktree policy | [05-agent-orchestration.md](05-agent-orchestration.md#worktrees) |

## Spec shape

Every numbered feature file uses the same sections:

1. **Description** — product intent for that feature
2. **Use cases** — which [users](users.md) care and what they need from this feature
3. **User stories** — Given / When / Then
4. **Acceptance criteria** — checklist for done

Named subsections (schema tables, state layout, worktrees, and so on) are fine when that feature owns the detail.

## Reading order

Read companion docs as needed, then features in number order the first time. Later, jump via [dependencies.md](dependencies.md).

1. [01-project-bootstrap-and-config.md](01-project-bootstrap-and-config.md) — config, bootstrap, interactive vs non-interactive
2. [02-local-state.md](02-local-state.md) — per-user state tree and record fields
3. [03-connector-interface-and-github.md](03-connector-interface-and-github.md) — connector, GitHub, privileges
4. [04-acp-agent-runtime.md](04-acp-agent-runtime.md) — ACP sessions
5. [05-agent-orchestration.md](05-agent-orchestration.md) — claim labels, caps, spawn, worktrees
6. [06-work-intake-and-issue-monitoring.md](06-work-intake-and-issue-monitoring.md) — intake poll and delta
7. [07-pr-babysitter.md](07-pr-babysitter.md) — optional PR babysitter
8. [08-cli-and-dashboard.md](08-cli-and-dashboard.md) — CLI, dashboard, shutdown

## Updating specs

- **Change behavior in the owning feature file.** Link to [vocabulary.md](vocabulary.md) for shared terms; update that file when a term's meaning changes.
- **Add or rename actors in [users.md](users.md).** Feature files only describe use cases for those actors.
- **Keep cross-links current.** When you add a required privilege, update the table in 03 and cite the feature that needs it. When you add a state field, update the tables in 02.
- **Adjust [dependencies.md](dependencies.md)** when a feature starts or stops relying on another. Keep the mermaid and the by-feature table aligned.
- **Preserve structure.** New features get the next number, the same section order, a reading-order row above, vocabulary/user rows if needed, and dependency edges.
- **Prefer stories + acceptance criteria** over implementation detail. Design-level policy (for example worktrees) belongs in the owning feature when product behavior depends on it.
- **Interactive vs non-interactive** is a cross-cutting principle: define prompts only where the operator can answer; non-interactive must fail hard with no prompt (see 01 and 08).
