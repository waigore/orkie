# ADR 001: Process model and module layout

## Status

Superseded by [001-1](../001-1-process-model-and-module-layout.md).

## Context

Orkie is a long-running orchestrator (features [05](../../feature/05-agent-orchestration.md), [08](../../feature/08-cli-and-dashboard.md)): intake poll, claim/spawn, optional babysitter, loopback dashboard, and ACP subprocesses must coexist in one process per GitHub repository. Component design needs a single process model and package map so modules do not invent their own concurrency or cross-import cycles.

## Decision

1. **One process per repository.** A single OS process owns the lock, intake, orchestration, dashboard, and ACP children for one resolved `owner/name`. A second live process refuses to start ([004](004-local-state-format-and-process-lock.md), [011](011-cli-signals-and-process-lifecycle.md)).

2. **Sync core, threads at the edges.** Orchestration and connector calls are synchronous on the **main loop thread** — the process main thread, which runs the poll cycle. Keeping the loop on the main thread lets Python signal handlers (delivered to the main thread) set the shutdown event directly ([011](011-cli-signals-and-process-lifecycle.md)). The dashboard runs on a **background thread** (`threading`). Each ACP session uses a subprocess; a small reader thread (or equivalent) drains that child's stdout/stderr into the ACP client and agent logs. v1 does **not** use `asyncio` as the primary concurrency model.

3. **Installable package `orkie`** with these modules (names are normative for v1 layout):

| Package / module | Responsibility |
|------------------|----------------|
| `orkie` | Package root; version |
| `orkie.__main__` / `orkie.cli` | Entrypoint `orkie`; argparse; project path; `--port` |
| `orkie.config` | Load and validate `.orkie/config.yaml`; default scaffold; prompt substitution |
| `orkie.state` | Local state root, lock, snapshot/claims/sessions/spawn_failures/logs I/O |
| `orkie.connectors` | Abstract connector protocol; `github` implementation |
| `orkie.acp` | ACP JSON-RPC client over stdio; spawn/prompt/interrupt/kill |
| `orkie.intake` | Poll timer; fetch via connector; delta vs snapshot |
| `orkie.orchestration` | Claim/spawn/release; swarm-fit; caps; babysitter hook; worktree prep |
| `orkie.worktree` | Git worktree create/remove |
| `orkie.dashboard` | Loopback HTTP server; agent/issue views; interrupt/kill |

4. **Dependency direction.** `cli` → bootstrap (`config`, `state`, `connectors`) → continuous loop (`intake` → `orchestration` → `acp` / `worktree`). `dashboard` reads `state` and calls into `orchestration`/`acp` for controls. Connector and ACP types do not leak GitHub or agent SDK types into `orchestration` or `intake`.

5. **No built-in role catalog package.** Agent behavior is config + prompts only ([AGENTS.md](../../../AGENTS.md)).

## Reasoning

- Feature 08 requires one long-running CLI process with graceful signal handling; splitting intake and orchestration into separate services would multiply locks and claim races.
- Sync orchestration keeps claim-then-spawn and swarm-fit ordering easy to reason about and test with fakes.
- Threads are enough for a loopback UI and stdio drains without forcing every connector call into async.
- Explicit modules match AGENTS.md (orchestration, connectors, config) and map 1:1 to ADRs 003–012.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Asyncio-first (`asyncio` event loop for poll + HTTP + ACP) | Higher complexity for stdio ACP and sync-friendly fakes; not required for v1 scale |
| Multiprocess workers per agent | Extra IPC; claim ownership and single-instance lock become harder; features assume one Orkie process |
| Monolithic `orkie.py` | Blocks clear fake boundaries for connector and ACP tests |
| Plugin role packages inside Orkie | Conflicts with project-owned roles in `.orkie/` |

## Consequences for design

- Entrypoint sequence: parse CLI → resolve project root → bootstrap ([003](003-config-load-and-bootstrap-sequence.md)) → start dashboard thread → run poll loop until shutdown ([011](011-cli-signals-and-process-lifecycle.md)).
- Shared in-memory handles: loaded config, connector instance, state store, session table (live ACP handles), shutdown event.
- Tests inject fakes at `connectors` and `acp` boundaries; default offline suite needs no network.
