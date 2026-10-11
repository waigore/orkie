"""State store I/O and lock tests."""

from __future__ import annotations

from pathlib import Path

from orkie.state import (
    ClaimRecord,
    Snapshot,
    SnapshotIssue,
    SpawnFailureRecord,
    StateStore,
    default_state_root,
)


def test_default_state_root_uses_local_share(tmp_path: Path) -> None:
    root = default_state_root("acme", "demo", home=tmp_path)
    assert root == tmp_path / ".local" / "share" / "orkie" / "acme--demo"


def test_claims_round_trip_in_memory(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    claims = [ClaimRecord(agent_id="worker", issue_number=1, claimed_at="2026-01-01T00:00:00Z")]
    store.save_claims(claims)
    assert store.load_claims() == claims
    assert not (tmp_path / "claims").exists()


def test_missing_claims_is_empty(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    assert store.load_claims() == []


def test_legacy_claims_file_is_scrubbed_not_loaded(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    (tmp_path / "claims").write_text('{"claims":[{"agent_id":"x","issue_number":1,"claimed_at":"t"}]}', encoding="utf-8")
    store.ensure_layout()
    assert not (tmp_path / "claims").exists()
    assert store.load_claims() == []


def test_snapshot_and_failures_in_memory(tmp_path: Path) -> None:
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
    assert not (tmp_path / "snapshot").exists()
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
    assert not (tmp_path / "spawn_failures").exists()


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


def test_acquire_lock_and_release_unlinks(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.acquire_lock()
    assert (tmp_path / "lock").exists()
    store.release_lock()
    assert not (tmp_path / "lock").exists()


def test_stale_lock_pid_allows_acquire(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    # Unlikely to be a live pid on the test host.
    (tmp_path / "lock").write_text(
        '{"pid": 2147483646, "started_at": "2026-01-01T00:00:00Z"}', encoding="utf-8"
    )
    store.acquire_lock()
    store.release_lock()
    assert not (tmp_path / "lock").exists()
