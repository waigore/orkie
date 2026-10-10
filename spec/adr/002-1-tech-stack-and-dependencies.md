# ADR 002: Tech stack and dependencies

## Status

Accepted

Supersedes [002](superseded/002-tech-stack-and-dependencies.md).

## Context

Orkie prefers the standard library and allows a dependency only when stdlib cannot do the job cleanly. Features require YAML config, GitHub HTTP, ACP over stdio, git worktrees, a loopback dashboard, and pytest-backed offline tests. Component design needs an approved stack and an explicit deny list so implementers do not pull frameworks ad hoc. Coding conventions for Python live here (not in [AGENTS.md](../../AGENTS.md)).

## Decision

### Runtime

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ (`tomllib` not required for v1 config) |
| Typing | Type hints on public functions and on the connector interface |
| Packaging | Standard installable project (`pyproject.toml`); console script `orkie` |
| Config YAML | **PyYAML** `yaml.safe_load` for reading. The default scaffold is the exact document in feature 01, written as that text |
| GitHub HTTP | **stdlib** `urllib.request` + `json` against GitHub REST API v3 |
| Git | **stdlib** `subprocess` invoking the `git` CLI on PATH |
| ACP transport | **stdlib** `subprocess` + stdio; Orkie-owned JSON-RPC framing in `orkie.acp` (no agent vendor SDK) |
| CLI | **stdlib** `argparse` |
| Dashboard HTTP | **stdlib** `http.server` (`ThreadingHTTPServer`) bound to `127.0.0.1` |
| HTML | Stdlib string templates / hand-built HTML with `html.escape`; no SPA framework |
| Concurrency | **stdlib** `threading`; sync orchestration ([001-1](001-1-process-model-and-module-layout.md)) |
| Time / paths | Stdlib `pathlib`, `time`, `datetime` (UTC ISO-8601 in state files) |
| Secrets | Environment only (`GITHUB_TOKEN`); never written to `.orkie/` or state logs |

### Test / dev

| Concern | Choice |
|---------|--------|
| Tests | **pytest** once a suite exists |
| Connector / ACP in tests | In-repo fakes; no network, no GitHub account for the default suite |
| Coverage focus | When orchestration or config loading changes, cover the change with an offline test |
| Coverage tooling | Optional later; not required to start the suite |

### Explicitly not used in v1

| Rejected | Reason |
|----------|--------|
| FastAPI / Starlette / Flask / Django | Dashboard is loopback-only and small; stdlib HTTP is enough |
| Click / Typer / fire | argparse covers path + `--port` |
| asyncio / anyio / trio as primary runtime | See [001-1](001-1-process-model-and-module-layout.md) |
| httpx / requests / aiohttp | urllib covers GitHub REST for Orkie's call volume |
| PyGithub / ghapi / PyGitHub | Avoid leaking SDK types into core; thin REST wrapper in `orkie.connectors.github` |
| pydantic / attrs / marshmallow for config | Hand validation against the feature-01 schema keeps one less model layer |
| SQLAlchemy / SQLite as primary state | See [004-1](004-1-local-state-format-and-process-lock.md) |
| Redis / external message bus | Single process owns orchestration |
| Jinja2 / React / Vue dashboard | Unnecessary for two simple views |
| Proprietary OpenCode/Grok Python SDKs | ACP stdio only |
| Shipping a systemd `.service` in-repo | Documented in feature 08 only |
| `yaml.safe_dump` for the default scaffold | A dump does not reproduce the feature-01 document |

### Adding a dependency later

Allowed only when stdlib cannot do the job cleanly. Update this ADR (or supersede it) before adding the package to `pyproject.toml`.

## Reasoning

- YAML has no stdlib parser; PyYAML is the minimal, well-known choice for reading project config.
- The scaffold is a fixed document the operator accepts, so it is stored as that document.
- GitHub needs only a small REST surface (issues, labels, PRs, repo metadata); urllib avoids an HTTP framework.
- ACP is JSON-RPC over stdio; a thin in-tree client matches “any ACP-compatible agent” without vendor lock-in.
- pytest is the suite runner once tests exist; offline fakes keep CI free of GitHub credentials.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Zero third-party deps (hand-rolled YAML) | Fragile and unnecessary |
| Full GitHub SDK | Couples core to SDK types; harder fakes |
| Web framework + Jinja | Overkill for loopback agent/issue views |
| pydantic settings | Feature schema is project YAML, not env-heavy settings |
| Round-tripping the scaffold through PyYAML | Breaks the required document text |

## Consequences for design

- `pyproject.toml` runtime deps: PyYAML only (plus pytest in dev/test extras).
- `orkie.connectors.github` owns URL building, pagination, auth header, and JSON parsing.
- `orkie.acp` owns message framing and method names; document OpenCode and Grok Build command lines only as first-class examples ([006](006-acp-agent-runtime.md)).
- `orkie.config` writes the scaffold from the feature-01 text and reads config with `safe_load`.
- CI and local tests run offline with fakes.
