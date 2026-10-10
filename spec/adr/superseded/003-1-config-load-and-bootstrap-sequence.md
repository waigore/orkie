## Status

Superseded by [003-2](003-2-config-load-and-bootstrap-sequence.md).

Supersedes [003](003-config-load-and-bootstrap-sequence.md).

## Context

Feature [01](../feature/01-project-bootstrap-and-config.md) defines config schema, interactive default scaffold, and non-interactive fail-hard behavior. Feature [03](../feature/03-connector-interface-and-github.md) defines privilege probes. Feature [08](../feature/08-cli-and-dashboard.md) starts the process. Implementers need a single ordered bootstrap sequence so prompts, hard fails, and side effects (scaffold write, label create, lock) never race or prompt in the wrong mode.

## Decision

### Interactive detection

Interactive when `sys.stdin.isatty()` and `sys.stdout.isatty()` are both true. Otherwise non-interactive. No override flag in v1.

### Bootstrap sequence (strict order)

On `orkie [project] [--port N]`:

1. **Resolve project root** — explicit CLI path, else cwd. Must be a Git working tree (`.git` present or discoverable). Failure → exit with error; no prompt.
2. **Locate `.orkie/config.yaml`**
   - Missing + interactive → prompt to create default scaffold; accept writes file and continues; reject exits without loop.
   - Missing + non-interactive → hard fail; no write.
3. **Load and validate config** — `yaml.safe_load` then hand validation against feature-01 schema (unknown fields fail; defaults applied). Load `prompt_file` paths only under `.orkie/`. Failure → hard fail (both modes).
4. **Resolve repository identity** — `connector.repo` or GitHub remote rules from feature 03. Failure → hard fail.
5. **Acquire process lock** — under state root for that `owner--repo` ([004-1](004-1-local-state-format-and-process-lock.md)). Live holder → refuse start. Stale pid → take lock.
6. **Prepare state directory** — ensure layout; reload snapshot, sessions, and spawn failures; then force every session `working` to false.
7. **Read `GITHUB_TOKEN`** — empty/missing counts as a required-privilege gap (step 9).
8. **Construct connector** — GitHub implementation; no orchestration yet.
9. **Privilege verification** — probe required privileges from feature 03 (token, read issues, add/remove labels, create claim label if missing, read PRs if babysitter enabled). Warn-only gaps → CLI warning, continue.
   - Required missing + interactive → report each gap; prompt retry/abort; do not enter loop until met or abort.
   - Required missing + non-interactive → hard fail naming each gap.
10. **Ensure claim label exists** — create via connector when absent and permitted (part of required privileges).
11. **Bind dashboard** — `127.0.0.1` + CLI `--port` or `dashboard_port`. In use → fail; do not run loop without dashboard.
12. **Enter continuous loop** — start dashboard thread; run intake/orchestration on `poll_interval_seconds` ([007-1](007-1-orchestration-cycle-and-claim-session-state-machine.md), [009-1](009-1-intake-poll-and-delta.md), [011-1](011-1-cli-signals-and-process-lifecycle.md)).

Config is immutable for the process lifetime after step 3. File edits require restart. Prompt text loaded in step 3 is the text later substituted.

### Default scaffold

When accepted, write the default `.orkie/config.yaml` as the exact document in feature 01's Default scaffold section. Treat it as normal config afterward.

### Prompt substitution

Owned by `orkie.config`. Replace every token listed in feature 01. For an issue session, the PR tokens become empty. For a babysitter session, the issue tokens become empty. No other templating engine.

## Reasoning

- Ordering puts validation before lock and network so bad YAML never holds the repository lock.
- Lock before connector probes prevents two processes from both creating labels or claiming.
- Reloading sessions and then forcing `working` false keeps a stored flag from surviving the reload.
- Interactive gates match vocabulary and features 01/03/08 without a separate “yes to all” mode that could hide missing privileges in systemd.

## Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Hot-reload config on file change | Feature 01: config applies for that process only |
| Prompt in non-interactive with defaults | Forbidden by non-interactive principle |
| Create default config without consent | Feature 01 requires accept/reject when interactive |
| Privilege probe before lock | Two starters could race claim-label creation and intake |
| Mark sessions not working and then reload them | The reload would restore `working: true` |
| Emit the scaffold with `yaml.safe_dump` | The dump is not the feature-01 document |

## Consequences for design

- `orkie.cli` owns the sequence; submodules expose pure helpers (`load_config`, `acquire_lock`, `verify_privileges`).
- Bootstrap failures never start the dashboard as “healthy” for an unbootstrapped project.
- Exit codes: non-zero on bootstrap failure; shutdown codes per [011-1](011-1-cli-signals-and-process-lifecycle.md).
- Unit tests cover interactive vs non-interactive branches with fake TTYs and fake connectors.
