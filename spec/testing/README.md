# Orkie Testing Specs

Standalone testing documents for Orkie. This layer sits beside [features](../feature/), [ADRs](../adr/), and [design](../design/). It does not redefine product behavior or replace the offline unit suite locked in [ADR 002-1](../adr/002-1-tech-stack-and-dependencies.md).

## Tiers

| Tier | Where | Network / GitHub | Role |
|------|-------|------------------|------|
| Offline suite | [`tests/`](../../tests/) (pytest; layout in [`tests/README.md`](../../tests/README.md)) | No (fakes; temp git only) | Default CI ([`.github/workflows/tests.yml`](../../.github/workflows/tests.yml)); ≥80% coverage of `orkie/` |
| Live integrated acceptance | This directory | Yes — designated test repository | System-level eval against a real GitHub fixture and real ACP agent |

Live acceptance is manual or scheduled. It is credentialed, destructive to the designated test repository, and **not** part of the coverage gate.

## Catalog

| File | Contents |
|------|----------|
| [01-integrated-acceptance.md](01-integrated-acceptance.md) | Purpose, methods, pristine preparation, hybrid pass criteria for the live scenario |

## Reading order

1. [ADR 002-1](../adr/002-1-tech-stack-and-dependencies.md) — offline test stack and what CI runs
2. [01-integrated-acceptance.md](01-integrated-acceptance.md) — live acceptance scenario
3. Owning features for claim/spawn/intake behavior: [05](../feature/05-agent-orchestration.md), [06](../feature/06-work-intake-and-issue-monitoring.md), [03](../feature/03-connector-interface-and-github.md)

## Updating these specs

- Change live-scenario purpose, methods, preparation, or pass criteria only in this directory.
- Do not pull live GitHub or real ACP into the default pytest suite without updating ADR 002 first.
- Fixture-repo product acceptance criteria live in the fixture repository, not here.
