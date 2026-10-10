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
| Concurrency | **stdlib** `threading`; sync orchestration ([001-2](001-2-process-model-and-module-layout.md)) |
| Time / paths | Stdlib `pathlib`, `time`, `datetime` (UTC ISO-8601 in state files) |
| Secrets | Environment only (`GITHUB_TOKEN`); never written to `.orkie/` or state logs |

### Test / dev

| Concern | Choice |
|---------|--------|
| Tests | **pytest** once a suite exists (`dev` / `test` extra in `pyproject.toml`) |
| Coverage tooling | **pytest-cov** + coverage.py |
| Overall coverage gate | **≥ 80%** line coverage of `orkie/`; CI fails below that (`--cov-fail-under=80`) |
| Critical modules (soft) | Prefer **≥ 90%** on `orchestration`, `intake`, `config`, and `state` — not a second hard CI gate |
| Connector / ACP in tests | In-repo fakes (`orkie.connectors.fake`, `orkie.acp.fake`); no network, no GitHub account for the default suite |
| Fake boundaries | Inject at the `Connector` and `AcpClient` protocols. Do not mock private urllib or ACP framing internals from orchestration tests |
| State in tests | Injectable home / `state_root` (temporary directory) |
| Layout | `tests/` mirroring `orkie.*` packages (e.g. `tests/orchestration/`, `tests/intake/`) |
| Markers | `@pytest.mark.integration` for temp-git or real-subprocess cases; default suite stays offline |
| Worktrees in unit tests | Stub `orkie.worktree` from orchestration tests; optional integration tests may use a temp git repo |
| Coverage focus | When orchestration or config loading changes, cover the change with an offline test that fails without the change |
| Coverage omit | Sparingly: `__main__` re-export, pure version string, unreachable `assert_never`-style arms — not business logic |
| Extra pytest plugins | None beyond pytest-cov unless this ADR is updated first |

#### Package test expectations

| Module | Must-cover behaviors (unit) | Doubles |
|--------|----------------------------|---------|
| `config` | Valid load; invalid schema rejects; scaffold exact text; prompt substitution | temp `.orkie/` |
| `state` | Claims, snapshot, sessions, spawn_failures I/O; lock acquire/refuse | `tmp_path` state root |
| `connectors.github` | URL/auth/pagination helpers; error mapping; privilege probe order | patched `urlopen` |
| `intake` | Snapshot delta (`entered` / `left` / `labels_changed`); fetch failure keeps disk snapshot and sets `last_error` | fake connector + temp store |
| `orchestration` | One cycle: claim, cap, spawn success/fail, drop on `left`, babysitter paths, ACP exit reconcile | fake connector, fake ACP, stub worktree |
| `acp` | Framing / request id / permission auto-allow; interrupt/kill sequencing | stdio double or fake client |
| `dashboard` | Handlers; claimed vs unclaimed join | fake orchestration + temp logs |
| `cli` | Interactive vs non-interactive bootstrap; `parse_args`; shutdown mode via flags | fake TTY, fake connector |

#### Test style

- Arrange–Act–Assert; one behavior per test name.
- Assert domain outcomes (claims, sessions, deltas, HTTP status/body) — not log text unless a feature requires operator-visible messages.
- No network except loopback dashboard tests on `127.0.0.1`.
- Default CI command once a suite exists: `pytest --cov=orkie --cov-report=term-missing --cov-fail-under=80`.

### Explicitly not used in v1

| Rejected | Reason |
|----------|--------|
| FastAPI / Starlette / Flask / Django | Dashboard is loopback-only and small; stdlib HTTP is enough |
| Click / Typer / fire | argparse covers path + `--port` |
| asyncio / anyio / trio as primary runtime | See [001-2](001-2-process-model-and-module-layout.md) |
| httpx / requests / aiohttp | urllib covers GitHub REST for Orkie's call volume |
| PyGithub / ghapi / PyGitHub | Avoid leaking SDK types into core; thin REST wrapper in `orkie.connectors.github` |
| pydantic / attrs / marshmallow for config | Hand validation against the feature-01 schema keeps one less model layer |
| SQLAlchemy / SQLite as primary state | See [004-2](004-2-local-state-format-and-process-lock.md) |
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
- An 80% overall line-coverage gate is enough for a sync orchestrator with clear fake seams; soft 90% on orchestration, intake, config, and state steers effort to the highest-risk modules without a second hard threshold.
- pytest-cov is the smallest coverage tool that fits the existing pytest choice; first-class `connectors.fake` and `acp.fake` modules avoid ad-hoc doubles per test file.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Zero third-party deps (hand-rolled YAML) | Fragile and unnecessary |
| Full GitHub SDK | Couples core to SDK types; harder fakes |
| Web framework + Jinja | Overkill for loopback agent/issue views |
| pydantic settings | Feature schema is project YAML, not env-heavy settings |
| Round-tripping the scaffold through PyYAML | Breaks the required document text |
| No coverage gate / coverage tooling forever optional | Lets critical paths land untested; 80% is a practical CI bar for this layout |
| Hard ≥90% on every package | Overfits urllib edge cases and signal/`os.kill` paths; soft guidance on critical modules is enough |

## Consequences for design

- `pyproject.toml` runtime deps: PyYAML only. Dev/test extras: **pytest** and **pytest-cov**.
- `orkie.connectors.github` owns URL building, pagination, auth header, and JSON parsing.
- `orkie.acp` owns message framing and method names; document OpenCode and Grok Build command lines only as first-class examples ([006-1](006-1-acp-agent-runtime.md)).
- `orkie.config` writes the scaffold from the feature-01 text and reads config with `safe_load`.
- `orkie.connectors.fake` and `orkie.acp.fake` are first-class modules for the offline suite ([001-2](001-2-process-model-and-module-layout.md), [components](../design/components.md)).
- CI and local tests run offline with fakes; CI enforces ≥80% line coverage of `orkie/` once the suite exists.
- Test layout and markers follow the Test / dev section above; integration cases stay hermetic (temp git only, no GitHub).
