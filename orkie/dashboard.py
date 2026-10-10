"""Loopback HTML dashboard and control POSTs."""

from __future__ import annotations

import html
import re
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from orkie.orchestration import RuntimeContext
from orkie.state import SpawnFailureRecord


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


def render_index(repo: str, port: int) -> str:
    return _page(
        repo,
        None,
        "<h1>Orkie</h1>"
        f"<p>Repository {html.escape(repo)}</p>"
        f"<p>Dashboard http://127.0.0.1:{port}/</p>"
        '<p><a href="/agents">Agent view</a> · <a href="/issues">Issue view</a></p>',
    )


def render_agents(view: AgentsView) -> str:
    body_parts = ["<h1>Agents</h1>"]
    if not view.sessions:
        body_parts.append("<p>No working sessions.</p>")
    else:
        body_parts.append(
            "<table><tr><th>Config id</th><th>Name</th><th>Session</th>"
            "<th>Work</th><th>Status</th><th>Actions</th></tr>"
        )
        for session in view.sessions:
            body_parts.append(
                "<tr>"
                f"<td>{html.escape(session.agent_id)}</td>"
                f"<td>{html.escape(session.agent_name)}</td>"
                f"<td><a href=\"#session-{html.escape(session.session_id)}\">"
                f"{html.escape(session.session_id)}</a></td>"
                f"<td>{html.escape(session.bound_work)}</td>"
                "<td>working</td>"
                "<td>"
                f'<form method="post" action="/sessions/{html.escape(session.session_id)}/interrupt">'
                '<button type="submit">Interrupt</button></form> '
                f'<form method="post" action="/sessions/{html.escape(session.session_id)}/kill">'
                '<button type="submit">Kill</button></form>'
                "</td></tr>"
            )
        body_parts.append("</table>")
        for session in view.sessions:
            body_parts.append(
                f'<h2 id="session-{html.escape(session.session_id)}">'
                f"Log {html.escape(session.session_id)}</h2>"
            )
            if not session.log_lines:
                body_parts.append("<p>No log lines for this session yet.</p>")
            else:
                escaped = "\n".join(html.escape(line) for line in session.log_lines)
                body_parts.append(f"<pre>{escaped}</pre>")
    body_parts.append("<h2>Spawn failures</h2>")
    if not view.failures:
        body_parts.append("<p>No spawn failures recorded.</p>")
    else:
        body_parts.append(
            "<table><tr><th>Agent</th><th>Work</th><th>Attempt</th>"
            "<th>Released</th><th>Error</th><th>At</th></tr>"
        )
        for failure in view.failures:
            work = (
                f"issue #{failure.issue_number}"
                if failure.issue_number is not None
                else f"PR #{failure.pr_number}"
            )
            cls = ' class="warn"' if failure.released else ""
            note = (
                " local claim dropped after three spawn failures"
                if failure.released
                else ""
            )
            body_parts.append(
                f"<tr{cls}>"
                f"<td>{html.escape(failure.agent_name)} ({html.escape(failure.agent_id)})</td>"
                f"<td>{html.escape(work)}</td>"
                f"<td>{failure.attempt}</td>"
                f"<td>{'yes' if failure.released else 'no'}{html.escape(note)}</td>"
                f"<td>{html.escape(failure.error)}</td>"
                f"<td>{html.escape(failure.at)}</td>"
                "</tr>"
            )
        body_parts.append("</table>")
    return _page(view.repo, view.intake_error, "".join(body_parts))


def render_issues(view: IssuesView) -> str:
    body_parts = [
        "<h1>Issues</h1>",
        f"<p>Repository {html.escape(view.repo)} · branch {html.escape(view.branch)}</p>",
    ]
    if not view.has_snapshot:
        body_parts.append("<p>No intake snapshot yet.</p>")
        return _page(view.repo, view.intake_error, "".join(body_parts))
    if not view.claimed and not view.unclaimed:
        body_parts.append("<p>No intake issues.</p>")
        return _page(view.repo, view.intake_error, "".join(body_parts))
    body_parts.append("<h2>Claimed</h2>")
    body_parts.append(_issue_table(view.claimed))
    body_parts.append("<h2>Unclaimed</h2>")
    body_parts.append(_issue_table(view.unclaimed))
    return _page(view.repo, view.intake_error, "".join(body_parts))


def handle_http(
    ctx: RuntimeContext,
    *,
    method: str,
    path: str,
    referer: str | None,
) -> tuple[int, str, str | None]:
    """Return (status, body, redirect_location)."""
    if method == "GET" and path in {"/", ""}:
        repo = f"{ctx.owner_repo.owner}/{ctx.owner_repo.name}"
        return 200, render_index(repo, ctx.dashboard_port), None
    if method == "GET" and path == "/agents":
        return 200, render_agents(build_agents_view(ctx)), None
    if method == "GET" and path == "/issues":
        return 200, render_issues(build_issues_view(ctx)), None
    match = re.fullmatch(r"/sessions/([^/]+)/(interrupt|kill)", path)
    if method == "POST" and match:
        session_id = match.group(1)
        action = match.group(2)
        if ctx.shutdown_event.is_set() or ctx.prompt_requested.is_set():
            return 503, "shutting down", None
        orchestrator = ctx.orchestrator
        if orchestrator is None:
            return 503, "not ready", None
        with ctx.cycle_lock:
            try:
                if action == "interrupt":
                    orchestrator.interrupt_session(session_id)
                else:
                    orchestrator.kill_session(session_id)
            except KeyError:
                return 404, "unknown session", None
            except RuntimeError:
                return 503, "shutting down", None
        redirect = _safe_redirect(referer)
        return 303, "", redirect
    return 404, "not found", None


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
            status, body, redirect = handle_http(
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
            payload = body.encode("utf-8")
            self.send_response(status)
            content_type = "text/html; charset=utf-8" if status == 200 else "text/plain"
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


def _issue_table(rows: list[IssueRow]) -> str:
    if not rows:
        return "<p>None.</p>"
    parts = [
        "<table><tr><th>Issue</th><th>Title</th><th>Agent</th>"
        "<th>Session</th><th>Warning</th></tr>"
    ]
    for row in rows:
        warn = (
            "local claim dropped after three spawn failures" if row.three_strike else ""
        )
        parts.append(
            "<tr>"
            f"<td>#{row.number}</td>"
            f"<td>{html.escape(row.title)}</td>"
            f"<td>{html.escape(row.agent_id or '')}</td>"
            f"<td>{html.escape(row.session_id or '')}</td>"
            f"<td>{html.escape(warn)}</td>"
            "</tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def _page(repo: str, intake_error: str | None, body: str) -> str:
    banner = ""
    if intake_error:
        banner = (
            f'<p class="error">{html.escape(intake_error)} '
            "(as of last failed poll)</p>"
        )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<title>Orkie</title>"
        "<style>"
        "body{font-family:sans-serif;margin:1.5rem}"
        "nav a{margin-right:1rem}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ccc;padding:0.4rem;text-align:left}"
        "tr.warn{background:#fff3cd}"
        ".error{color:#a40000}"
        "form{display:inline}"
        "</style></head><body>"
        "<nav>"
        '<a href="/">Orkie</a>'
        '<a href="/agents">Agents</a>'
        '<a href="/issues">Issues</a>'
        f"<span>{html.escape(repo)}</span>"
        "</nav>"
        f"{banner}{body}"
        "</body></html>"
    )
