# Getting started

## What you need

- Python 3.11+
- macOS or Linux (`git` on `PATH`)
- A clone of the GitHub repository Orkie should manage
- A GitHub token in `GITHUB_TOKEN` (classic or fine-grained) that can **read the repository** and **read open issues**. If you enable the PR babysitter later, the token must also **read open pull requests**.

Orkie never stores tokens under `.orkie/`.

## Install

From a checkout of Orkie:

```bash
pip install -e .
```

Confirm the console script:

```bash
orkie --help
```

## First run

1. Export a token:

   ```bash
   export GITHUB_TOKEN=ghp_…
   ```

2. Start Orkie from inside the target project (or pass its path):

   ```bash
   cd /path/to/your-project
   orkie
   ```

3. If `.orkie/config.yaml` is missing and the terminal is interactive, Orkie offers a default scaffold. Accept to create it, or reject and write your own. Non-interactive runs (no TTY) fail immediately when config is missing — no prompt, no file write.

4. On success, Orkie prints the dashboard URL (default `http://127.0.0.1:8765/`) and enters the poll loop.

The default scaffold watches open issues labeled `orkie` and spawns one OpenCode ACP worker at a time. Customize labels, agents, and prompts under [Configuration](configuration.md).

## Mark work for Orkie

Create or open a GitHub issue and add at least one label listed in `issue_labels` (default: `orkie`). Orkie claims labeled open issues locally and spawns an agent when session caps allow. It does not add claim markers on GitHub.

## Next

- Tune [`.orkie/config.yaml`](configuration.md)
- Day-to-day [CLI, dashboard, and shutdown](operation.md)
