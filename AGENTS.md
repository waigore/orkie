# Orkie

Orkie is a Python orchestrator: run it in a cloned Git repo; it reads that project's `.orkie` settings and spawns AI agents for the roles defined there.
GitHub is the supported platform; further hosts plug in through connectors. Details: [`spec/feature/`](spec/feature/), [`spec/adr/`](spec/adr/).

## Scope

This file is for agents changing the orkie codebase. Settings, role prompts, and project instructions live in the target project's `.orkie/` (roles in `config.yaml`; no built-in role catalog).
Product behavior and acceptance criteria: [`spec/feature/`](spec/feature/).

## Architecture

Platform access goes through a connector interface; core orchestration depends on that interface so hosts can be added without rewriting it. Prefer extending an existing connector, role, or config field when the behavior belongs there.
Decisions: [`spec/adr/`](spec/adr/) (current files only — not [`superseded/`](spec/adr/superseded/); catalog in [`spec/adr/README.md`](spec/adr/README.md)). Implementable design: [`spec/design/`](spec/design/). Live acceptance: [`spec/testing/`](spec/testing/).

## Skills

Canonical skill bodies live under [`.agents/skills/`](.agents/skills/) (one folder per skill). Do not treat any agent's native skills path as the source of truth.
When adding or updating a skill, also update thin facades under `.cursor/skills/`, `.opencode/skill/`, and `.grok/skills/` that point at the shared body — do not duplicate it.

## Implementation

Language, dependencies, secrets, and tests: [ADR 002](spec/adr/002-2-tech-stack-and-dependencies.md). Package layout: [ADR 001](spec/adr/001-2-process-model-and-module-layout.md). Conventions: [`spec/design/conventions.md`](spec/design/conventions.md).
Offline unit tests: [`tests/`](tests/) (see [`tests/README.md`](tests/README.md)); live acceptance is out of band under [`spec/testing/`](spec/testing/).

## License

Apache License 2.0. Keep new files compatible with that license.
