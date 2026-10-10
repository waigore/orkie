# ADR 005: Connector interface and GitHub client

## Status

Superseded by [005-1](../005-1-connector-interface-and-github-client.md).

## Context

Feature [03](../../feature/03-connector-interface-and-github.md) requires an abstract connector so intake and orchestration never embed GitHub HTTP. Features [06](../../feature/06-work-intake-and-issue-monitoring.md) and [07](../../feature/07-pr-babysitter.md) consume issue and PR reads. Design needs a typed sync interface, a GitHub implementation, and privilege probing without SDK leakage.

## Decision

### Interface shape

`orkie.connectors` defines a `typing.Protocol` named `Connector` (runtime-checkable optional) with **sync** methods and plain dataclass / TypedDict results (no PyGithub types).

Minimum surface for v1:

| Method | Purpose |
|--------|---------|
| `repository_id() -> OwnerRepo` | Resolved `owner`, `name` |
| `list_open_issues() -> list[Issue]` | Open non-PR issues: number, title, body, url, state, labels |
| `list_open_pull_requests() -> list[PullRequest]` | Open PRs: number, title, url, head, base, draft, mergeable_state |
| `ensure_label(name: str) -> None` | Create label if missing |
| `add_issue_label(number: int, label: str) -> None` | Claim |
| `remove_issue_label(number: int, label: str) -> None` | Release claim |
| `probe_privileges(required: set[Privilege]) -> ProbeResult` | Required vs warn-only gaps |

Issue comments are out of scope (no read/write comment APIs in v1).

`mergeable_state` is the string returned by GitHub (e.g. `clean`, `dirty`, `blocked`, `unknown`, …) passed through to babysitter selection and `__PR_MERGE_STATE__`.

### GitHub implementation

- Module: `orkie.connectors.github`.
- Auth: `Authorization: Bearer` from `GITHUB_TOKEN` (never from `.orkie/`).
- Transport: stdlib `urllib.request` ([002](002-tech-stack-and-dependencies.md)).
- API: GitHub REST v3; `Accept: application/vnd.github+json`; paginate with `Link` headers. A partial multi-page fetch raises and must not be treated as a complete list ([009](009-intake-poll-and-delta.md)).
- Open issues: request open issues and exclude PRs (`pull_request` key present) client-side, or use the issues API with filters that avoid closed history dumps. Do not enumerate closed issues for intake.
- Factory: `build_connector(config) -> Connector` returns GitHub when `connector.type == "github"`; other types fail validation at config load.

### Privilege probing

Map feature-03 required privileges to concrete **read-only** API checks (e.g. GET repo, GET issues, inspect token scopes). Probes never mutate; claim-label creation happens only at the ensure step in bootstrap ([003](003-config-load-and-bootstrap-sequence.md) step 10). Interactive vs non-interactive handling stays in bootstrap ([003](003-config-load-and-bootstrap-sequence.md)); the connector only reports gaps. `Privilege` and `ProbeResult` shapes are left to component design.

### Fakes

`orkie.connectors.fake` (or test package) implements `Connector` for offline pytest.

## Reasoning

- Protocol + dataclasses keep core free of GitHub SDK types and match AGENTS.md.
- Sync API fits the sync main loop ([001](001-process-model-and-module-layout.md)).
- urllib is enough for Orkie's poll-rate traffic and removes an HTTP dependency.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| PyGithub / ghapi in orchestration | Leaks SDK types; harder fakes |
| Async connector | Forces asyncio through intake/orchestration |
| GraphQL-only client | REST covers the v1 field set with simpler pagination |
| `gh` CLI subprocess as the connector | Fragile parsing; poorer privilege errors; extra dependency on `gh` |
| Comment APIs in v1 | Explicitly out of feature 03 |

## Consequences for design

- Intake and orchestration import only `Connector` and shared model types.
- Babysitter PR selection uses `list_open_pull_requests` only ([010](010-pr-babysitter-lifecycle.md)).
- Rate-limit and network errors surface as connector exceptions; intake preserves last good snapshot.
- Future hosts implement `Connector` without changing orchestration.
