# Components

| Features | ADRs |
|----------|------|
| [01](../feature/01-project-bootstrap-and-config.md)–[08](../feature/08-cli-and-dashboard.md) | [001](../adr/001-1-process-model-and-module-layout.md)–[012](../adr/012-1-dashboard-stack-and-control-api.md) |

Package map and process model are locked by [ADR 001](../adr/001-1-process-model-and-module-layout.md). This document defines purpose, scope, interfaces, and lifecycle for each package so implementation does not invent boundaries.

## Shared process objects

One OS process per resolved `owner/name`. After successful bootstrap, these live for the process lifetime:

| Object | Type / location | Owner |
|--------|-----------------|-------|
| Loaded config | Immutable in-memory object from `orkie.config` | `cli` after bootstrap |
| Connector | `Connector` instance | `cli` constructs; intake/orchestration use |
| State store | `orkie.state.StateStore` | Shared; main thread writes; dashboard reads |
| Live session table | `dict[str, SessionHandle]` keyed by Orkie `session_id` | `orchestration` / `acp` |
| `shutdown_event` | `threading.Event` | `cli` sets; loop and dashboard observe |
| `immediate_kill` | `threading.Event` or bool flag | Second signal during grace |
| Cycle lock | `threading.Lock` | Main holds for whole poll cycle; dashboard takes for one interrupt/kill |
| Start-checkout label | `str` branch name or `"detached"` | Set at bootstrap; dashboard issue view |
| Last intake error | `str \| None` in memory | `intake` writes; dashboard reads |
| Effective dashboard port | `int` | CLI `--port` or config |

Dependency direction (do not invert):

```text
cli → config, state, connectors → intake → orchestration → acp, worktree
dashboard → state (read), orchestration (controls only)
```

---

## `orkie.cli`

**Features:** [01](../feature/01-project-bootstrap-and-config.md), [08](../feature/08-cli-and-dashboard.md)  
**ADRs:** [003](../adr/003-1-config-load-and-bootstrap-sequence.md), [011](../adr/011-1-cli-signals-and-process-lifecycle.md)

### Purpose

Process entrypoint: parse args, run bootstrap, install signals, start dashboard thread, run poll loop, graceful shutdown, exit codes.

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

def install_signal_handlers(shutdown_event: threading.Event, immediate_kill: threading.Event) -> None:
    """SIGINT and SIGTERM: first sets shutdown_event; second sets immediate_kill."""

def run_poll_loop(ctx: RuntimeContext) -> None:
    """Until shutdown_event: acquire cycle lock → one orchestration cycle → release → wait."""

def wait_poll_interval(ctx: RuntimeContext) -> None:
    """Sleep up to poll_interval_seconds in ≤1s slices, waking early if shutdown_event is set."""

def graceful_shutdown(ctx: RuntimeContext) -> int:
    """Returns 0 if all claim-label removals succeeded, else 1."""
```

`RuntimeContext` holds the shared process objects listed above plus project root and state root.

### Lifecycle

1. `main` → `parse_args` → `run_bootstrap` (failure → non-zero exit; dashboard never healthy).
2. Start dashboard thread; print URL.
3. `run_poll_loop` until `shutdown_event`.
4. `graceful_shutdown` → exit code.

Unix-like hosts only for process lock (macOS/Linux). Document that on refuse-start / help text.

---

## `orkie.config`

**Features:** [01](../feature/01-project-bootstrap-and-config.md)  
**ADRs:** [002](../adr/002-1-tech-stack-and-dependencies.md), [003](../adr/003-1-config-load-and-bootstrap-sequence.md)

### Purpose

Load and validate `.orkie/config.yaml`, write the default scaffold on accept, substitute prompt tokens.

### Scope

| In | Out |
|----|-----|
| YAML load (`yaml.safe_load`); schema validation; defaults; `prompt_file` resolution under `.orkie/`; scaffold write (exact feature-01 text); token substitution | Repo remote resolution; privileges; state I/O |

### Interfaces

```python
@dataclass(frozen=True)
class Config:
    version: int
    connector: ConnectorConfig
    poll_interval_seconds: int
    issue_labels: list[str]
    claim_label: str
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
    issue: IssuePromptFields | None,
    pr: PrPromptFields | None,
) -> str:
    """Replace every feature-01 token. Issue session: PR tokens empty. Babysitter: issue tokens empty."""
```

Full field rules: [config.md](config.md).

### Lifecycle

Called only during bootstrap (and scaffold write before re-load). Config object is immutable for the process lifetime.

---

## `orkie.state`

**Features:** [02](../feature/02-local-state.md)  
**ADRs:** [004](../adr/004-1-local-state-format-and-process-lock.md)

### Purpose

Per-user state root, process lock, JSON documents, agent logs.

### Scope

| In | Out |
|----|-----|
| Path layout; flock lock; atomic JSON save/load; append logs with redaction; mark sessions not working | Claim semantics; intake delta; ACP |

### Interfaces

```python
class StateStore:
    def __init__(self, state_root: Path, *, github_token: str | None = None) -> None: ...

    @property
    def state_root(self) -> Path: ...

    def acquire_lock(self) -> None:
        """Open lock, exclusive fcntl.flock, refuse if holder pid alive, else write pid/started_at."""

    def release_lock(self) -> None:
        """Release flock; leave lock file on disk."""

    def ensure_layout(self) -> None:
        """Create state_root, logs/, worktrees/ as needed."""

    def load_snapshot(self) -> Snapshot | None: ...
    def save_snapshot(self, snapshot: Snapshot) -> None: ...

    def load_sessions(self) -> list[SessionRecord]: ...
    def save_sessions(self, sessions: list[SessionRecord]) -> None: ...

    def load_spawn_failures(self) -> list[SpawnFailureRecord]: ...
    def save_spawn_failures(self, failures: list[SpawnFailureRecord]) -> None: ...

    def mark_sessions_not_working(self) -> None:
        """Load sessions, set every working=False, save. Call after reload at start."""

    def append_log(
        self,
        agent_id: str,
        line: str,
        *,
        session_id: str,
        issue_number: int | None = None,
        pr_number: int | None = None,
    ) -> None:
        """Append UTF-8 line with session_id= marker; redact github_token; flush."""

    def read_log(self, agent_id: str) -> str:
        """Full file contents or empty string if missing."""

def default_state_root(owner: str, repo: str, *, home: Path | None = None) -> Path:
    """(home or Path.home()) / '.local' / 'share' / 'orkie' / f'{owner}--{repo}'."""
```

JSON field schemas: [data.md](data.md). Injectable `home` / `state_root` for tests.

### Lifecycle

Constructed in bootstrap step 5–6; lock held until shutdown step 8. Dashboard and orchestration share one instance.

---

## `orkie.connectors`

**Features:** [03](../feature/03-connector-interface-and-github.md), [06](../feature/06-work-intake-and-issue-monitoring.md), [07](../feature/07-pr-babysitter.md)  
**ADRs:** [005](../adr/005-1-connector-interface-and-github-client.md)

### Purpose

Abstract tracker access; GitHub REST v3 implementation; fake for tests.

### Scope

| In | Out |
|----|-----|
| `Connector` Protocol; dataclasses; GitHub urllib client; privilege probe; label ensure/add/remove; mergeable resolution | Intake delta; claim policy; ACP |

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
    READ_ISSUES = "read_issues"
    ADD_LABEL = "add_label"
    REMOVE_LABEL = "remove_label"
    CREATE_LABEL = "create_label"
    READ_PULL_REQUESTS = "read_pull_requests"

@dataclass(frozen=True)
class ProbeResult:
    missing_required: set[Privilege]
    missing_warn_only: set[Privilege]  # always empty in v1 probe list

class Connector(Protocol):
    def repository_id(self) -> OwnerRepo: ...
    def list_open_issues(self) -> list[Issue]: ...
    def list_open_pull_requests(self) -> list[PullRequest]: ...
    def ensure_label(self, name: str) -> None: ...
    def add_issue_label(self, number: int, label: str) -> None: ...
    def remove_issue_label(self, number: int, label: str) -> None: ...
    def probe_privileges(self, required: set[Privilege]) -> ProbeResult: ...

def resolve_github_repo(project_root: Path, connector_repo: str | None) -> OwnerRepo:
    """connector.repo if set; else origin if GitHub; else sole GitHub remote; else fail naming connector.repo."""

def build_connector(config: Config, token: str, owner_repo: OwnerRepo) -> Connector:
    """GitHub when config.connector.type == 'github'."""

def required_privileges(config: Config, *, claim_label_exists: bool) -> set[Privilege]:
    """Feature-03 table. Include CREATE_LABEL iff claim label missing. Include READ_PULL_REQUESTS iff babysitter.enabled."""
```

#### GitHub client (`orkie.connectors.github`)

- Base URL: `https://api.github.com`
- Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`
- List open issues: `GET /repos/{owner}/{repo}/issues?state=open&per_page=100`; follow `Link`; exclude items with `pull_request` key
- List open PRs: `GET /repos/{owner}/{repo}/pulls?state=open&per_page=100`; for each PR whose `mergeable_state` is null/`unknown`, `GET /repos/{owner}/{repo}/pulls/{number}` and use that `mergeable_state` (or `"unknown"` if still unset)
- Ensure label: `GET /repos/{owner}/{repo}/labels/{name}` → 404 then `POST /repos/{owner}/{repo}/labels` with `{"name": name, "color": "0e8a16"}` (color fixed for v1)
- Add/remove label: `POST/DELETE /repos/{owner}/{repo}/issues/{number}/labels[/{name}]`
- Probe: missing token → `TOKEN`; otherwise attempt lightweight checks mapped to required set (e.g. GET repo, GET issues page 1, label ops as needed). Warn-only set always empty in v1
- Errors: raise `ConnectorError` subclasses (`AuthError`, `RateLimitError`, `NotFoundError`, `ConnectorError`) — never return partial pages

#### Fake (`orkie.connectors.fake`)

In-memory issues/PRs/labels for pytest. `list_open_pull_requests` returns stored `mergeable_state` without secondary GETs.

### Lifecycle

Built in bootstrap step 8; used for privilege probe (9), ensure claim label (10), then every poll cycle. No connection pool beyond urllib defaults.

---

## `orkie.acp`

**Features:** [04](../feature/04-acp-agent-runtime.md)  
**ADRs:** [006](../adr/006-acp-agent-runtime.md), [002](../adr/002-1-tech-stack-and-dependencies.md)

### Purpose

JSON-RPC-over-stdio ACP client: spawn, prompt, interrupt, kill, log drain.

### Scope

| In | Out |
|----|-----|
| Subprocess + stdio framing; ACP initialize / session / prompt / cancel / permissions; process-group kill; log mirror | Worktree create; claim labels; spawn-failure policy |

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
    # internal: stdin/stdout locks, pending JSON-RPC futures, closed flag

class AcpClient(Protocol):
    def spawn(
        self,
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
        """New Orkie session_id; start process; ACP handshake; deliver prompt.
        On any failure after process start: kill process, raise AcpError.
        Does not set disk working=true (orchestration does after success)."""

    def interrupt(self, handle: SessionHandle) -> None:
        """session/cancel; answer pending permissions with cancelled."""

    def kill(self, handle: SessionHandle) -> None:
        """session/close if possible, then terminate process / process group."""

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
2. Start reader thread: read stdout lines → parse JSON-RPC → dispatch responses/notifications; mirror text-like `session/update` content and stderr lines to `append_log` with `session_id=`.
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

4. Require response `protocolVersion == 2` (or a version Orkie supports). If agent returns unsupported version → fail spawn. If `authMethods` is non-empty → fail spawn with a clear error (v1 does not implement `auth/login`).
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

6. **Full permissions:** for every inbound `session/request_permission` while the session is alive (except after cancel), auto-approve without prompting. Choose the option whose `kind` is, in order: `allow_always`, then `allow_once`, else the first option whose `kind` is not `reject_once` or `reject_always`. If no allow option exists, fail the spawn or log and respond cancelled (should not happen with well-behaved agents).

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

After `session/cancel`, respond to every pending permission with:

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

Spawn succeeds when this request returns success (message accepted). Foreground agent work continues via `session/update` notifications; Orkie does not wait for idle before returning from `spawn`.

**Handshake timeout:** 60 seconds wall clock covering steps 3–7. On timeout → kill process group → `AcpError`.

**Interrupt:**

```json
{"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": "<acp_session_id>"}}
```

Notification (no response). For each pending `session/request_permission`, respond with cancelled outcome. Session stays alive; Orkie `working` stays true.

**Kill / shutdown terminate:**

1. Best-effort `session/close` request (ignore errors).
2. `process.terminate()`; if still alive after a short wait (2s), `os.killpg(pid, SIGKILL)` when `start_new_session` was used, else `process.kill()`.
3. Join reader thread (bounded wait).

**Observe exit:** `process.poll() is not None` or stdout EOF with process dead → `is_alive` false. Orchestration owns claim release.

### Fake (`orkie.acp.fake`)

Controllable spawn success/failure, interrupt/kill, and exit for offline tests. No real subprocess.

### Lifecycle

Handles exist only while Orkie runs. Disk `working` is cleared on every process start; live handles are authoritative while running.

---

## `orkie.intake`

**Features:** [06](../feature/06-work-intake-and-issue-monitoring.md)  
**ADRs:** [009](../adr/009-1-intake-poll-and-delta.md)

### Purpose

Fetch open issues via connector, maintain intake snapshot, compute delta and `claim_labeled` set for orchestration.

### Scope

| In | Out |
|----|-----|
| Eligibility; fetch; snapshot save; delta; last-error memory | Claim label mutations; PR list; ACP |

### Interfaces

```python
@dataclass(frozen=True)
class IntakeDelta:
    entered: list[Issue]
    left: list[Issue]           # prior snapshot issues no longer intake
    labels_changed: list[Issue] # still intake; label set differed
    claim_labeled: list[Issue]  # open issues with claim_label (intake or not); not stored in snapshot

@dataclass(frozen=True)
class IntakeResult:
    ok: bool
    intake_issues: list[Issue]  # empty/unused for mutations when not ok
    delta: IntakeDelta | None
    claim_labeled: list[Issue]  # empty when not ok
    error: str | None           # set when not ok; also stored as last_error

class Intake:
    def __init__(self, config: Config, connector: Connector, store: StateStore) -> None: ...

    @property
    def last_error(self) -> str | None: ...

    def fetch_and_diff(self) -> IntakeResult:
        """On success: save snapshot, clear last_error, return delta.
        On failure: keep disk snapshot, set last_error, ok=False; no claim_labeled."""
```

**Eligibility:** open non-PR issue (connector already excludes PRs) whose `labels` intersect `config.issue_labels`.

**Delta:** compare previous snapshot issues (by number) to new intake set — entered / left / labels_changed. `claim_labeled` = all issues from this successful open-issue fetch that include `config.claim_label` in `labels` (including non-intake opens).

### Lifecycle

Invoked once per poll cycle step 2 from the main thread. Does not start a fetch when `shutdown_event` is set.

---

## `orkie.orchestration`

**Features:** [05](../feature/05-agent-orchestration.md), [07](../feature/07-pr-babysitter.md)  
**ADRs:** [007](../adr/007-1-orchestration-cycle-and-claim-session-state-machine.md), [010](../adr/010-1-pr-babysitter-lifecycle.md)

### Purpose

Sole owner of claim-label mutations, spawn/release decisions, caps, swarm-fit, babysitter step, and dashboard interrupt/kill entrypoints.

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
        """Terminate ACP; issue session → remove claim label; remove worktree; mark not working."""

    def request_shutdown(self) -> None:
        """Idempotent; sets shutdown_event (also set by signals)."""

    def terminate_all_sessions(self) -> None:
        """ACP kill all live handles (shutdown step 3)."""

    def release_claims_for_stopped_issue_sessions(
        self, session_ids: list[str]
    ) -> list[str]:
        """Remove claim labels; return list of issue numbers (or ids) that failed removal."""

    def remove_all_worktrees(self) -> None: ...
```

**Agent match:** an agent matches an intake issue if any trigger is `any`, or `labels` and every listed label is on the issue.

**Caps:** count working issue sessions only (not babysitter, not failed spawns). Room for agent A = `min(A.max - working_A, global.max - working_all_issues)`.

**Spawn-failure key:** issue sessions keyed by `issue_number`; babysitter by `pr_number`. Consecutive `attempt` 1–3. Success clears that key's records. Third issue failure: warn stderr, set `released=True`, remove claim label. Third PR failure: skip that PR until not selectable.

### Lifecycle

Constructed after bootstrap; `run_cycle` each poll; controls from dashboard thread under cycle lock.

---

## `orkie.worktree`

**Features:** [05](../feature/05-agent-orchestration.md) (worktrees), [07](../feature/07-pr-babysitter.md)  
**ADRs:** [008](../adr/008-1-git-worktrees.md)

### Purpose

Create and remove per-session detached git worktrees under the state root.

### Scope

| In | Out |
|----|-----|
| `git` CLI via subprocess; path under `state_root/worktrees/<session_id>/` | ACP; claims |

### Interfaces

```python
class WorktreeService:
    def __init__(self, state_root: Path, project_root: Path) -> None: ...

    def resolve_base(self) -> tuple[str, str]:
        """Return (commit_sha, branch_or_detached). branch_or_detached is branch name or 'detached'.
        Freeze at first call (bootstrap); reuse for the process lifetime."""

    def create(self, session_id: str) -> Path:
        """git -C project_root worktree add --detach <state_root>/worktrees/<session_id> <commit_sha>
        Missing git → raise WorktreeError (becomes spawn failure)."""

    def remove(self, worktree_path: Path) -> None:
        """Best-effort: git worktree remove --force <path> from discovered git dir;
        else shutil.rmtree. Never raises to block shutdown (log and continue)."""
```

### Lifecycle

`resolve_base` during bootstrap (for dashboard label). `create` immediately before `acp.spawn`. `remove` on every terminal session transition and on failed spawn after create.

---

## `orkie.dashboard`

**Features:** [08](../feature/08-cli-and-dashboard.md)  
**ADRs:** [012](../adr/012-1-dashboard-stack-and-control-api.md)

### Purpose

Loopback HTML UI and control POSTs.

### Scope

| In | Out |
|----|-----|
| `ThreadingHTTPServer` on `127.0.0.1`; pages; form POSTs; cycle lock for controls | Claim policy logic (delegates to orchestration); ACP wire |

### Interfaces

```python
def start_dashboard_thread(ctx: RuntimeContext) -> threading.Thread:
    """Bind 127.0.0.1:port; on failure raise before loop. Serve until shutdown."""

# HTTP routes — see ui.md for columns and CTAs
# GET  / | /agents | /issues
# POST /sessions/<session_id>/interrupt
# POST /sessions/<session_id>/kill
```

Control handlers: if `shutdown_event` → HTTP 503. Else acquire cycle lock (block until main releases), call orchestration, redirect back to referrer or `/agents`. Unknown session → 404.

### Lifecycle

Bound in bootstrap step 11; thread started in step 12; stopped in shutdown step 7.
