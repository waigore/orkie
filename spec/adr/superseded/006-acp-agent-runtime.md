## Status

Superseded by [006-1](../006-1-acp-agent-runtime.md).

## Context

Feature [04](../feature/04-acp-agent-runtime.md) requires spawn, prompt, status, interrupt, and kill via Agent Client Protocol. Feature [05](../feature/05-agent-orchestration.md) supplies worktrees and claim lifecycle around sessions. Design needs a concrete transport, session lifecycle, and permission policy without vendor SDKs.

## Decision

### Transport and client

- Orkie owns `orkie.acp`: a thin **JSON-RPC over stdio** client compatible with ACP.
- Spawn: `subprocess.Popen` with `command` from config (argv list), `cwd=worktree_path`, env = parent env plus `GITHUB_TOKEN`.
- First-class documented commands (not hard-coded exclusivity): `opencode acp`; `grok agent --always-approve stdio`.
- No proprietary OpenCode/Grok Python SDK for core control.

### Session identity and binding

On each spawn, generate a new `session_id` (UUID4 string). Bind exactly one config identity (`agent_id`) and exactly one of `issue_number` or `pr_number`. Persist session record; set `working=true` only after successful ACP start and initial prompt delivery.

### Control sequence

```text
prepare worktree -> start process -> ACP initialize/session -> grant full permissions
  -> deliver substituted prompt -> monitor (status/logs) -> {interrupt | kill | observe exit}
```

| Operator / orch action | ACP behavior | Claim (issue sessions) |
|------------------------|--------------|------------------------|
| Interrupt (dashboard) | Cancel current turn | Remains |
| Kill (dashboard) | Terminate session/process | Released by orchestration |
| Agent exit | Observe EOF/exit | Released by orchestration |
| Shutdown | Terminate all sessions | Released per [011-1](011-1-cli-signals-and-process-lifecycle.md) |

v1 dashboard does not send follow-up prompts after interrupt.

### Permissions

Orkie grants **full permissions** for project work whenever ACP negotiates capabilities. No Orkie-side restrictive sandbox. Behavioral limits live in project prompts.

### Logs and redaction

Mirror ACP/log output into `logs/<agent_id>.log` with `session_id=` markers ([004-1](004-1-local-state-format-and-process-lock.md)). Never write the raw `GITHUB_TOKEN` value into logs or spawn-failure `error` text.

### Spawn failure

If the process cannot start or ACP handshake/prompt fails: no working session; return error to orchestration for spawn-failure records and three-strike claim rules ([007-1](007-1-orchestration-cycle-and-claim-session-state-machine.md)). Spawn failure does not occupy a session slot.

### Process groups

Start agents in a new session/process group where the platform allows so shutdown can kill the group after the 30s grace ([011-1](011-1-cli-signals-and-process-lifecycle.md)).

## Reasoning

- In-tree ACP client matches “any ACP-compatible agent” and avoids vendor lock-in ([002-1](002-1-tech-stack-and-dependencies.md)).
- Full permissions match feature 04; Orkie's job is orchestration, not sandboxing the coding agent.
- Clear interrupt vs kill semantics keep claim labels stable during cooperative cancel.
- UUID4 session ids are an ADR-level choice; the features require only a generated id that is unique per spawn.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Vendor SDK per agent | Breaks generic ACP path; multiplies integrations |
| Orkie permission sandbox | Feature 04 requires full permissions |
| Reuse session id across respawns | Feature vocabulary: new spawn = new session id |
| Dashboard follow-up prompt in v1 | Explicitly out of scope in features 04/08 |

## Consequences for design

- `orkie.orchestration` calls `acp.spawn` / `interrupt` / `kill` and owns claim release on kill/exit.
- Live handles live in an in-memory session table keyed by `session_id`; disk `working` is informational after restart (always cleared on start).
- Tests fake the ACP client at the `orkie.acp` boundary.
- Worktree path is an input to spawn; ACP module does not create worktrees ([008-1](../008-1-git-worktrees.md)).
