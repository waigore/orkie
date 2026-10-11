# ADR 003: Config load and bootstrap sequence

## Status

Superseded by [003-4-config-load-and-bootstrap-sequence](../003-4-config-load-and-bootstrap-sequence.md).

Was Accepted.


## Context

Feature [01](../feature/01-project-bootstrap-and-config.md) defines config schema, interactive default scaffold, and non-interactive fail-hard behavior. Feature [03](../feature/03-connector-interface-and-github.md) defines privilege probes. Feature [08](../feature/08-cli-and-dashboard.md) starts the process. Implementers need a single ordered bootstrap sequence so prompts, hard fails, and side effects (scaffold write, lock) never race or prompt in the wrong mode.

## Decision

### Interactive detection

Interactive when `sys.stdin.isatty()` and `sys.stdout.isatty()` are both true. Otherwise non-interactive. No override flag in v1.

### Bootstrap sequence (strict order)

On `orkie [project] [--port N]`:

1. **Resolve project root** — explicit CLI path, else cwd. Must be a Git working tree (`.git` present or discoverable). Failure → exit with error; no prompt.
2. **Locate `.orkie/config.yaml`**
   - Missing + interactive → prompt to create default scaffold; accept writes file and continues; reject exits without loop.
   - Missing + non-interactive → hard fail; no write.
3. **Load and validate config** — `yaml.safe_load` then hand validation against feature-01 schema (unknown fields fail; defaults applied). Resolve optional `prompt_root` (default `.`) under the project root; load each `prompt_file` relative to that root. Reject absolute paths and any path that escapes the project root. Resolve each agent and enabled-babysitter `command_ref` against built-in presets and optional project `commands` (feature 01); store resolved argv on the loaded config. Failure → hard fail (both modes).
4. **Resolve repository identity** — `connector.repo` or GitHub remote rules from feature 03. Failure → hard fail.
5. **Resolve the start checkout** — `worktree.resolve_base` on the project root ([008-1](008-1-git-worktrees.md)). Remember the branch name, or `detached`, and the commit, for the process lifetime. Failure → hard fail.
6. **Acquire process lock** — under state root for that `owner--repo` ([004-2](004-2-local-state-format-and-process-lock.md)). Live holder → refuse start. Stale pid → take lock. Corrupt lock contents, once the lock is held, are overwritten in place.
7. **Prepare state directory** — ensure layout; load `claims`, `snapshot`, and `spawn_failures`. Delete leftover session records. Remove leftover worktrees best-effort. Do not resume ACP sessions and do not reap agent processes. A corrupt `claims`, `snapshot`, or `spawn_failures` file fails bootstrap and names the file. A missing file is empty.
8. **Read `GITHUB_TOKEN`** — empty/missing counts as a required-privilege gap (step 10).
9. **Construct connector** — GitHub implementation; no orchestration yet.
10. **Privilege verification** — probe the required set from feature 03 (token, read issues, read PRs if babysitter enabled). The probe is read-only. The v1 warn-only set is empty.
    - Required missing + interactive → report each gap; prompt retry/abort; do not enter loop until met or abort.
    - Required missing + non-interactive → hard fail naming each gap.
11. **Bind dashboard** — `127.0.0.1` + CLI `--port` or `dashboard_port`. In use → fail; do not run loop without dashboard.
12. **Enter continuous loop** — start dashboard thread; run intake/orchestration on `poll_interval_seconds` ([007-2](007-2-orchestration-cycle-and-claim-session-state-machine.md), [009-2](009-2-intake-poll-and-delta.md), [011-2](011-2-cli-signals-and-process-lifecycle.md)).

Config is immutable for the process lifetime after step 3. File edits require restart. Prompt text loaded in step 3 is the text later substituted.

### Default scaffold

When accepted, write the default `.orkie/config.yaml` as the exact document in feature 01's Default scaffold section. Treat it as normal config afterward.

### Prompt substitution

Owned by `orkie.config`. Replace every token listed in feature 01. Inputs are the connector `Issue` or `PullRequest` for the bound work item, plus the config identity and the session id minted for that spawn. For an issue session, the PR tokens become empty. For a babysitter session, the issue tokens become empty. No other templating engine.

## Reasoning

- Ordering puts validation before lock and network so bad YAML never holds the repository lock.
- Lock before connector probes prevents two processes from probing and spawning for the same repository.
- The start checkout is resolved once the project root is known, and kept for every worktree created in this process.
- Discarding leftover sessions matches feature 02: claims survive, ACP sessions do not resume.
- Interactive gates match vocabulary and features 01/03/08 without a separate “yes to all” mode that could hide missing privileges in systemd.
- Prompt files are project-level configuration. Resolving them from `prompt_root` (default project root) keeps them out of the Orkie-owned `.orkie/` tree unless the maintainer opts in with `prompt_root: .orkie`.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Hot-reload config on file change | Feature 01: config applies for that process only |
| Prompt in non-interactive with defaults | Forbidden by non-interactive principle |
| Create default config without consent | Feature 01 requires accept/reject when interactive |
| Privilege probe before lock | Two starters could both pass the probe and enter the loop |
| Reload session records and treat them as live | Sessions are not resumed. The files are deleted |
| Emit the scaffold with `yaml.safe_dump` | The dump is not the feature-01 document |
| Create or ensure a GitHub label during bootstrap | Claims are local. The connector does not write labels |
| Resolve `prompt_file` only under `.orkie/` | Feature 01: prompts are project-level; `.orkie/` is Orkie settings |

## Consequences for design

- `orkie.cli` owns the sequence; submodules expose pure helpers (`load_config`, `acquire_lock`, `verify_privileges`, `resolve_base`).
- Bootstrap failures never start the dashboard as “healthy” for an unbootstrapped project.
- Exit codes: non-zero on bootstrap failure; shutdown exits 0 after local cleanup ([011-2](011-2-cli-signals-and-process-lifecycle.md)).
- Unit tests cover interactive vs non-interactive branches with fake TTYs and fake connectors.
- `orkie.config` resolves `prompt_root` once at load and reads each `prompt_file` from that base; resolved paths stay under the project root.
