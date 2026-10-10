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

## Python

- Type hints on public functions and on the connector interface.
- Separate modules for orchestration, connectors, agent roles, and config loading.
- Prefer the standard library. Add a dependency when the standard library cannot do the job cleanly.
- Keep secrets and tokens out of the tree.

## Tests

- Use pytest once a suite exists.
- Exercise connector boundaries with fakes so the default run needs no network and no GitHub account.
- When orchestration or config loading changes, cover the change with an offline test.

## License

Apache License 2.0. Keep new files compatible with that license.
