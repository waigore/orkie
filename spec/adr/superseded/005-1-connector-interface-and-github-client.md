## Status

Superseded by [005-2](../005-2-connector-interface-and-github-client.md).

Supersedes [005](005-connector-interface-and-github-client.md).

## Context

Feature [03](../feature/03-connector-interface-and-github.md) requires an abstract connector so intake and orchestration never embed GitHub HTTP. Features [06](../feature/06-work-intake-and-issue-monitoring.md) and [07](../feature/07-pr-babysitter.md) consume issue and PR reads. Design needs a typed sync interface, a GitHub implementation, and privilege probing without SDK leakage.

## Decision

### Interface shape

`orkie.connectors` defines a `typing.Protocol` named `Connector` with **sync** methods and plain dataclass results (no PyGithub types).

Minimum surface for v1:

| Method | Purpose |
|--------|---------|
| `repository_id() -> OwnerRepo` | Resolved `owner`, `name` |
| `list_open_issues() -> list[Issue]` | Open non-PR issues: number, title, body, url, state, labels |
| `list_open_pull_requests() -> list[PullRequest]` | Open PRs: number, title, url, head, base, draft, mergeable_state |
| `ensure_label(name: str) -> None` | Create label if missing |
| `add_issue_label(number: int, label: str) -> None` | Apply the claim label |
| `remove_issue_label(number: int, label: str) -> None` | Remove the claim label |
| `probe_privileges(required: set[Privilege]) -> ProbeResult` | Required vs warn-only gaps |

Issue comments are out of scope (no read/write comment APIs in v1).

`mergeable_state` is the string returned to babysitter selection and `__PR_MERGE_STATE__` (for example `clean`, `dirty`, `blocked`, `unknown`).

### GitHub implementation

- Module: `orkie.connectors.github`.
- Auth: `Authorization: Bearer` from `GITHUB_TOKEN` (never from `.orkie/`).
- Transport: stdlib `urllib.request` ([002-1](../002-1-tech-stack-and-dependencies.md)).
- API: GitHub REST v3; `Accept: application/vnd.github+json`; paginate with `Link` headers. A partial multi-page fetch raises and must not be treated as a complete list ([009-1](009-1-intake-poll-and-delta.md)).
- Open issues: request open issues and exclude PRs (`pull_request` key present) client-side. Do not enumerate closed issues for intake.
- Factory: `build_connector(config) -> Connector` returns GitHub when `connector.type == "github"`; other types fail validation at config load.

### Mergeable state

`list_open_pull_requests` returns a mergeable state the GitHub client has resolved. GitHub computes that state when a pull request is read on its own, and a list payload often has null or `unknown`. The GitHub client resolves those with a per-PR read before returning. If GitHub still has no computed state, the method returns `unknown`. Callers treat `unknown` or missing as not selectable yet ([010-1](010-1-pr-babysitter-lifecycle.md)). Orchestration does not grow its own PR fetch.

### Privilege probing

Map feature-03 required privileges to concrete checks: repository read, open-issue read, label create when the claim label is missing, label add and remove, and open-PR read when the babysitter is enabled. The v1 probe list is that required set. Interactive vs non-interactive handling stays in bootstrap ([003-1](003-1-config-load-and-bootstrap-sequence.md)); the connector only reports gaps.

### Fakes

`orkie.connectors.fake` implements `Connector` for offline pytest. The fake returns `mergeable_state` directly.

## Reasoning

- Protocol + dataclasses keep core free of GitHub SDK types and match AGENTS.md.
- Sync API fits the sync main loop ([001-1](001-1-process-model-and-module-layout.md)).
- urllib is enough for Orkie's poll-rate traffic and removes an HTTP dependency.
- Resolving mergeability inside the GitHub client keeps a single PR method on the interface. A list-only return would leave selectable PRs unknown.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| PyGithub / ghapi in orchestration | Leaks SDK types; harder fakes |
| Async connector | Forces asyncio through intake/orchestration |
| GraphQL-only client | REST covers the v1 field set with simpler pagination |
| `gh` CLI subprocess as the connector | Fragile parsing; poorer privilege errors; extra dependency on `gh` |
| Comment APIs in v1 | Explicitly out of feature 03 |
| A second connector method for one PR | Callers only need the list. Resolution stays inside the GitHub client |
| Trust list `mergeable_state` as computed | The list payload is often unknown, so the babysitter would not select |

## Consequences for design

- Intake and orchestration import only `Connector` and shared model types.
- Babysitter PR selection uses `list_open_pull_requests` only ([010-1](010-1-pr-babysitter-lifecycle.md)).
- Rate-limit and network errors surface as connector exceptions; intake preserves the last good snapshot.
- Future hosts implement `Connector` without changing orchestration. A host that already knows mergeability returns it from the list method.
