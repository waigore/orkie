# Design principles (audit checklist)

Source of truth for process: `spec/design/README.md`. Features and current ADRs outrank design.

## Layer role

```text
Features → ADRs → Design → Code
```

| Layer | Owns |
|-------|------|
| `spec/feature/` | Product behavior, stories, AC, vocabulary |
| `spec/adr/` | Process model, modules, libraries, locked flows |
| `spec/design/` | Implementable interfaces, schemas, sequences, UI, config shape |
| Code | Implementation matching design |

## Design principles

1. **Simple.** Fewest components, interactions, and integrations that still satisfy features. Do not invent packages, knobs, or services beyond ADR 001’s package map and knobs required by feature 01.
2. **No guesswork.** Every public function signature, JSON field, HTTP route, poll-cycle step, error path, and wire message needed for v1 is specified here or cited to a feature/ADR table. Missing → fix design (or owning feature/ADR) before coding.
3. **Traceable.** Each design file lists owning features and ADRs. Component sections name the stories they satisfy. Do not restate full AC; link to features. Do not reopen ADR alternatives.

## Catalog files

| File | Contents |
|------|----------|
| `components.md` | Purpose, scope, interfaces, lifecycle per package (ADR 001 order) |
| `sequences.md` | Happy-path diagrams; unhappy flows and retries as notes |
| `data.md` | On-disk and in-memory structures, ownership, readers |
| `ui.md` | CLI surface and dashboard pages, navigation, CTAs |
| `config.md` | Configurable fields, YAML shape, defaults, precedence |

Reading order: config → components → data → sequences → ui.

## Coverage matrices

- Feature coverage and ADR coverage tables in `spec/design/README.md` must stay accurate.
- Spot-check that cited design files actually carry the behavior.

## Locked design choices (beyond ADRs)

Normative for v1 unless explicitly under revision — see table in `spec/design/README.md` (doc layout, intake fetch failure behavior, warn-only privilege probes, ACP depth). Flag design text that contradicts those locks.

## Update rules

1. Product behavior changes → owning feature first, then owning ADR if architecture shifts, then design.
2. Architecture/library changes → supersede or revise ADR, then design.
3. Implementable detail only → update design; cite feature/ADR.
4. Keep coverage matrices current.
5. Prefer extending an existing design section over adding a new component.

## Cross-layer audit prompts

- Can an implementer code the path without inventing signatures, fields, or error handling?
- Do sequences call only APIs defined in `components.md` (or clearly cited)?
- Does every persisted field in `data.md` have a writer and at least one reader?
- Do config keys in `config.md` match feature 01 / ADR config decisions and have consumers?
- Does UI expose actions that exist on the control/CLI paths in components/sequences?
- Any design invention (package, knob, mode) not justified by feature + ADR?
- Links point at **current** ADR files, not `superseded/`?
