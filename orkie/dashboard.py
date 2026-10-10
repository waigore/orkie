"""Loopback HTML dashboard and control POSTs."""

from __future__ import annotations

import mimetypes
import re
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from jinja2 import Environment, PackageLoader, select_autoescape

from orkie.orchestration import RuntimeContext
from orkie.state import SpawnFailureRecord

_ENV = Environment(
    loader=PackageLoader("orkie", "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


@dataclass(frozen=True, slots=True)
class SessionView:
    session_id: str
    agent_id: str
    agent_name: str
    bound_work: str
    log_lines: list[str]


@dataclass(frozen=True, slots=True)
class AgentsView:
    repo: str
    intake_error: str | None
    sessions: list[SessionView]
    failures: list[SpawnFailureRecord]


@dataclass(frozen=True, slots=True)
class IssueRow:
    number: int
    title: str
    claimed: bool
    agent_id: str | None
    session_id: str | None
    three_strike: bool


@dataclass(frozen=True, slots=True)
class IssuesView:
    repo: str
    branch: str
    intake_error: str | None
    has_snapshot: bool
    claimed: list[IssueRow]
    unclaimed: list[IssueRow]


def build_agents_view(ctx: RuntimeContext) -> AgentsView:
    repo = f"{ctx.owner_repo.owner}/{ctx.owner_repo.name}"
    name_by_id = {agent.id: agent.name for agent in ctx.config.agents}
    if ctx.config.babysitter.enabled and ctx.config.babysitter.id:
        name_by_id[ctx.config.babysitter.id] = ctx.config.babysitter.name or ctx.config.babysitter.id
    sessions: list[SessionView] = []
    for session_id, handle in ctx.sessions.items():
        if handle.issue_number is not None:
            bound = f"issue #{handle.issue_number}"
        else:
            bound = f"PR #{handle.pr_number}"
        log_text = ctx.store.read_log(handle.agent_id)
        filtered = [
            line
            for line in log_text.splitlines()
            if f"session_id={session_id}" in line
        ][-200:]
        sessions.append(
            SessionView(
                session_id=session_id,
                agent_id=handle.agent_id,
                agent_name=name_by_id.get(handle.agent_id, handle.agent_id),
                bound_work=bound,
                log_lines=filtered,
            )
        )
    failures = list(reversed(ctx.store.load_spawn_failures()))
    return AgentsView(
        repo=repo,
        intake_error=ctx.intake.last_error,
        sessions=sessions,
        failures=failures,
    )


def build_issues_view(ctx: RuntimeContext) -> IssuesView:
    repo = f"{ctx.owner_repo.owner}/{ctx.owner_repo.name}"
    snapshot = ctx.store.load_snapshot()
    claims = {claim.issue_number: claim for claim in ctx.store.load_claims()}
    session_by_issue: dict[int, str] = {}
    for session_id, handle in ctx.sessions.items():
        if handle.issue_number is not None:
            session_by_issue[handle.issue_number] = session_id
    failures = ctx.store.load_spawn_failures()
    three_strike = {
        failure.issue_number
        for failure in failures
        if failure.issue_number is not None and failure.attempt == 3
    }
    claimed_rows: list[IssueRow] = []
    unclaimed_rows: list[IssueRow] = []
    if snapshot is not None:
        for issue in snapshot.issues:
            claim = claims.get(issue.number)
            row = IssueRow(
                number=issue.number,
                title=issue.title,
                claimed=claim is not None,
                agent_id=claim.agent_id if claim is not None else None,
                session_id=session_by_issue.get(issue.number),
                three_strike=issue.number in three_strike,
            )
            if claim is not None:
                claimed_rows.append(row)
            else:
                unclaimed_rows.append(row)
    return IssuesView(
        repo=repo,
        branch=ctx.start_branch_or_detached,
        intake_error=ctx.intake.last_error,
        has_snapshot=snapshot is not None,
        claimed=claimed_rows,
        unclaimed=unclaimed_rows,
    )


def render_template(name: str, **context: Any) -> str:
    return _ENV.get_template(name).render(**context)


def render_index(repo: str, port: int) -> str:
    return render_template(
        "index.html",
        repo=repo,
        port=port,
        intake_error=None,
    )


def render_agents(view: AgentsView) -> str:
    return render_template(
        "agents.html",
        view=view,
        repo=view.repo,
        intake_error=view.intake_error,
    )


def render_issues(view: IssuesView) -> str:
    return render_template(
        "issues.html",
        view=view,
        repo=view.repo,
        intake_error=view.intake_error,
    )


def handle_http(
    ctx: RuntimeContext,
    *,
    method: str,
    path: str,
    referer: str | None,
) -> tuple[int, str | bytes, str | None, str]:
    """Return (status, body, redirect_location, content_type)."""
    if method == "GET" and path.startswith("/static/"):
        return _serve_static(path.removeprefix("/static/"))
    if method == "GET" and path in {"/", ""}:
        repo = f"{ctx.owner_repo.owner}/{ctx.owner_repo.name}"
        return 200, render_index(repo, ctx.dashboard_port), None, "text/html; charset=utf-8"
    if method == "GET" and path == "/agents":
        return (
            200,
            render_agents(build_agents_view(ctx)),
            None,
            "text/html; charset=utf-8",
        )
    if method == "GET" and path == "/issues":
        return (
            200,
            render_issues(build_issues_view(ctx)),
            None,
            "text/html; charset=utf-8",
        )
    match = re.fullmatch(r"/sessions/([^/]+)/(interrupt|kill)", path)
    if method == "POST" and match:
        session_id = match.group(1)
        action = match.group(2)
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            return 503, "shutting down", None, "text/plain; charset=utf-8"
        orchestrator = ctx.orchestrator
        if orchestrator is None:
            return 503, "not ready", None, "text/plain; charset=utf-8"
        with ctx.cycle_lock:
            try:
                if action == "interrupt":
                    orchestrator.interrupt_session(session_id)
                else:
                    orchestrator.kill_session(session_id)
            except KeyError:
                return 404, "unknown session", None, "text/plain; charset=utf-8"
            except RuntimeError:
                return 503, "shutting down", None, "text/plain; charset=utf-8"
        redirect = _safe_redirect(referer)
        return 303, "", redirect, "text/plain; charset=utf-8"
    return 404, "not found", None, "text/plain; charset=utf-8"


def start_dashboard_thread(ctx: RuntimeContext) -> threading.Thread:
    server = _bound_server(ctx)
    ctx.dashboard_server = server

    def serve() -> None:
        server.serve_forever(poll_interval=0.5)

    thread = threading.Thread(target=serve, name="orkie-dashboard", daemon=True)
    thread.start()
    ctx.dashboard_thread = thread
    return thread


def bind_dashboard(ctx: RuntimeContext) -> None:
    """Bind during bootstrap before the loop starts."""
    server = _bound_server(ctx)
    ctx.dashboard_server = server


def start_bound_dashboard(ctx: RuntimeContext) -> threading.Thread:
    server = ctx.dashboard_server
    if not isinstance(server, ThreadingHTTPServer):
        raise RuntimeError("dashboard not bound")

    def serve() -> None:
        server.serve_forever(poll_interval=0.5)

    thread = threading.Thread(target=serve, name="orkie-dashboard", daemon=True)
    thread.start()
    ctx.dashboard_thread = thread
    return thread


def stop_dashboard(ctx: RuntimeContext) -> None:
    server = ctx.dashboard_server
    if isinstance(server, ThreadingHTTPServer):
        server.shutdown()
        server.server_close()
    thread = ctx.dashboard_thread
    if thread is not None:
        thread.join(timeout=5)


def _bound_server(ctx: RuntimeContext) -> ThreadingHTTPServer:
    handler = _make_handler(ctx)
    try:
        return ThreadingHTTPServer(("127.0.0.1", ctx.dashboard_port), handler)
    except OSError as exc:
        raise OSError(
            f"dashboard port in use: 127.0.0.1:{ctx.dashboard_port}"
        ) from exc


def _make_handler(ctx: RuntimeContext) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            status, body, redirect, content_type = handle_http(
                ctx,
                method=method,
                path=parsed.path,
                referer=self.headers.get("Referer"),
            )
            if redirect is not None:
                self.send_response(status)
                self.send_header("Location", redirect)
                self.end_headers()
                return
            payload = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    return Handler


def _safe_redirect(referer: str | None) -> str:
    if not referer:
        return "/agents"
    parsed = urlparse(referer)
    if parsed.path in {"/agents", "/issues"}:
        return parsed.path
    return "/agents"


def _serve_static(rel: str) -> tuple[int, str | bytes, str | None, str]:
    rel = unquote(rel).lstrip("/")
    parts = Path(rel).parts
    if not parts or ".." in parts or any(part.startswith("/") for part in parts):
        return 404, "not found", None, "text/plain; charset=utf-8"
    candidate = resources.files("orkie").joinpath("static", *parts)
    if not candidate.is_file():
        return 404, "not found", None, "text/plain; charset=utf-8"
    data = candidate.read_bytes()
    content_type, _ = mimetypes.guess_type(parts[-1])
    if content_type is None:
        content_type = "application/octet-stream"
    if content_type.startswith("text/"):
        content_type = f"{content_type}; charset=utf-8"
    return 200, data, None, content_type
