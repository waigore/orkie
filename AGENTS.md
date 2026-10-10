# Orkie

Orkie is a Python orchestrator. Started inside a cloned Git repository, it reads that project's `.orkie` settings and spawns AI agents for the roles that project defines.

GitHub is the supported platform. Further task trackers and version-control hosts plug in through connectors. The core stays usable with the GitHub connector alone.

## Scope

- Orkie runs in the target project. Settings, role prompts, and project-specific instructions live in that project's `.orkie` directory.
- This file is for agents changing the orkie codebase.
- Agent roles are project-defined in `.orkie/config.yaml`. Orkie does not require a built-in role catalog. New roles use the same orchestration path.

## Architecture

- Platform access goes through a connector interface: issues, pull requests, repositories, and the comments those need. GitHub is the first connector.
- Core orchestration and agent roles depend on that interface, so another host can be added without rewriting them.
- A project with a `.orkie` directory runs out of the box. The GitHub connector takes its token from the `GITHUB_TOKEN` environment variable.
- Extend an existing connector, role, or config field when the behavior belongs there.
- Design decisions live in [`spec/adr/`](spec/adr/). Files in that directory are current; superseded ADRs live under [`spec/adr/superseded/`](spec/adr/superseded/). When linking an ADR, use the current file (see the catalog in [`spec/adr/README.md`](spec/adr/README.md)), not anything under `superseded/`.
- Implementable component, sequence, data, UI, and config design lives in [`spec/design/`](spec/design/).

## Skills

- Project-related skills live under [`.agents/skills/`](.agents/skills/), one folder per skill. That layout keeps skill selection and execution vendor-neutral.
- Put the skill definition and content (instructions, scripts, references, assets) in that folder. Do not treat any coding agent's native skills path as the source of truth.
- Whenever a skill is created or updated under `.agents/skills/`, also create or update thin native facades so Cursor, OpenCode, and Grok Build can load it:
  - Cursor: [`.cursor/skills/<name>/`](.cursor/skills/)
  - OpenCode: [`.opencode/skill/<name>/`](.opencode/skill/)
  - Grok Build: [`.grok/skills/<name>/`](.grok/skills/)
- Those facades must point at or wrap the shared skill under `.agents/skills/`; they must not duplicate the skill body.

## Implementation

- Language, dependencies, secrets, and tests: [`spec/adr/002-1-tech-stack-and-dependencies.md`](spec/adr/002-1-tech-stack-and-dependencies.md).
- Tests: offline pytest with `connectors`/`acp` fakes; ≥80% overall coverage. Details: [`spec/adr/002-1-tech-stack-and-dependencies.md`](spec/adr/002-1-tech-stack-and-dependencies.md).
- Package and module layout: [`spec/adr/001-2-process-model-and-module-layout.md`](spec/adr/001-2-process-model-and-module-layout.md).

## License

Apache License 2.0. Keep new files compatible with that license.
