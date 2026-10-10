# ADR principles (audit checklist)

Source of truth for process: `spec/adr/README.md`. Features remain authoritative for product behavior.

## Layer role

| Layer | Owns |
|-------|------|
| `spec/feature/` | What Orkie does; vocabulary; acceptance criteria |
| `spec/adr/` | How Orkie is built: process model, modules, sequences, libraries |
| `spec/design/` | Implementable detail: interfaces, schemas, UI, config shape |

- ADRs cite owning features; they do **not** restate acceptance criteria.
- When product behavior changes: **feature first**, then owning ADR, then design.
- ADRs must **agree with** features. Feature wins on product intent conflicts.

## Coverage criteria (full set)

1. **Satisfy all features** — every numbered feature is covered by one or more ADRs (catalog Feature coverage).
2. **Inform component design** — together, ADRs are detailed/consistent enough to design packages, modules, flows, states, sequences without inventing unstated architecture.
3. **Cover the tech stack** — approved deps, stdlib-first choices, rejected libraries (especially ADR 002).

## General principles

1. **Keep it simple.** Fewest components, interactions, and third-party libraries that still achieve feature goals. Reject options that add moving parts without a clear need from the specs.
2. **Configurability only when the feature demands it.** No knobs, modes, or pluggable surfaces unless a feature requires that variability. Fixed defaults beat speculative flexibility.

## Document shape (every ADR)

1. Status — `Proposed` / `Accepted` / `Superseded` (superseded files under `superseded/`; Status links successor ↔ predecessor)
2. Context — why a decision is needed; link features
3. Decision — what we chose, including libraries/APIs when relevant
4. Reasoning — why
5. Rejected alternatives — notable options and why not
6. Consequences for design — modules, flows, states, sequences implied

## Naming, layout, linking

- Current ADRs: `spec/adr/*.md` only (`Proposed` or `Accepted` + README).
- Supersession: same `NNN`, revision suffix `-1`, `-2`, …; move prior current file to `superseded/`; do **not** mint a new sequence for a replacement.
- Catalog lists only the **current** file per `NNN`.
- Link current files (or catalog); do not link into `superseded/` except Status history.

## Clarification / update rules

- New catalog entries only after Context, Decision, Rejected alternatives, and Consequences are agreed; Status starts `Proposed` until accepted.
- Prefer extending an existing ADR when the change is the same decision boundary.
- New sequence only for a distinct architectural choice that is not replacing an existing ADR.

## Cross-layer audit prompts

- Does every Decision trace to a real feature need (Context links + catalog Features column)?
- Do Consequences contradict any story/AC in owning features?
- Do two current ADRs lock incompatible libraries, process models, or sequences?
- Is the Feature coverage matrix missing a real dependency or listing a stale one?
- Are Consequences rich enough that design can proceed without inventing architecture?
- Are superseded files correctly relocated and linked both ways?
