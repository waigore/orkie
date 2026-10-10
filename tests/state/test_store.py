"""State store I/O and lock tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from orkie.state import (
    ClaimRecord,
    Snapshot,
    SnapshotIssue,
    SpawnFailureRecord,
    StateError,
    StateStore,
    default_state_root,
)


def test_default_state_root_uses_local_share(tmp_path: Path) -> None:
    root = default_state_root("acme", "demo", home=tmp_path)
    assert root == tmp_path / ".local" / "share" / "orkie" / "acme--demo"


def test_claims_round_trip(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    claims = [ClaimRecord(agent_id="worker", issue_number=1, claimed_at="2026-01-01T00:00:00Z")]
    store.save_claims(claims)
    assert store.load_claims() == claims


def test_missing_claims_is_empty(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    assert store.load_claims() == []


def test_corrupt_claims_raises(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    (tmp_path / "claims").write_text("{not json", encoding="utf-8")
    with pytest.raises(StateError, match="claims"):
        store.load_claims()


def test_snapshot_and_failures(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    snap = Snapshot(
        fetched_at="2026-01-01T00:00:00Z",
        issues=[
            SnapshotIssue(
                number=1,
                title="t",
                body="",
                url="u",
                state="open",
                labels=["orkie"],
            )
        ],
    )
    store.save_snapshot(snap)
    assert store.load_snapshot() == snap
    failures = [
        SpawnFailureRecord(
            agent_id="worker",
            agent_name="Worker",
            issue_number=1,
            pr_number=None,
            attempt=1,
            released=False,
            error="boom",
            at="2026-01-01T00:00:00Z",
        )
    ]
    store.save_spawn_failures(failures)
    assert store.load_spawn_failures() == failures


def test_delete_sessions_without_parsing(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    (tmp_path / "sessions").write_text("not-json", encoding="utf-8")
    store.delete_sessions()
    assert not (tmp_path / "sessions").exists()


def test_append_log_redacts_token(tmp_path: Path) -> None:
    store = StateStore(tmp_path, github_token="secret-token")
    store.ensure_layout()
    store.append_log("worker", "token=secret-token", session_id="abc", issue_number=1)
    text = store.read_log("worker")
    assert "secret-token" not in text
    assert "***" in text
    assert "session_id=abc" in text
    assert "issue=1" in text


def test_set_github_token_refreshes_redaction(tmp_path: Path) -> None:
    store = StateStore(tmp_path, github_token=None)
    store.ensure_layout()
    store.set_github_token("new-secret-token")
    store.append_log(
        "worker", "token=new-secret-token", session_id="abc", issue_number=1
    )
    text = store.read_log("worker")
    assert "new-secret-token" not in text
    assert "***" in text


def test_acquire_lock_and_release(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.acquire_lock()
    store.release_lock()
    assert (tmp_path / "lock").exists()
