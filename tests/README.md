# Offline unit tests

Pytest suite for the installable `orkie` package. This is the default CI suite locked in [ADR 002-1](../spec/adr/002-1-tech-stack-and-dependencies.md). Live GitHub acceptance lives under [`spec/testing/`](../spec/testing/) and is out of band.

## Layout

Mirror `orkie.*` packages under `tests/`:

| Package | Tests |
|---------|-------|
| `orkie` (root / version) | `tests/` (e.g. `test_version.py`) |
| `orkie.cli` | `tests/cli/` |
| `orkie.config` | `tests/config/` |
| `orkie.state` | `tests/state/` |
| `orkie.connectors` / `github` / `fake` | `tests/connectors/` |
| `orkie.acp` / `fake` | `tests/acp/` |
| `orkie.intake` | `tests/intake/` |
| `orkie.orchestration` | `tests/orchestration/` |
| `orkie.worktree` | `tests/worktree/` |
| `orkie.dashboard` | `tests/dashboard/` |

Name files `test_*.py`. Prefer one behavior per test name (Arrange–Act–Assert).

## Doubles and hermetic rules

- Inject fakes at the `Connector` and `AcpClient` protocols (`orkie.connectors.fake`, `orkie.acp.fake`).
- Do not mock private urllib or ACP framing internals from orchestration tests.
- Use injectable `tmp_path` / state root for state I/O.
- Stub `orkie.worktree` from orchestration unit tests; optional `@pytest.mark.integration` may use a temp git repo.
- No network except loopback dashboard tests on `127.0.0.1`.
- Do not call live GitHub or a real ACP agent here.

## Markers

```python
@pytest.mark.integration  # temp-git or real-subprocess; excluded from default CI
```

Default / CI suite stays offline: `pytest -m "not integration"`.

## Local commands

```bash
python -m pip install -e ".[dev]"
pytest --cov=orkie --cov-report=term-missing --cov-fail-under=80
```

Overall line coverage of `orkie/` must stay ≥ 80%. Prefer ≥ 90% on `orchestration`, `intake`, `config`, and `state` (soft guidance, not a second CI gate).
