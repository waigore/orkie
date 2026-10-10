# ADR 005: Connector interface and GitHub client

## Status

Accepted

Supersedes [005-1](superseded/005-1-connector-interface-and-github-client.md).

## Context

Feature [03](../feature/03-connector-interface-and-github.md) requires an abstract connector so intake and orchestration never embed GitHub HTTP. Features [06](../feature/06-work-intake-and-issue-monitoring.md) and [07](../feature/07-pr-babysitter.md) consume issue and PR reads. The connector does not write labels. Design needs a typed sync interface, a GitHub implementation, and a read-only privilege probe without SDK leakage.

## Decision

### Interface shape

`orkie.connectors` defines a `typing.Protocol` named `Connector` with **sync** methods and plain dataclass results (no PyGithub types).

Minimum surface for v1:

| Method | Purpose |
|--------|---------|
| `repository_id() -> OwnerRepo` | Resolved `owner`, `name` |
| `list_open_issues() -> list[Issue]` | Open non-PR issues: number, title, body, url, state, labels |
| `list_open_pull_requests() -> list[PullRequest]` | Open PRs: number, title, url, head, base, draft, mergeable_state |
| `probe_privileges(required: set[Privilege]) -> ProbeResult` | Required vs warn-only gaps |

`Issue` and `PullRequest` are the prompt-substitution inputs ([003-2](003-2-config-load-and-bootstrap-sequence.md)).

Issue comments are out of scope (no read/write comment APIs in v1). Label create, add, and remove are out of scope.

`mergeable_state` is the string returned to babysitter selection and `__PR_MERGE_STATE__` (for example `clean`, `dirty`, `blocked`, `unknown`).

### GitHub implementation

- Module: `orkie.connectors.github`.
- Auth: `Authorization: Bearer` from `GITHUB_TOKEN` (never from `.orkie/`).
- Transport: stdlib `urllib.request` ([002-1](002-1-tech-stack-and-dependencies.md)).
- API: GitHub REST v3; `Accept: application/vnd.github+json`; paginate with `Link` headers. A partial multi-page fetch raises and must not be treated as a complete list ([009-2](009-2-intake-poll-and-delta.md)).
- Open issues: request open issues and exclude PRs (`pull_request` key present) client-side. Do not enumerate closed issues for intake.
- Factory: `build_connector(config) -> Connector` returns GitHub when `connector.type == "github"`; other types fail validation at config load.

### Mergeable state

`list_open_pull_requests` returns a mergeable state the GitHub client has resolved. GitHub computes that state when a pull request is read on its own, and a list payload often has null or `unknown`. The GitHub client resolves those with a per-PR read before returning. If GitHub still has no computed state, the method returns `unknown`. Callers treat `unknown` or missing as not selectable yet ([010-2](010-2-pr-babysitter-lifecycle.md)). Orchestration does not grow its own PR fetch.

### Privilege probing

The probe is read-only. Map feature-03 required privileges to: token present, repository read, open-issue read, and open-PR read when the babysitter is enabled. An empty token is a missing privilege and performs no HTTP request. HTTP 401 or 403 on a required read is a missing privilege (`AuthError`). A rate-limit response is `RateLimitError`, which is a failed fetch during a poll and a probe failure at bootstrap, not a distinct warn-only gap. The v1 warn-only set is empty. Interactive vs non-interactive handling stays in bootstrap ([003-2](003-2-config-load-and-bootstrap-sequence.md)); the connector only reports gaps.

`Privilege` names the required reads. It has no label-create, label-add, or label-remove member.

### Fakes

`orkie.connectors.fake` implements `Connector` for offline pytest. The fake returns `mergeable_state` directly.

## Reasoning

- Protocol + dataclasses keep core free of GitHub SDK types and match AGENTS.md.
- Sync API fits the sync main loop ([001-2](001-2-process-model-and-module-layout.md)).
- urllib is enough for Orkie's poll-rate traffic and removes an HTTP dependency.
- Resolving mergeability inside the GitHub client keeps a single PR method on the interface. A list-only return would leave selectable PRs unknown.
- A read-only probe cannot create repository state while checking that the token can see it.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| PyGithub / ghapi in orchestration | Leaks SDK types; harder fakes |
| Async connector | Forces asyncio through intake/orchestration |
| GraphQL-only client | REST covers the v1 field set with simpler pagination |
| `gh` CLI subprocess as the connector | Fragile parsing; poorer privilege errors; extra dependency on `gh` |
| Comment APIs in v1 | Explicitly out of feature 03 |
| Label write methods on `Connector` | Claims are local. Feature 03 does not write labels |
| A second connector method for one PR | Callers only need the list. Resolution stays inside the GitHub client |
| Trust list `mergeable_state` as computed | The list payload is often unknown, so the babysitter would not select |
| Probe by creating a label | That mutates the repository. The required set is reads |

## Consequences for design

- Intake and orchestration import only `Connector` and shared model types.
- Babysitter PR selection uses `list_open_pull_requests` only ([010-2](010-2-pr-babysitter-lifecycle.md)).
- Rate-limit and network errors surface as connector exceptions; intake preserves the last good snapshot and does not change claims because of a failed fetch.
- Future hosts implement `Connector` without changing orchestration. A host that already knows mergeability returns it from the list method.
