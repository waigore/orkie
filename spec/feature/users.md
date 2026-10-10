# Users

Canonical actors for the feature specs. Feature files list **use cases** for these users; they should not redefine who the user is. When a new actor appears, add them here first.

## People

| User | Who they are |
|------|----------------|
| Project maintainer | Owns the repository's `.orkie/` config: agents, triggers, prompts, caps, and whether the babysitter is enabled. |
| Architect / agent author | Writes or reviews project-owned roles and prompts. Expects Orkie not to hard-code a role catalog beyond the optional default scaffold. |
| Operator | Runs Orkie against a project (CLI path or cwd), supplies `GITHUB_TOKEN`, and leaves the process running or stops it. Includes first-time setup, continuous runs, and large-repo operation. |
| Dashboard user | Uses the local web dashboard to monitor agents and issues, read logs, and interrupt or kill sessions without stopping Orkie. |
| Collaborator on GitHub | Works in the same GitHub repository; sees Orkie claim labels and issue/PR activity but does not run Orkie. |
| Future integrator | Implements another task-tracker connector against the abstract interface without rewriting core orchestration. |
| Host administrator | Runs Orkie under a process supervisor (for example systemd), always non-interactive. |

## System actors

These are not people; features still name them in use cases when the behavior is machine-to-machine.

| Actor | Who they are |
|-------|----------------|
| Continuous Orkie process | The long-running Orkie instance after successful bootstrap: intake, orchestration, and optional babysitter. |
| Orchestration | The orchestration loop that claims work, spawns and stops sessions, and applies swarm-fit rules. |
| Intake | The intake poll loop that refreshes tracker state and produces deltas for orchestration. |
