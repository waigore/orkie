# Operation

## CLI

```bash
orkie [project] [--port PORT]
```

| Argument | Meaning |
|----------|---------|
| `project` | Git project root (default: current directory) |
| `--port` | Dashboard port; overrides `dashboard_port` in config |

Examples:

```bash
orkie
orkie /path/to/project
orkie --port 9000
```

After bootstrap, Orkie prints the bound dashboard URL and runs continuously: intake poll → claim / spawn → optional babysitter. One live Orkie process per GitHub repository; a second start for the same repo refuses to take the lock.

Full CLI and dashboard stories: [feature 08](../spec/feature/08-cli-and-dashboard.md).

## Dashboard

Bound to loopback only (`127.0.0.1`). Default port `8765`.

| View | Use |
|------|-----|
| Agents | Live sessions, bound issue/PR, status, logs (including permission grants) |
| Issues | Claimed vs unclaimed intake issues; session id when one is working |

From the dashboard you can **interrupt** (cancel current turn; claim stays) or **kill** (end session and drop the issue claim). There is no follow-up prompt box in v1.

## Interactive vs non-interactive

Both stdin and stdout must be TTYs for interactive mode. Otherwise Orkie never prompts.

| Situation | Interactive | Non-interactive |
|-----------|-------------|-----------------|
| Missing `.orkie/config.yaml` | Offer default scaffold | Fail hard |
| Missing required GitHub privileges | Prompt (retry / abort) | Fail hard |
| Ctrl-C with live agents | Choose graceful or normal shutdown | Normal shutdown |
| SIGTERM | Normal shutdown | Normal shutdown |

Host administrators typically run under systemd or similar — always non-interactive. Provide config and a valid `GITHUB_TOKEN` before start.

## Shutdown

Both modes delete live ACP sessions and session records, attempt worktree removal, keep local claims, and exit 0.

| Mode | Behavior |
|------|----------|
| **Normal** | Delete sessions now (ACP delete, then SIGKILL after 5s if needed) |
| **Graceful** | Cancel, send wrap-up prompt, wait 20s, then same delete path |

- Interactive Ctrl-C with live agents → choose mode
- No live agents, or SIGTERM / non-interactive SIGINT → normal, no prompt
- Second SIGINT/SIGTERM during shutdown → SIGKILL remaining agent process groups

Sessions are not resumed after restart. Claims survive; orchestration may spawn again for claimed issues.

## Local state

Runtime state is **outside** the project clone:

```text
~/.local/share/orkie/<owner>--<repo>/
```

Includes process lock, intake snapshot, local claims, spawn-failure records, and per-agent logs. Two clones of the same GitHub repo on one machine share this tree. A different OS user or machine gets a separate tree (empty claims).

Layout detail: [feature 02](../spec/feature/02-local-state.md).

## Worktrees

Each session gets a dedicated git worktree under the state tree. Orkie removes it when the session ends and cleans leftovers on the next start. Agents work in that worktree, not necessarily in your main checkout.

## GitHub connector notes

- Orkie **reads** issues (and PRs when the babysitter is on). It does not create labels, comment on issues, or merge PRs in v1.
- Claims are local only; collaborators on GitHub do not see Orkie claim markers.
- Required privileges checklist: [feature 03](../spec/feature/03-connector-interface-and-github.md#required-privileges).
