# Orkie

Orkie is a long-running Python orchestrator. You run it against a cloned Git repo; it loads that project's `.orkie/` settings, watches labeled GitHub issues, and spawns AI agents (via ACP) for the roles defined in config. GitHub is the supported host; other platforms can plug in through a connector interface.

Roles, prompts, and intake labels live in the **target project**, not in Orkie itself. There is no built-in role catalog.

## Quick start

```bash
pip install -e .
export GITHUB_TOKEN=ghp_…
cd /path/to/your-project
orkie
```

On first interactive run without `.orkie/config.yaml`, Orkie can offer a default scaffold. The process prints a loopback dashboard URL (default `http://127.0.0.1:8765/`) and polls until you stop it.

**User and operator guides:** [`docs/`](docs/) — [getting started](docs/getting-started.md), [configuration](docs/configuration.md), [operation](docs/operation.md).

## Requirements

- Python 3.11+
- Unix-like host (macOS/Linux) for the process lock
- `git` on `PATH`
- `GITHUB_TOKEN` in the environment (never stored under `.orkie/`)

## Specs and contributors

| Layer | Where | What |
|-------|--------|------|
| User / operator docs | [`docs/`](docs/) | Install, configure, run |
| Product behavior | [`spec/feature/`](spec/feature/) | Stories, acceptance criteria, vocabulary |
| Architecture decisions | [`spec/adr/`](spec/adr/) | Process model, stack, locked flows |
| Implementable design | [`spec/design/`](spec/design/) | Components, sequences, data, UI, config shape |
| Live acceptance | [`spec/testing/`](spec/testing/) | Out-of-band integrated checks |
| Agent contributors | [`AGENTS.md`](AGENTS.md) | How to change this repo |

Offline unit tests: [`tests/`](tests/). Tech stack: [ADR 002](spec/adr/002-2-tech-stack-and-dependencies.md).

## License

[Apache License 2.0](LICENSE)
