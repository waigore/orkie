# Coding conventions

| Features | ADRs |
|----------|------|
| [01](../feature/01-project-bootstrap-and-config.md)–[08](../feature/08-cli-and-dashboard.md) | [001](../adr/001-2-process-model-and-module-layout.md), [002](../adr/002-2-tech-stack-and-dependencies.md) |

Normative rules for the `orkie` package. Features own behavior. ADRs own the process model, the module map, the libraries, and the test locks. [components.md](components.md), [sequences.md](sequences.md), [data.md](data.md), [ui.md](ui.md), and [config.md](config.md) own signatures, schemas, and flows. This file owns how that code is written.

A signature or sequence in those documents wins over a style note here. These conventions add no dependency, knob, product behavior, or import path beyond the ADR 001 module names. Stack, coverage, and fake boundaries stay in [ADR 002](../adr/002-2-tech-stack-and-dependencies.md).

## Goals

Write code that is composable, modular, layered, testable, and readable, with control flow visible in the source.

- **Composable.** A decision is a function from values to a value. A procedure calls those functions in the order the sequence already locks, then performs one kind of effect.
- **Modular.** Each ADR 001 module owns one reason to change. Cross-module talk uses the frozen values and protocols in [components.md](components.md).
- **Layered.** Imports point the same way as [ADR 001](../adr/001-2-process-model-and-module-layout.md). Inside a module, pure functions sit above the effectful procedure that calls them.
- **Testable.** Policy is tested by calling a pure function with dataclasses. Effects are tested at the seams ADR 002 already names.
- **Readable.** A reader can recover the bootstrap order and the poll-cycle order by reading one straight-line function each.
- **Static.** Behavior is named functions, `match` on closed sets, and frozen dataclasses. The source lists every branch.

## Module layout

ADR 001 names are the public import paths. `orkie.connectors` and `orkie.acp` are packages because design already gives them a fake module. `orkie.orchestration` is a package so the cycle procedure imports pure decisions without going through an effect. Every other ADR 001 unit is one module. Add no further package and no plugin module.

```text
orkie/__init__.py                  # __version__ only
orkie/__main__.py                  # calls orkie.cli.main
orkie/cli.py
orkie/config.py
orkie/state.py
orkie/intake.py
orkie/worktree.py
orkie/dashboard.py
orkie/templates/                   # Jinja2 HTML (package data)
orkie/templates/base.html
orkie/templates/index.html
orkie/templates/agents.html
orkie/templates/issues.html
orkie/templates/partials/
orkie/static/                      # Packaged assets served at /static/ (package data)
orkie/static/dashboard.css
orkie/orchestration/__init__.py    # Orchestrator and the cycle procedure
orkie/orchestration/decide.py      # pure claim, cap, strike, and babysitter decisions
orkie/connectors/types.py         # Issue, PullRequest, OwnerRepo, errors, Privilege
orkie/connectors/__init__.py       # Connector, resolve, build; re-exports types
orkie/connectors/github.py         # urllib client
orkie/connectors/fake.py
orkie/acp/__init__.py              # AcpClient, SessionHandle, AcpError, re-exports
orkie/acp/framing.py               # pure JSON-RPC encode/decode and permission choice
orkie/acp/stdio.py                 # subprocess client
orkie/acp/fake.py
```

`orkie/__init__.py` exports `__version__` only. Callers import the module that defines a name. `connectors/__init__.py` and `acp/__init__.py` are the public surfaces from [components.md](components.md); each sets `__all__` to those names. `github`, `stdio`, and `fake` are imported by the composing module or by tests, not by a registry.

## Import direction

Imports are static, at the top of the file, and point inward. No import cycle.

| Module | May import |
|--------|------------|
| `cli` | `config`, `state`, `connectors`, `worktree`, `intake`, `orchestration`, `dashboard`, `acp` (construct the stdio client and store it on the context) |
| `dashboard` | `state`, `orchestration`, `connectors.types` for display |
| `orchestration` | `config`, `state`, `connectors.types`, `Connector`, `intake` result types, `acp` protocol and handle, `worktree` |
| `intake` | `config`, `state`, `connectors.types`, `Connector` |
| `acp` | stdlib, plus the log callback passed into `spawn` |
| `worktree` | stdlib only |
| `connectors` | `connectors.types`. `__init__.py` also imports `config` for `build_connector` and `required_privileges` |
| `config` | `connectors.types` (`Issue`, `PullRequest`) for `substitute_prompt` |
| `state` | stdlib only |

`config` imports `orkie.connectors.types` and does not import `orkie.connectors`. That is what keeps `build_connector(config: Config)` from forming a cycle. `github.py` and `fake.py` do not import `config`.

`orchestration` and `intake` do not import `orkie.connectors.github`, `urllib`, or `orkie.acp.stdio`. `dashboard` does not import `acp` or `github`. `acp` does not import `orchestration`, `intake`, `connectors`, or `worktree`. `state` does not import a policy module. No module imports `cli`.

GitHub payloads and PyYAML values stop at the module that reads them. What leaves `connectors.github` is an `Issue`, a `PullRequest`, an `OwnerRepo`, or a `ConnectorError`. What leaves `config` is a frozen `Config`. What leaves `acp.framing` is a frozen message or a chosen permission option.

## Decision then procedure

Every module is two layers.

1. **Decisions** take frozen values and return frozen values. They do not read the clock, the environment, the filesystem, the network, or a thread. They do not mutate their arguments.
2. **Procedures** call decisions in the locked order, then perform the effects that belong to that module. A procedure does not take a policy callback.

The poll cycle, bootstrap, shutdown, permission grants, and claim math stay `if` / `match` over those returned values. They are not a list of handlers.

`run_cycle` reads as the nine ADR 007 steps: each step is one named call, and the issue-fetch failure branch is an `if` that skips steps 4–7 and still runs step 3. `run_bootstrap` reads as the twelve ADR 003 steps in that order. `shutdown` reads as the normal or graceful sequence from [sequences.md](sequences.md). The step body can call helpers. The order stays in the one procedure.

### Pure decisions

These functions are public so tests call them directly. Names and inputs are normative. The owning feature and ADR stay the behavior.

```python
def eligible_issue(issue: Issue, issue_labels: list[str]) -> bool: ...

def diff_intake(previous: list[SnapshotIssue], current: list[Issue]) -> IntakeDelta: ...

def agent_matches(agent: AgentConfig, issue: Issue) -> bool: ...

def claim_still_applies(
    claim: ClaimRecord, intake: list[Issue], agents: list[AgentConfig]
) -> bool: ...

def cap_room(
    agent: AgentConfig,
    working_issue_sessions: list[SessionRecord],
    *,
    global_max: int,
) -> int: ...

def blocked_by_spawn_failures(
    failures: list[SpawnFailureRecord],
    *,
    issue_number: int | None = None,
    pr_number: int | None = None,
) -> bool: ...

def plan_fulfillment(
    claims: list[ClaimRecord],
    intake: list[Issue],
    agents: list[AgentConfig],
    working_issue_sessions: list[SessionRecord],
    failures: list[SpawnFailureRecord],
    *,
    global_max: int,
) -> list[SpawnWork]: ...

def plan_new_claims(
    intake: list[Issue],
    claims: list[ClaimRecord],
    agents: list[AgentConfig],
    working_issue_sessions: list[SessionRecord],
    failures: list[SpawnFailureRecord],
    *,
    global_max: int,
) -> list[SpawnWork]: ...

def plan_exits(
    sessions: list[SessionRecord],
    *,
    alive_ids: set[str],
    shutdown_started: bool,
) -> list[ExitWork]: ...

def select_babysitter(
    pull_requests: list[PullRequest],
    failures: list[SpawnFailureRecord],
    *,
    babysitter_working: bool,
) -> PullRequest | None: ...

def record_spawn_failure(
    failures: list[SpawnFailureRecord],
    *,
    agent_id: str,
    agent_name: str,
    issue_number: int | None,
    pr_number: int | None,
    error: str,
    at: str,
) -> StrikeUpdate: ...

def clear_spawn_failures(
    failures: list[SpawnFailureRecord],
    *,
    issue_number: int | None = None,
    pr_number: int | None = None,
) -> list[SpawnFailureRecord]: ...

def choose_permission_option(options: list[PermissionOption]) -> PermissionOption: ...
```

`substitute_prompt` stays the signature in [components.md](components.md). `eligible_issue` and `diff_intake` live in `intake`. `choose_permission_option` lives in `acp.framing`. The rest live in `orchestration.decide`.

`SpawnWork`, `ExitWork`, `StrikeUpdate`, and `PermissionOption` are frozen dataclasses. They carry records and flags. They do not carry callables.

| Value | Fields |
|-------|--------|
| `SpawnWork` | `issue`, `agent`, `claim` (`ClaimRecord` when the claim already exists, otherwise `None` and the procedure writes it) |
| `ExitWork` | `session_id`, `drop_claim`, `issue_number`, `pr_number`, `worktree_path` |
| `StrikeUpdate` | `failures`, `drop_claim`, `warn` |
| `PermissionOption` | `option_id`, `kind` |

`plan_fulfillment` and `plan_new_claims` return candidates in the order ADR 007 walks them. The procedure walks that list, stops when `cap_room` is 0, and keeps walking after a spawn that does not occupy a slot. `plan_exits` receives session ids that have already exited. The procedure is what calls `AcpClient.is_alive`. `record_spawn_failure` assigns the next attempt for that issue or PR. The procedure passes the timestamp and the redacted error.

`choose_permission_option` uses the grant order in [components.md](components.md): `allow_always`, else `allow_once`, else the first kind that is neither `reject_once` nor `reject_always`, else the first option. It does not return `cancelled`. An empty option list raises `AcpError`.

Clock reads and `uuid.uuid4()` happen in the procedure, once per record or spawn. The resulting timestamp string or session id is an argument to the decision when the decision needs it. JSON writers receive the timestamp; they do not call `datetime.now`.

## Static control flow

Closed sets use `match` or a plain `if` chain with a final exhaustive arm. `typing.assert_never` on that arm is the exhaustiveness check ADR 002 already allows omitting from coverage.

Use `match` for trigger type, shutdown mode, privilege, intake outcome, JSON-RPC method, ACP permission kind, and connector error class. The arms call named functions. They do not look up a callable in a dict.

JSON-RPC methods Orkie sends are named functions (`initialize`, `session_new`, `session_prompt`, `session_cancel`, `session_delete`), each building one frozen request. Inbound dispatch is a `match` on `method` in the reader thread. An unknown method is ignored after a redacted log line. Orkie does not resolve methods with `getattr`.

Dashboard routes are an `if` chain on `(method, path)` inside one handler function that returns `(status, body_or_bytes, redirect, content_type)`. The HTML routes and control POSTs are those in [components.md](components.md); `GET /static/<path>` is an additional branch that reads package data. The `ThreadingHTTPServer` subclass is an adapter that calls that function.

Config and state loaders read named keys. Each key is checked with `isinstance` and then stored on a dataclass. There is no schema object, no field-name dispatch, and no model metaclass.

Prompt substitution replaces the feature-01 token list with `str.replace` for each token. It does not use `string.Template`, `str.format` with a mapping, or a template engine. Issue sessions pass empty strings for PR tokens. Babysitter sessions pass empty strings for issue tokens.

GitHub list and probe URLs are built by named functions that return the URL string. Pagination is a loop in the list function that follows `Link` until it is absent. A failed page raises; the function does not return a partial list.

### Values that stay data

| Boundary | Python |
|----------|--------|
| Config, claims, sessions, snapshot, spawn failures, issues, pull requests | `@dataclass(frozen=True, slots=True)` |
| Live ACP handle | the mutable dataclass in components (it owns a `Popen` and a thread) |
| Privileges | `enum.Enum` already in components |
| Trigger type, shutdown mode | `Literal` already in components |
| JSON object before validation | `object`, narrowed with `isinstance` before field access |
| Errors | the module exception (`ConfigError`, `ConnectorError` and its subclasses, `AcpError`, `WorktreeError`) |

`SessionHandle` stays mutable because the design stores process state on it. Do not copy that pattern onto records. New value types are frozen.

Absent data uses `None` or an empty list, and only where the design already uses it (missing snapshot, unbound issue or PR, no babysitter candidate). A failed operation raises the module exception. It does not return `None` or a status string.

### Parsing

- YAML enters through `yaml.safe_load` and goes straight into the config validator. JSON state enters through `json.loads` and goes straight into that document's loader.
- Config rejects unknown fields ([config.md](config.md)). State loaders reject an unknown key, a missing required key, or a wrong JSON type as a corrupt file, and bootstrap names that file ([data.md](data.md)).
- GitHub response objects and inbound ACP objects are open. Parsers read the keys Orkie uses, check those types, and ignore every other key.
- Each loader returns the dataclass or raises. Callers do not re-check the raw dict.
- Writers build a dict with explicit keys, then `json.dumps`. The scaffold writer writes the feature-01 document bytes. It does not dump the `Config` object.

Five small checkers (`dict`, `str`, `int`, `bool`, `list`) may exist inside `config` and again inside `state`. They stay in that module. A shared parsing package is a module the layout does not have.

### Effects

Each effect has one home.

| Effect | Home |
|--------|------|
| `os.environ` for `GITHUB_TOKEN` | `cli`, which passes the string on |
| Process lock, JSON replace, agent-log append | `state` |
| GitHub HTTP | `connectors.github` |
| `git` CLI | `worktree` |
| Agent subprocess and JSON-RPC stdio | `acp.stdio` |
| Loopback HTTP | `dashboard` |
| Operator prompts and stderr warnings | `cli` or the procedure the feature names (three-strike warning) |

Library modules take the token, paths, and clock result as arguments. `StateStore` already receives `github_token` and redacts in `append_log`. Error text that can contain a child environment is redacted with that same function before it is stored or raised. `AcpError` messages are redacted.

Timestamps are UTC ISO-8601 with a `Z` suffix, produced by one function in `state`. Every writer calls it.

### Constants

Locked numbers and sentences are module-level constants next to the procedure that uses them. The value is the feature or design text.

| Constant | Where |
|----------|--------|
| Feature-01 scaffold document | `config` |
| Wrap-up prompt sentence | `orchestration` |
| 5 second process-exit wait | `acp` |
| 20 second wrap-up wait | `orchestration` or `cli` shutdown |
| 60 second handshake timeout | `acp` |
| 1 second poll-wait slice | `cli` |
| GitHub API base, Accept header, API version | `connectors.github` |

## What stays out of the source

The following are out of the v1 tree. A behavior that seems to need one of them is written as a named function instead, or the design is updated first.

- `eval`, `exec`, `compile`, `importlib`, `__import__`, entry points, and package walking
- `getattr`, `setattr`, `hasattr`, or `vars` used to dispatch or to read fields
- Metaclasses, runtime type construction, and decorator registries
- A dict or list of callables used as a policy table, middleware, hook list, or event bus
- `functools.partial` and lambdas as stored behavior
- `*args` and `**kwargs` on functions this repo defines
- New `Callable[..., None]` parameters. The `spawn` log callback is the one design already requires; annotate it with the `append_log` parameters from [components.md](components.md)
- New `Protocol`s beyond `Connector` and `AcpClient`, except a private frozen-value helper is not a protocol. Do not add an ABC hierarchy
- `unittest.mock` in production modules, and in tests outside the seams ADR 002 names (`urlopen` in `connectors.github` tests, TTY in `cli` tests)
- Mutable module globals. The lock FD lives on `StateStore`. The session table lives on the orchestration context
- The `logging` package and its handler tree. Operator text goes to stderr. Agent text goes through `StateStore.append_log`
- A second concurrency runtime. Threads are the dashboard thread and one reader thread per ACP child, as ADR 001 describes
- Reading or writing a GitHub type, a raw YAML dict, or a raw JSON-RPC dict from `orchestration` or `intake`

`patch` of `urlopen` and of stdin/stdout stays available in the tests ADR 002 names. Other tests build the fake or pass a temporary directory.

## Composition rules

- Prefer three similar lines to a helper whose only job is to hide a mode flag the features do not have.
- The connector protocol exists so intake, orchestration, and tests share one sync surface, and so `connectors.fake` can implement it. v1 constructs the GitHub client from `build_connector`. Do not add a connector loader.
- Agent roles stay config records. Orchestration treats every agent through `AgentConfig` and `agent_matches`. There is no role class.
- Do not parameterize cap math, permission choice, shutdown timing, or poll order. Those are fixed by the features.
- Constructor arguments are the collaborating values: config, store, connector, ACP client, worktree service, shutdown event. Tests pass fakes there. Functions do not reach for a global.
- A function that only sequences two calls in one module can stay inline in the procedure when naming it would not describe a decision from the table above.

## Readability

- Type every function, including private helpers. Use Python 3.11 forms: `list[str]`, `str | None`, `Literal`. Public annotations match [components.md](components.md).
- Import order is stdlib, then third party (`yaml`), then `orkie`. No wildcard imports. No alias that hides the defining module.
- Use double quotes, matching the samples in the design docs. PEP 8 layout otherwise.
- One statement per line. A nested conditional expression becomes an `if` block. A long boolean becomes a named local whose name is the predicate (`claim_applies`, `globally_full`).
- Guard clauses return or continue before the main path: shutting down, missing file, empty token, session already gone.
- Names use the [vocabulary](../feature/vocabulary.md): claim, intake issue, working session, spawn failure, selectable pull request. Avoid names that restate a mechanism (`manager`, `handler`, `processor`) when a vocabulary word exists.
- Comments record a constraint the types cannot: the lock file is rewritten on the held FD, the scaffold is exact bytes, session files are deleted without parsing, a reject-only permission is still a grant. Comments do not restate the feature.
- Format operator-visible sentences in one function per sentence family (config field path, privilege gap, three-strike warning, permission-grant log line) so the wording has one source.

## Dashboard and HTML

`dashboard.py` builds a frozen view model from the store and the in-memory session table, then renders a named Jinja2 template to HTML. Templates live under `orkie/templates/` and use a shared `base.html` for nav, intake banner, and the stylesheet link. Autoescape is on; page builders do not concatenate HTML or call `html.escape` for template values. Tests call the view-model function and the render function with dataclasses. The server adapter binds `127.0.0.1`, serves HTML or static bytes, and posts controls.

Control handling is one function: shutdown in progress returns 503; otherwise it takes the cycle lock, calls `interrupt_session` or `kill_session`, and returns the redirect. Unknown session returns 404.

Static files under `orkie/static/` are served only via `GET /static/<path>` with the resolved path constrained to that directory.

## Tests

ADR 002 still owns layout, markers, coverage, and the fake modules. The extra rules below keep those tests on the seams.

- A decision-table test calls one pure function, builds frozen inputs, and asserts the frozen result. It does not create a temporary directory, a thread, or a fake process.
- A cycle test builds `Orchestrator` with the fake connector, the fake ACP client, and a stub worktree, calls `run_cycle` once, and asserts claims, sessions, and spawn failures.
- A state test uses `tmp_path`. A GitHub test patches `urlopen` or feeds response bytes to the parser functions in `connectors.github`. An ACP framing test calls `acp.framing` with byte strings and option lists. A worktree integration test is marked `integration` and uses a temporary git repository.
- Fakes are the classes in `connectors.fake` and `acp.fake`. They store the lists and flags the test sets. They are not generated mocks.
- One behavior per test. The name states the behavior (`test_attempt_three_drops_the_claim`). Assert the domain result. Assert log or stderr text only when a feature specifies the words.
- `pytest.mark.parametrize` is for a closed table of inputs, such as the permission-option order or the privilege-probe order. It is not a second test runner.
- No network except loopback dashboard tests. No sleep. `wait_poll_interval` returns because the shutdown event is set.
- Coverage gates and the soft 90% guidance stay as ADR 002 wrote them. Pure decision tests are how orchestration, intake, config, and state reach that guidance without mocking private branches.

## Checklist

Before adding code, confirm:

1. The import is on the allowed edge, and no GitHub or YAML dict crosses it.
2. The new behavior is either a pure function in the decision table or a straight-line step in an existing procedure.
3. The branch is a `match` or `if` on a closed set, written out in the file.
4. The effect stays in the module that already owns that I/O.
5. A test calls the decision, or drives one cycle through the ADR 002 fakes, and fails if the behavior is removed.
