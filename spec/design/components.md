# Components

| Features | ADRs |
|----------|------|
| [01](../feature/01-project-bootstrap-and-config.md)–[08](../feature/08-cli-and-dashboard.md) | [001](../adr/001-2-process-model-and-module-layout.md)–[012](../adr/012-3-dashboard-stack-and-control-api.md) |

Package map and process model are locked by [ADR 001](../adr/001-2-process-model-and-module-layout.md). This document defines purpose, scope, interfaces, and lifecycle for each package so implementation does not invent boundaries.

## Shared process objects

One OS process per resolved `owner/name`. After successful bootstrap, these live for the process lifetime:

| Object | Type / location | Owner |
|--------|-----------------|-------|
| Loaded config | Immutable in-memory object from `orkie.config` | `cli` after bootstrap |
| Connector | `Connector` instance | `cli` constructs; intake/orchestration use |
| State store | `orkie.state.StateStore` | Shared; main thread writes; dashboard reads |
| Live session table | `dict[str, SessionHandle]` keyed by Orkie `session_id` | `orchestration` / `acp` |
| `shutdown_event` | `threading.Event` | `cli` sets; loop and dashboard observe |
| `immediate_kill` | `threading.Event` or bool flag | Second signal during the shutdown prompt or the graceful 20 second wait |
| Cycle lock | `threading.Lock` | Main holds for whole poll cycle; dashboard takes for one interrupt/kill |
| Start checkout | commit sha plus branch name or `"detached"` | `worktree.resolve_base` at bootstrap for initial dashboard value; refreshed after each successful sync in `worktree.create` |
| Last intake error | `str \| None` in memory | `intake` writes; dashboard reads |
| Effective dashboard port | `int` | CLI `--port` or config |

Dependency direction (do not invert):

```text
cli → bootstrap (config, state, connectors, worktree)
    → loop (intake → orchestration → acp / worktree)
dashboard → state (read), orchestration (controls only)
```

---

## `orkie.cli`

**Features:** [01](../feature/01-project-bootstrap-and-config.md), [08](../feature/08-cli-and-dashboard.md)  
**ADRs:** [003](../adr/003-4-config-load-and-bootstrap-sequence.md), [011](../adr/011-3-cli-signals-and-process-lifecycle.md)

### Purpose

Process entrypoint: parse args, run bootstrap, install signals, start dashboard thread, run poll loop, shut down (normal or graceful), exit codes.

### Scope

| In | Out |
|----|-----|
| `argparse` CLI; interactive detection; bootstrap sequence orchestration; signal handlers; main poll sleep; shutdown sequence; exit status | Config schema validation internals; connector HTTP; ACP wire; dashboard HTML |

### Interfaces

```python
def main(argv: list[str] | None = None) -> int: ...

def parse_args(argv: list[str]) -> argparse.Namespace:
    """Positional project: Path | None. Optional --port: int | None."""

def is_interactive() -> bool:
    """True iff sys.stdin.isatty() and sys.stdout.isatty()."""

def resolve_project_root(project: Path | None) -> Path:
    """CLI path or cwd; must be a Git working tree."""

def run_bootstrap(...) -> RuntimeContext:
    """Strict 12-step sequence; see sequences.md. Raises SystemExit or returns context."""

def install_signal_handlers(shutdown_event: threading.Event, immediate_kill: threading.Event, prompt_requested: threading.Event) -> None:
    """Handlers only set flags. SIGTERM and non-interactive SIGINT set shutdown_event for normal shutdown.
    Interactive SIGINT with a live session sets prompt_requested. A second SIGINT or SIGTERM sets immediate_kill."""

def run_poll_loop(ctx: RuntimeContext) -> None:
    """Until shutdown_event or prompt_requested: acquire cycle lock → one orchestration cycle → release → wait."""

def wait_poll_interval(ctx: RuntimeContext) -> None:
    """Sleep up to poll_interval_seconds in ≤1s slices, waking early if shutdown_event is set."""

def choose_shutdown_mode(ctx: RuntimeContext) -> Literal["normal", "graceful"]:
    """Main thread. Interactive Ctrl-C with a live session: prompt until g or n (ui.md). Otherwise normal."""

def shutdown(ctx: RuntimeContext, *, mode: Literal["normal", "graceful"]) -> int:
    """Local cleanup, then 0. Worktree removal failure is logged and does not change the code. Claims are kept."""
```

`RuntimeContext` holds the shared process objects listed above plus project root and state root.

### Lifecycle

1. `main` → `parse_args` → `run_bootstrap` (failure → non-zero exit; dashboard never healthy).
2. Start dashboard thread; print URL.
3. `run_poll_loop` until `shutdown_event` or `prompt_requested`.
4. `choose_shutdown_mode` (if prompt path) then `shutdown` → exit 0.

Unix-like hosts only for process lock (macOS/Linux). Document that on refuse-start / help text.

---

## `orkie.config`

**Features:** [01](../feature/01-project-bootstrap-and-config.md)  
**ADRs:** [002](../adr/002-2-tech-stack-and-dependencies.md), [003](../adr/003-4-config-load-and-bootstrap-sequence.md)

### Purpose

Load and validate `.orkie/config.yaml`, write the default scaffold on accept, substitute prompt tokens.

### Scope

| In | Out |
|----|-----|
| YAML load (`yaml.safe_load`); schema validation; defaults; `prompt_root` resolve under project root; `prompt_file` resolution under `prompt_root` (jailed to project root); `command_ref` resolve against built-in presets + optional project `commands`; scaffold write (exact feature-01 text); token substitution | Repo remote resolution; privileges; state I/O |

### Interfaces

```python
@dataclass(frozen=True)
class Config:
    version: int
    connector: ConnectorConfig
    poll_interval_seconds: int
    issue_labels: list[str]
    max_concurrent_sessions: int
    dashboard_port: int
    agents: list[AgentConfig]
    babysitter: BabysitterConfig

@dataclass(frozen=True)
class ConnectorConfig:
    type: str  # "github"
    repo: str | None  # "owner/name" or None

@dataclass(frozen=True)
class AgentConfig:
    id: str
    name: str
    role: str
    command: list[str]
    max_concurrent_sessions: int
    prompt_template: str  # resolved text (inline or from file)
    triggers: list[Trigger]

@dataclass(frozen=True)
class Trigger:
    type: Literal["any", "labels"]
    labels: list[str]  # empty when type == "any"

@dataclass(frozen=True)
class BabysitterConfig:
    enabled: bool
    id: str | None
    name: str | None
    role: str | None
    command: list[str] | None
    prompt_template: str | None

def config_path(project_root: Path) -> Path:
    """project_root / '.orkie' / 'config.yaml'."""

def load_config(project_root: Path) -> Config:
    """safe_load + validate; unknown fields fail; apply defaults. Raises ConfigError."""

def write_default_scaffold(project_root: Path) -> None:
    """Write exact feature-01 Default scaffold bytes/text. Not yaml.safe_dump."""

def substitute_prompt(
    template: str,
    *,
    session_id: str,
    agent_id: str,
    agent_name: str,
    repo: str,
    issue: Issue | None,
    pr: PullRequest | None,
) -> str:
    """Replace every feature-01 token. Issue and PullRequest are the connector dataclasses.
    Issue session: PR tokens empty. Babysitter: issue tokens empty."""
```

Full field rules: [config.md](config.md).

### Lifecycle

Called only during bootstrap (and scaffold write before re-load). Config object is immutable for the process lifetime.

---

## `orkie.state`

**Features:** [02](../feature/02-local-state.md)  
**ADRs:** [004](../adr/004-3-local-state-format-and-process-lock.md)

### Purpose

Per-user state root, process lock, in-memory claims/snapshot/spawn failures, agent logs.

### Scope

| In | Out |
|----|-----|
| Path layout; flock lock (unlink on release); in-memory get/set for claims/snapshot/spawn failures; append logs with redaction and a per-agent line lock; scrub legacy JSON docs | Claim policy; intake delta; ACP |

### Interfaces

```python
@dataclass(frozen=True)
class ClaimRecord:
    agent_id: str
    issue_number: int
    claimed_at: str  # UTC ISO-8601 with Z

@dataclass(frozen=True)
class SnapshotIssue:
    number: int
    title: str
    body: str
    url: str
    state: str
    labels: list[str]

@dataclass(frozen=True)
class Snapshot:
    fetched_at: str
    issues: list[SnapshotIssue]

@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    agent_id: str
    issue_number: int | None
    pr_number: int | None
    working: bool
    worktree_path: str
    started_at: str

@dataclass(frozen=True)
class SpawnFailureRecord:
    agent_id: str
    agent_name: str
    issue_number: int | None
    pr_number: int | None
    attempt: int  # 1–3
    released: bool
    error: str
    at: str

class StateStore:
    def __init__(self, state_root: Path, *, github_token: str | None = None) -> None: ...

    @property
    def state_root(self) -> Path: ...

    def acquire_lock(self) -> None:
        """Open lock, exclusive fcntl.flock, refuse if holder pid alive, else write pid/started_at."""

    def release_lock(self) -> None:
        """Unlink lock while flock held, then unlock and close. Lock file must not remain after clean shutdown."""

    def ensure_layout(self) -> None:
        """Create state_root, logs/, worktrees/; scrub legacy claims/snapshot/sessions/spawn_failures files."""

    def load_snapshot(self) -> Snapshot | None: ...
    def save_snapshot(self, snapshot: Snapshot) -> None: ...

    def load_claims(self) -> list[ClaimRecord]: ...
    def save_claims(self, claims: list[ClaimRecord]) -> None: ...

    def load_spawn_failures(self) -> list[SpawnFailureRecord]: ...
    def save_spawn_failures(self, failures: list[SpawnFailureRecord]) -> None: ...

    def append_log(
        self,
        agent_id: str,
        line: str,
        *,
        session_id: str,
        issue_number: int | None = None,
        pr_number: int | None = None,
    ) -> None:
        """Hold the lock for this agent_id, append one UTF-8 line with session_id= marker, redact github_token, flush."""

    def read_log(self, agent_id: str) -> str:
        """Full file contents or empty string if missing."""

def default_state_root(owner: str, repo: str, *, home: Path | None = None) -> Path:
    """(home or Path.home()) / '.local' / 'share' / 'orkie' / f'{owner}--{repo}'."""
```

Field schemas and invariants (at most one claim per issue; exactly one of session `issue_number` / `pr_number` non-null): [data.md](data.md). Injectable `home` / `state_root` for tests. `SessionRecord` remains a derived view type for planning; the live session table is authoritative.

### Lifecycle

Constructed when the lock is acquired. Lock held until shutdown releases and unlinks it. Dashboard and orchestration share one instance. Claims, snapshot, and spawn failures start empty in memory.

---

## `orkie.connectors`

**Features:** [03](../feature/03-connector-interface-and-github.md), [06](../feature/06-work-intake-and-issue-monitoring.md), [07](../feature/07-pr-babysitter.md)  
**ADRs:** [005](../adr/005-2-connector-interface-and-github-client.md)

### Purpose

Abstract tracker access; GitHub REST v3 implementation; fake for tests.

### Scope

| In | Out |
|----|-----|
| `Connector` Protocol; dataclasses; GitHub urllib client; read-only privilege probe; mergeable resolution | Intake delta; claim policy; ACP |

### Interfaces

```python
@dataclass(frozen=True)
class OwnerRepo:
    owner: str
    name: str

@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    url: str
    state: str  # connector-reported; open issues from list_open_issues
    labels: list[str]

@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    url: str
    head: str  # head branch name
    base: str  # base branch name
    draft: bool
    mergeable_state: str  # "clean" | "dirty" | "blocked" | "unstable" | "unknown" | other GitHub string

class Privilege(enum.Enum):
    TOKEN = "token"
    READ_REPOSITORY = "read_repository"
    READ_ISSUES = "read_issues"
    READ_PULL_REQUESTS = "read_pull_requests"

@dataclass(frozen=True)
class ProbeResult:
    missing_required: set[Privilege]
    missing_warn_only: set[Privilege]  # always empty in v1 probe list

class Connector(Protocol):
    def repository_id(self) -> OwnerRepo: ...
    def list_open_issues(self) -> list[Issue]: ...
    def list_open_pull_requests(self) -> list[PullRequest]: ...
    def probe_privileges(self, required: set[Privilege]) -> ProbeResult: ...

def resolve_github_repo(project_root: Path, connector_repo: str | None) -> OwnerRepo:
    """connector.repo if set; else origin if GitHub; else sole GitHub remote; else fail naming connector.repo."""

def build_connector(config: Config, token: str, owner_repo: OwnerRepo) -> Connector:
    """GitHub when config.connector.type == 'github'."""

def required_privileges(config: Config) -> set[Privilege]:
    """Feature-03 table: TOKEN, READ_REPOSITORY, READ_ISSUES, and READ_PULL_REQUESTS iff babysitter.enabled."""
```

#### GitHub client (`orkie.connectors.github`)

- Base URL: `https://api.github.com`
- Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`
- List open issues: `GET /repos/{owner}/{repo}/issues?state=open&per_page=100`; follow `Link`; exclude items with `pull_request` key
- List open PRs: `GET /repos/{owner}/{repo}/pulls?state=open&per_page=100`; for each PR whose `mergeable_state` is null/`unknown`, `GET /repos/{owner}/{repo}/pulls/{number}` and use that `mergeable_state` (or `"unknown"` if still unset)
- Probe, in order, only for privileges in `required`: empty token → missing `TOKEN` and no HTTP. `GET /repos/{owner}/{repo}` → `READ_REPOSITORY`. `GET /repos/{owner}/{repo}/issues?state=open&per_page=1` → `READ_ISSUES`. `GET /repos/{owner}/{repo}/pulls?state=open&per_page=1` → `READ_PULL_REQUESTS` only when the babysitter is enabled. HTTP 401 or 403 is `AuthError` and that privilege is missing. A rate-limit body is `RateLimitError` (probe failure at bootstrap; failed fetch during a poll), not a warn-only gap. Warn-only set is always empty in v1
- Errors: raise `ConnectorError` subclasses (`AuthError`, `RateLimitError`, `NotFoundError`, `ConnectorError`) — never return partial pages

#### Fake (`orkie.connectors.fake`)

In-memory issues and PRs for pytest. `list_open_pull_requests` returns stored `mergeable_state` without secondary GETs.

### Lifecycle

Built after the token is read; used for the read-only privilege probe, then every poll cycle. No connection pool beyond urllib defaults.

---

## `orkie.acp`

**Features:** [04](../feature/04-acp-agent-runtime.md)  
**ADRs:** [006](../adr/006-2-acp-agent-runtime.md), [002](../adr/002-2-tech-stack-and-dependencies.md)

### Purpose

JSON-RPC-over-stdio ACP client: spawn, prompt, interrupt, delete, log drain.

### Scope

| In | Out |
|----|-----|
| Subprocess + stdio framing; ACP initialize / optional authenticate / session / prompt / cancel / permissions; session/delete and process-group SIGKILL; log mirror including permission grants | Worktree create; local claims; spawn-failure policy |

### Orkie module API

```python
@dataclass
class SessionHandle:
    session_id: str              # Orkie UUID4
    acp_session_id: str          # from session/new
    agent_id: str
    issue_number: int | None
    pr_number: int | None
    worktree_path: Path
    process: subprocess.Popen
    reader_thread: threading.Thread
    session_delete: bool          # capabilities.session.delete from initialize
    # internal: stdin/stdout locks, pending JSON-RPC futures, closed flag

class AcpClient(Protocol):
    def spawn(
        self,
        session_id: str,
        *,
        command: list[str],
        worktree_path: Path,
        agent_id: str,
        prompt: str,
        issue_number: int | None,
        pr_number: int | None,
        env_token: str,
        append_log: Callable[..., None],
    ) -> SessionHandle:
        """Use the session_id orchestration minted. Do not mint a second id.
        Start process; ACP handshake; deliver prompt. Success is the prompt result's messageId.
        On any failure after process start: SIGKILL the process group, raise AcpError.
        Does not write the session record (orchestration does after success)."""

    def interrupt(self, handle: SessionHandle) -> None:
        """session/cancel; answer pending permissions with cancelled and log permission cancelled."""

    def prompt(self, handle: SessionHandle, text: str) -> None:
        """session/prompt. A JSON-RPC error raises AcpError. Does not wait for idle.
        Used for the graceful wrap-up prompt."""

    def end_session(self, handle: SessionHandle) -> None:
        """Delete path. If session_delete: send session/delete, then SIGKILL the process group
        if the process has not exited within 5 seconds. If not session_delete: SIGKILL immediately.
        The 5 seconds are process exit, not the empty JSON-RPC result."""

    def is_alive(self, handle: SessionHandle) -> bool:
        """False when process has exited."""

class AcpError(Exception):
    """Handshake, prompt, or process failure. str(e) must be redacted (no token)."""
```

Exactly one of `issue_number` / `pr_number` is non-`None` per spawn (enforced by orchestration).

### Wire protocol (ACP v2, stdio)

Normative external reference: [Agent Client Protocol](https://agentclientprotocol.com/protocol/v2/overview) (protocol version **2**). Orkie implements the client side as follows.

**Framing:** newline-delimited JSON-RPC 2.0 UTF-8 messages on the child's stdin/stdout. Messages MUST NOT contain embedded newlines. Child stderr is captured and appended to the agent log (redacted). Orkie never writes non-ACP bytes to stdin.

**Spawn sequence (success path):**

1. `Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=worktree_path, env=os.environ | {"GITHUB_TOKEN": env_token}, start_new_session=True)` when the platform allows a new process group.
2. Start reader thread: read stdout lines → parse JSON-RPC → dispatch responses/notifications; mirror `agent_message` and `agent_message_chunk` text, and stderr lines, to `append_log` with `session_id=`.
3. Request `initialize`:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": 2,
    "capabilities": {},
    "info": {"name": "orkie", "title": "Orkie", "version": "<package_version>"}
  }
}
```

4. Require `protocolVersion == 2`. Any other version fails the spawn. Remember `capabilities.session.delete` (true only when that field is present and true). If `authMethods` is a non-empty list, call `authenticate` with the first method's id (string entry, or object `id` / `methodId`). Empty `authMethods` skips authenticate. Authenticate RPC error fails the spawn.
5. Request `session/new`:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "session/new",
  "params": {
    "cwd": "<absolute worktree_path>",
    "mcpServers": []
  }
}
```

Store returned `sessionId` as `handle.acp_session_id`.

6. **Implicit permission grants:** for every inbound `session/request_permission` while the session is running, including during this handshake, select an option and log a grant. Order: `allow_always`, else `allow_once`, else the first kind that is neither `reject_once` nor `reject_always`, else the first option. A reject-only choice is still a grant and is not a spawn failure. Do not answer `cancelled` on this path. The log line is the permission-grant format in [data.md](data.md).

```json
{
  "jsonrpc": "2.0",
  "id": "<request_id>",
  "result": {
    "outcome": {
      "outcome": "selected",
      "optionId": "<chosen optionId from the request>"
    }
  }
}
```

After `session/cancel` (dashboard interrupt or graceful shutdown), respond to every pending permission with `cancelled` and append a `permission cancelled` log line:

```json
{
  "jsonrpc": "2.0",
  "id": "<request_id>",
  "result": {
    "outcome": { "outcome": "cancelled" }
  }
}
```

7. Request `session/prompt` with a single text content block equal to the substituted prompt:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "session/prompt",
  "params": {
    "sessionId": "<acp_session_id>",
    "prompt": [{"type": "text", "text": "<substituted prompt>"}]
  }
}
```

Spawn succeeds when this request returns a result that carries `messageId`. A later idle `state_update` does not clear `working`. Orkie does not wait for idle before returning from `spawn`. A JSON-RPC error on this request fails the spawn.

```json
{ "jsonrpc": "2.0", "id": 3, "result": { "messageId": "<id>" } }
```

**Handshake timeout:** 60 seconds wall clock covering initialize, `session/new`, and prompt acceptance (steps 3–7). On timeout → SIGKILL the process group → `AcpError`. The wrap-up prompt is not part of this timeout.

**Interrupt:**

```json
{"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": "<acp_session_id>"}}
```

Notification (no response). For each pending `session/request_permission`, respond with cancelled outcome. Session stays alive; Orkie `working` stays true.

**Delete path** (`end_session`), used by dashboard kill and by both shutdown modes:

1. If `session_delete` is true, send:

```json
{
  "jsonrpc": "2.0",
  "id": "<n>",
  "method": "session/delete",
  "params": { "sessionId": "<acp_session_id>" }
}
```

The result is `{}`. That result does not mean the process has exited.

2. If the process has not exited within 5 seconds, `os.killpg` SIGKILL (the child was started with `start_new_session=True`).
3. If `session_delete` is false, skip the request and SIGKILL immediately.
4. Join the reader thread (bounded wait).

**Observe exit:** `process.poll() is not None` or stdout EOF with process dead → `is_alive` false. Orchestration drops a local issue claim only when the exit is observed while Orkie is running and neither `shutdown_event` nor the interactive shutdown-prompt flag is set.

### Fake (`orkie.acp.fake`)

Controllable spawn success/failure, interrupt/kill, and exit for offline tests. No real subprocess.

### Lifecycle

Handles exist only while Orkie runs. The on-disk session document is deleted on shutdown and at the next start. Live handles are authoritative while running. Orkie does not store the agent pid and does not reap orphaned processes at startup.

---

## `orkie.intake`

**Features:** [06](../feature/06-work-intake-and-issue-monitoring.md)  
**ADRs:** [009](../adr/009-3-intake-poll-and-delta.md)

### Purpose

Fetch open issues via connector, maintain intake snapshot, compute the delta for orchestration.

### Scope

| In | Out |
|----|-----|
| Eligibility; fetch; snapshot save; delta; last-error memory | Local claims; PR list; ACP |

### Interfaces

```python
@dataclass(frozen=True)
class IntakeDelta:
    entered: list[Issue]
    left: list[Issue]           # prior snapshot issues no longer intake (diagnostic; step 4 scans all claims)
    labels_changed: list[Issue] # still intake; label set differed

@dataclass(frozen=True)
class IntakeResult:
    ok: bool
    intake_issues: list[Issue]  # empty/unused for mutations when not ok
    delta: IntakeDelta | None
    error: str | None           # set when not ok; also stored as last_error

class Intake:
    def __init__(self, config: Config, connector: Connector, store: StateStore) -> None: ...

    @property
    def last_error(self) -> str | None: ...

    def fetch_and_diff(self) -> IntakeResult:
        """On success: save snapshot, clear last_error, return delta.
        On failure: keep disk snapshot, set last_error, ok=False. Claims are not changed by this method."""
```

**Eligibility:** open non-PR issue (connector already excludes PRs) whose `labels` intersect `config.issue_labels`.

**Delta:** compare previous snapshot issues (by number) to new intake set — entered / left / labels_changed. Orchestration step 4 still scans every claim against the full `intake_issues` list; `left` is diagnostic, not the sole drop input.

### Lifecycle

Invoked once per poll cycle step 2 from the main thread. Does not start a fetch when `shutdown_event` is set.

---

## `orkie.orchestration`

**Features:** [05](../feature/05-agent-orchestration.md), [07](../feature/07-pr-babysitter.md)  
**ADRs:** [007](../adr/007-3-orchestration-cycle-and-claim-session-state-machine.md), [010](../adr/010-2-pr-babysitter-lifecycle.md)

### Purpose

Sole owner of local claims, spawn and drop decisions, caps, the babysitter step, and dashboard interrupt/kill entrypoints.

### Scope

| In | Out |
|----|-----|
| Poll cycle steps 1–9; agent matching; caps; three-strike; babysitter selection; kill/interrupt; shutdown helpers | YAML parsing; GitHub HTTP; dashboard HTML |

### Interfaces

```python
class Orchestrator:
    def __init__(self, ctx: RuntimeContext) -> None: ...

    def run_cycle(self) -> None:
        """One poll tick. Caller holds cycle lock. See sequences.md."""

    def interrupt_session(self, session_id: str) -> None:
        """Raise KeyError if unknown; fail closed if shutting down."""

    def kill_session(self, session_id: str) -> None:
        """ACP delete path; issue session drops the local claim; remove worktree; delete the session record."""

    def request_shutdown(self) -> None:
        """Idempotent; sets shutdown_event (also set by signals)."""

    def wrap_up_sessions(self) -> None:
        """Graceful shutdown: session/cancel and the fixed wrap-up prompt for each live session.
        Pending permissions are cancelled. A prompt error moves that session to end_session."""

    def end_all_sessions(self) -> None:
        """Delete path for every live handle. Does not drop claims."""

    def remove_all_worktrees(self) -> None: ...
```

Orchestration mints one UUID4 `session_id` per spawn and passes it to `worktree.create`, `substitute_prompt`, and `acp.spawn`.

**Agent match:** look up `agent_id` in `config.agents`. Absent → not a match. Present → matches an intake issue if any trigger is `any`, or `labels` and every listed label is on the issue.

**Step 4 (successful issue fetch):** for each saved claim, if `issue_number` ∉ current `intake_issues`, or the stored agent does not match that issue (including absent `agent_id`), stop a live session on it (delete path), drop the claim, remove the worktree. Persist each drop. Do not use only `delta.left` / `labels_changed`.

**Caps:** count working issue sessions only (not babysitter, not failed spawns, not queued claims). Room for agent A = `min(A.max - working_A, global.max - working_all_issues)`.

**Spawn-failure key:** issue sessions keyed by `issue_number`; babysitter by `pr_number`. Append `attempt` 1–3. Success clears that key's records. Third issue failure: warn stderr, set `released=True`, drop the local claim, write no fourth row. While any row has `attempt == 3`, do not claim or spawn that issue. Third PR failure: skip that PR until not selectable, which clears its rows.

### Lifecycle

Constructed after bootstrap; `run_cycle` each poll; controls from dashboard thread under cycle lock.

---

## `orkie.worktree`

**Features:** [05](../feature/05-agent-orchestration.md) (worktrees), [07](../feature/07-pr-babysitter.md)  
**ADRs:** [008](../adr/008-2-git-worktrees.md)

### Purpose

Sync the start checkout to `origin`, then create and remove per-session detached git worktrees under the state root.

### Scope

| In | Out |
|----|-----|
| `git` CLI via subprocess; fetch/reset against `origin`; path under `state_root/worktrees/<session_id>/` | ACP; claims |

### Interfaces

```python
class WorktreeService:
    def __init__(self, state_root: Path, project_root: Path) -> None: ...

    def resolve_base(self) -> tuple[str, str]:
        """Return (commit_sha, branch_or_detached). branch_or_detached is branch name or 'detached'.
        Bootstrap may call once for an initial value. After sync_to_remote / create, returns the synced tip."""

    def sync_to_remote(self) -> tuple[str, str]:
        """Fetch origin; ensure named branch (origin/HEAD default when detached); reset --hard origin/<branch>.
        Update and return (commit_sha, branch). Raise WorktreeError on failure."""

    def create(self, session_id: str) -> Path:
        """sync_to_remote, then git worktree add --detach <state_root>/worktrees/<session_id> <tip_sha>.
        Sync or create failure → raise WorktreeError (becomes spawn failure); no leftover path."""

    def remove(self, worktree_path: Path) -> None:
        """Best-effort: git worktree remove --force <path> from discovered git dir;
        else shutil.rmtree. Never raises to block shutdown or startup (log and continue)."""

    def remove_leftovers(self) -> None:
        """Best-effort remove each directory under worktrees/. Log failures. Do not raise."""
```

### Lifecycle

`resolve_base` during bootstrap, once the project root is known, and the result is stored on `RuntimeContext`. `remove_leftovers` during state prepare. `create` (sync then add) immediately before `acp.spawn`, using the session id orchestration minted; orchestration refreshes `RuntimeContext` tip/branch from `resolve_base` after a successful create. `remove` on agent exit while running, dashboard kill, failed spawn after create, lost eligibility, and both shutdown modes.

---

## `orkie.dashboard`

**Features:** [08](../feature/08-cli-and-dashboard.md)  
**ADRs:** [012](../adr/012-3-dashboard-stack-and-control-api.md), [002](../adr/002-2-tech-stack-and-dependencies.md)

### Purpose

Loopback HTML UI (Jinja2 + packaged CSS) and control POSTs.

### Scope

| In | Out |
|----|-----|
| `ThreadingHTTPServer` on `127.0.0.1`; Jinja page render; `GET /static/...`; form POSTs; cycle lock for controls | Claim policy (delegates to orchestration); ACP wire |

### Interfaces

```python
def start_dashboard_thread(ctx: RuntimeContext) -> threading.Thread:
    """Bind 127.0.0.1:port; on failure raise before loop. Serve until shutdown."""

# HTTP routes — see ui.md for columns and CTAs
# GET  / | /agents | /issues
# GET  /static/<path>   # package data under orkie/static/
# POST /sessions/<session_id>/interrupt
# POST /sessions/<session_id>/kill
```

Page handlers build a frozen view model, then render a Jinja template (`orkie/templates/`). Static handler reads only files under `orkie/static/`. Control handlers: if `shutdown_event` → HTTP 503. Else acquire cycle lock (block until main releases), call orchestration, redirect back to referrer or `/agents`. Unknown session → 404.

### Lifecycle

Bound in bootstrap before the loop; thread started as the loop begins; stopped during shutdown after sessions are ended.
