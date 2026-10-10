"""Orchestrator shutdown helpers."""

from __future__ import annotations

import threading
from pathlib import Path

from orkie.acp.fake import FakeAcpClient
from orkie.config import (
    AgentConfig,
    BabysitterConfig,
    Config,
    ConnectorConfig,
    Trigger,
)
from orkie.connectors.fake import FakeConnector
from orkie.connectors.types import Issue, OwnerRepo
from orkie.intake import Intake
from orkie.orchestration import Orchestrator, RuntimeContext, WRAP_UP_PROMPT
from orkie.state import StateStore
from tests.orchestration.test_cycle import StubWorktree, _ctx


def test_wrap_up_and_end_all(tmp_path: Path) -> None:
    issue = Issue(1, "t", "", "u", "open", ["orkie"])
    ctx = _ctx(tmp_path, issues=[issue])
    assert ctx.orchestrator is not None
    with ctx.cycle_lock:
        ctx.orchestrator.run_cycle()
    assert ctx.sessions
    ctx.orchestrator.wrap_up_sessions()
    assert isinstance(ctx.acp_client, FakeAcpClient)
    session_id = next(iter(ctx.sessions))
    assert WRAP_UP_PROMPT in ctx.acp_client.sessions[session_id].prompts
    ctx.orchestrator.end_all_sessions()
    assert ctx.sessions == {}
    ctx.orchestrator.remove_all_worktrees()
    ctx.orchestrator.request_shutdown()
    assert ctx.shutdown_event.is_set()
