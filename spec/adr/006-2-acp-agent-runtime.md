# ADR 006: ACP agent runtime

## Status

Accepted

Supersedes [006-1](superseded/006-1-acp-agent-runtime.md).

## Context

Feature [04](../feature/04-acp-agent-runtime.md) requires spawn, prompt, status, interrupt, and kill via Agent Client Protocol version 2, implicit permission grants, authenticate when the agent advertises auth methods, and two ways to end a session. Feature [05](../feature/05-agent-orchestration.md) supplies worktrees and the local claim around sessions. Design needs a concrete transport, session lifecycle, and permission policy without vendor SDKs.

## Decision

### Transport and client

- Orkie owns `orkie.acp`: a thin **JSON-RPC over stdio** client compatible with ACP protocol version 2. Initialize requests that version and no other.
- Spawn: `subprocess.Popen` with `command` from config (argv list, already resolved from inline `command` or `command_ref`), `cwd=worktree_path`, env = parent env plus `GITHUB_TOKEN`, `start_new_session=True` so the child is its own process group.
- First-class documented commands (not hard-coded exclusivity): `opencode acp`; `grok agent --always-approve stdio`; `agent acp` (Cursor). Built-in preset names live in feature [01](../feature/01-project-bootstrap-and-config.md).
- No proprietary OpenCode/Grok/Cursor Python SDK for core control.
- Client capabilities sent at initialize are empty. If the agent returns a non-empty `authMethods` list, call `authenticate` with the first method's id before `session/new`. Empty `authMethods` skips authenticate. Authenticate RPC error fails the spawn. Operator pre-authenticates outside Orkie (CLI login or env credentials).
- Remember `capabilities.session.delete` from initialize.

### Session identity and binding

Orchestration mints one `session_id` (UUID4 string) per spawn and passes it to worktree create, prompt substitution, and `acp.spawn`. `acp.spawn` does not mint a second id. Bind exactly one config identity (`agent_id`) and exactly one of `issue_number` or `pr_number`. Persist the session record and set `working=true` only after the agent accepts the initial prompt. Acceptance is the prompt result that carries a message id. Do not wait for a later idle status. A JSON-RPC error on that prompt fails the spawn.

### Control sequence

```text
prepare worktree -> start process -> ACP initialize [/ authenticate] / session
  -> grant permissions -> deliver substituted prompt -> monitor (status/logs)
  -> {interrupt | delete | observe exit}
```

| Operator / orch action | ACP behavior | Local issue claim |
|------------------------|--------------|-------------------|
| Interrupt (dashboard) | Cancel current turn. Pending permission → `cancelled`, logged as `permission cancelled` | Stays |
| Kill (dashboard) | Delete path below | Dropped by orchestration |
| Agent exit while running (shutdown not started) | Observe EOF/exit | Dropped by orchestration |
| Agent exit after shutdown started (`shutdown_event` or prompt flag) | Observe EOF/exit | Kept |
| Normal shutdown | Delete path for every live session | Kept |
| Graceful shutdown | Cancel, one wrap-up prompt, 20 seconds, then the delete path | Kept |

v1 dashboard does not send follow-up prompts after interrupt. The wrap-up prompt is the fixed string in feature 04. An idle status during the 20 seconds does not end that wait early. A JSON-RPC error on the wrap-up prompt moves that session to the delete path immediately. Pending permission requests after graceful `session/cancel` are answered `cancelled` and logged as `permission cancelled`.

### Delete path

Used by dashboard kill and by both shutdown modes:

- If `capabilities.session.delete` was reported, send `session/delete`.
- If the process has not exited within 5 seconds, SIGKILL the process group.
- If `capabilities.session.delete` was not reported, SIGKILL the process group immediately and do not send `session/delete`.

The 5 seconds are process exit. An empty `session/delete` result does not by itself mean the process has exited. Session transcripts are not retained. Orkie does not store the agent pid and does not reap orphaned agent processes at startup.

### Permissions

While a session is running, select an option for every `session/request_permission`: `allow_always`, else `allow_once`, else the first kind that is neither `reject_once` nor `reject_always`, else the first option. A reject-only choice is still a grant, including during handshake, and is not a spawn failure. Log each grant to the agent log (feature 02). Do not answer `cancelled` as the autonomous policy.

### Logs and redaction

Mirror agent message text and child stderr into `logs/<agent_id>.log` with `session_id=` markers ([004-2](004-2-local-state-format-and-process-lock.md)). Permission lines go to the same file. Never write the raw `GITHUB_TOKEN` value into logs or spawn-failure `error` text.

### Spawn failure

If the process cannot start, the handshake fails (including protocol version mismatch or failed `authenticate`), or the initial prompt returns an error: no working session; return the error to orchestration for spawn-failure records and three-strike claim rules ([007-2](007-2-orchestration-cycle-and-claim-session-state-machine.md)). Advertising a non-empty `authMethods` list alone is not a spawn failure when `authenticate` succeeds. Spawn failure does not occupy a session slot. Remove a worktree created for that attempt.

## Reasoning

- In-tree ACP client matches “any ACP-compatible agent” and avoids vendor lock-in ([002-2](002-2-tech-stack-and-dependencies.md)).
- Implicit grants match feature 04: Orkie is autonomous, and the audit trail is the agent log.
- Calling `authenticate` when methods are advertised unblocks Cursor and similar agents that advertise login while relying on pre-auth credentials.
- One session id minted by orchestration keeps the worktree, the prompt token, and the ACP session on the same identity.
- Delete-then-SIGKILL matches feature 04. The empty delete result is not a process exit.
- Clear interrupt vs kill semantics keep the local claim in place during cooperative cancel and drop it on dashboard kill.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Vendor SDK per agent | Breaks generic ACP path; multiplies integrations |
| Ask the operator to approve permissions | Feature 04: grants are implicit |
| Fail spawn whenever `authMethods` is non-empty | Blocks Cursor even when pre-authenticated; feature 04 requires `authenticate` |
| Interactive ACP login inside Orkie | Orkie is autonomous; operator authenticates the agent CLI outside the loop |
| Answer `cancelled` when every option is a reject kind | The agent would block. Feature 04 still selects an option |
| `session/close` and a 30 second grace | Feature 04 ends sessions with `session/delete` and a 5 second process-exit window |
| Treat the empty delete result as process exit | The protocol does not define that the process has exited |
| Reuse session id across respawns | Feature vocabulary: new spawn = new session id |
| `acp.spawn` mints its own session id | The worktree and `__SESSION_ID__` already used the id orchestration minted |
| Dashboard follow-up prompt in v1 | Explicitly out of scope in features 04/08 |
| Wait for idle before spawn succeeds | Acceptance is the prompt's message id. Idle arrives later |
| Store agent pids and reap them at startup | Feature 02 does not record an agent pid. Orphans are outside this process |

## Consequences for design

- `orkie.orchestration` mints `session_id`, calls `worktree.create`, then `acp.spawn(session_id, ...)`, and owns claim drop on kill and on exit while running.
- `orkie.acp` exposes `spawn`, `interrupt`, `delete_session`, and the delete-path helper used by kill and shutdown. It does not create worktrees ([008-1](008-1-git-worktrees.md)). Spawn runs initialize, optional authenticate, then session/new and the initial prompt.
- Live handles live in an in-memory session table keyed by `session_id`. The on-disk session document is deleted on shutdown and at the next start ([004-2](004-2-local-state-format-and-process-lock.md)).
- Wire bodies for permission outcomes, prompt acceptance, authenticate, and `session/delete` live in design.
- Tests fake the ACP client at the `orkie.acp` boundary.
