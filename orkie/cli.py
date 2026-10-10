"""Process entrypoint: argparse, bootstrap, poll loop, shutdown."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Literal

from orkie.acp import StdioAcpClient
from orkie.config import ConfigError, config_path, load_config, write_default_scaffold
from orkie.connectors import (
    ConnectorError,
    build_connector,
    required_privileges,
    resolve_github_repo,
)
from orkie.dashboard import (
    bind_dashboard,
    start_bound_dashboard,
    stop_dashboard,
)
from orkie.intake import Intake
from orkie.orchestration import Orchestrator, RuntimeContext
from orkie.state import StateError, StateStore, default_state_root
from orkie.worktree import WorktreeError, WorktreeService

SHUTDOWN_PROMPT = """\
Live agent sessions are still running. Shut down how?
  [g] graceful — ask agents to wrap up (20s), then delete sessions
  [n] normal — delete sessions now
"""

WRAP_UP_WAIT_SECONDS = 20
POLL_SLICE_SECONDS = 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        ctx = run_bootstrap(args.project, port=args.port)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1
    start_bound_dashboard(ctx)
    print(f"http://127.0.0.1:{ctx.dashboard_port}/")
    install_signal_handlers(ctx)
    run_poll_loop(ctx)
    mode = choose_shutdown_mode(ctx)
    return shutdown(ctx, mode=mode)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="orkie",
        description=(
            "Orkie orchestrator. Process lock requires a Unix-like host (macOS/Linux)."
        ),
    )
    parser.add_argument(
        "project",
        nargs="?",
        type=Path,
        default=None,
        help="Git project root (default: current directory)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Dashboard port override",
    )
    return parser.parse_args(argv)


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def resolve_project_root(project: Path | None) -> Path:
    root = (project if project is not None else Path.cwd()).resolve()
    if not (root / ".git").exists():
        # Also accept worktrees where .git is a file.
        git_path = root / ".git"
        if not git_path.exists():
            print(f"not a Git working tree: {root}", file=sys.stderr)
            raise SystemExit(1)
    return root


def run_bootstrap(project: Path | None, *, port: int | None) -> RuntimeContext:
    # 1. Resolve project root
    project_root = resolve_project_root(project)
    # 2. Locate config
    path = config_path(project_root)
    if not path.exists():
        if not is_interactive():
            print(
                f"missing required config: {path}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        answer = input("Create default .orkie/config.yaml? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("configuration is required", file=sys.stderr)
            raise SystemExit(1)
        write_default_scaffold(project_root)
    # 3. Load and validate
    try:
        config = load_config(project_root)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    # 4. Resolve repository
    try:
        owner_repo = resolve_github_repo(project_root, config.connector.repo)
    except ConnectorError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    state_root = default_state_root(owner_repo.owner, owner_repo.name)
    worktree = WorktreeService(state_root, project_root)
    # 5. Resolve start checkout
    try:
        start_commit_sha, start_branch = worktree.resolve_base()
    except WorktreeError as exc:
        print(f"git resolve failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    # 6–7. Lock and prepare state
    token = os.environ.get("GITHUB_TOKEN", "")
    store = StateStore(state_root, github_token=token or None)
    try:
        store.acquire_lock()
    except StateError as exc:
        print(
            f"another Orkie is running for {owner_repo.owner}/{owner_repo.name}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    try:
        store.ensure_layout()
        store.load_claims()
        store.load_snapshot()
        store.load_spawn_failures()
        store.delete_sessions()
        worktree.remove_leftovers()
    except StateError as exc:
        store.release_lock()
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    # 8–10. Token, connector, privileges
    connector = build_connector(config, token, owner_repo)
    required = required_privileges(config)
    while True:
        probe = connector.probe_privileges(required)
        if not probe.missing_required:
            break
        gaps = ", ".join(sorted(p.value for p in probe.missing_required))
        print(f"missing required privileges: {gaps}", file=sys.stderr)
        if not is_interactive():
            store.release_lock()
            raise SystemExit(1)
        answer = input("Retry privilege check / abort? [r/a] ").strip().lower()
        if answer in {"a", "abort"}:
            store.release_lock()
            raise SystemExit(1)
        token = os.environ.get("GITHUB_TOKEN", "")
        store.set_github_token(token or None)
        connector = build_connector(config, token, owner_repo)
    dashboard_port = port if port is not None else config.dashboard_port
    shutdown_event = threading.Event()
    immediate_kill = threading.Event()
    prompt_requested = threading.Event()
    cycle_lock = threading.Lock()
    intake = Intake(config, connector, store)
    acp_client = StdioAcpClient()
    ctx = RuntimeContext(
        project_root=project_root,
        state_root=state_root,
        config=config,
        owner_repo=owner_repo,
        connector=connector,
        store=store,
        worktree=worktree,
        intake=intake,
        acp_client=acp_client,
        shutdown_event=shutdown_event,
        immediate_kill=immediate_kill,
        prompt_requested=prompt_requested,
        cycle_lock=cycle_lock,
        start_commit_sha=start_commit_sha,
        start_branch_or_detached=start_branch,
        dashboard_port=dashboard_port,
        github_token=token,
    )
    ctx.orchestrator = Orchestrator(ctx)
    # 11. Bind dashboard
    try:
        bind_dashboard(ctx)
    except OSError as exc:
        store.release_lock()
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    return ctx


def install_signal_handlers(ctx: RuntimeContext) -> None:
    interactive = is_interactive()

    def handle_sigterm(_signum: int, _frame: object) -> None:
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            ctx.immediate_kill.set()
            return
        ctx.shutdown_event.set()

    def handle_sigint(_signum: int, _frame: object) -> None:
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            ctx.immediate_kill.set()
            return
        if interactive and ctx.sessions:
            ctx.prompt_requested.set()
            return
        ctx.shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigint)


def run_poll_loop(ctx: RuntimeContext) -> None:
    orchestrator = ctx.orchestrator
    assert orchestrator is not None
    while not ctx.shutdown_event.is_set() and not ctx.prompt_requested.is_set():
        with ctx.cycle_lock:
            orchestrator.run_cycle()
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            break
        wait_poll_interval(ctx)


def wait_poll_interval(ctx: RuntimeContext) -> None:
    remaining = ctx.config.poll_interval_seconds
    while remaining > 0:
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            return
        slice_seconds = min(POLL_SLICE_SECONDS, remaining)
        time.sleep(slice_seconds)
        remaining -= slice_seconds


def choose_shutdown_mode(ctx: RuntimeContext) -> Literal["normal", "graceful"]:
    if not ctx.prompt_requested.is_set():
        return "normal"
    if not ctx.sessions:
        ctx.shutdown_event.set()
        return "normal"
    if not is_interactive():
        ctx.shutdown_event.set()
        return "normal"
    while True:
        print(SHUTDOWN_PROMPT, end="", file=sys.stderr)
        try:
            answer = input().strip().lower()
        except EOFError:
            ctx.shutdown_event.set()
            return "normal"
        if ctx.immediate_kill.is_set():
            ctx.shutdown_event.set()
            return "normal"
        if answer == "g":
            ctx.shutdown_event.set()
            return "graceful"
        if answer == "n":
            ctx.shutdown_event.set()
            return "normal"


def shutdown(ctx: RuntimeContext, *, mode: Literal["normal", "graceful"]) -> int:
    orchestrator = ctx.orchestrator
    assert orchestrator is not None
    ctx.shutdown_event.set()
    if mode == "graceful":
        orchestrator.wrap_up_sessions()
        deadline = time.monotonic() + WRAP_UP_WAIT_SECONDS
        while time.monotonic() < deadline:
            if ctx.immediate_kill.is_set():
                break
            time.sleep(0.1)
        if ctx.immediate_kill.is_set():
            for handle in list(ctx.sessions.values()):
                try:
                    ctx.acp_client.force_kill(handle)
                except Exception:  # noqa: BLE001
                    pass
    orchestrator.end_all_sessions()
    orchestrator.remove_all_worktrees()
    stop_dashboard(ctx)
    ctx.store.delete_sessions()
    ctx.store.release_lock()
    return 0
