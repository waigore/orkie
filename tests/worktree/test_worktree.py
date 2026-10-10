"""Worktree service integration-style offline tests with temp git repos."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orkie.worktree import WorktreeError, WorktreeService


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "README").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
    )


@pytest.mark.integration
def test_create_and_remove_worktree(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    _init_repo(project)
    state = tmp_path / "state"
    state.mkdir()
    service = WorktreeService(state, project)
    sha, branch = service.resolve_base()
    assert len(sha) >= 7
    assert branch != ""
    path = service.create("sess-1")
    assert path.exists()
    service.remove(path)
    assert not path.exists()


@pytest.mark.integration
def test_remove_discovers_git_dir_from_worktree(tmp_path: Path) -> None:
    """Removal must not require the creating process's project_root (ADR 008)."""
    project = tmp_path / "repo"
    project.mkdir()
    _init_repo(project)
    state = tmp_path / "state"
    state.mkdir()
    creator = WorktreeService(state, project)
    path = creator.create("sess-2")
    assert path.exists()
    other_root = tmp_path / "other-clone"
    other_root.mkdir()
    remover = WorktreeService(state, other_root)
    remover.remove(path)
    assert not path.exists()
    listed = subprocess.run(
        ["git", "-C", str(project), "worktree", "list", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert str(path) not in listed
