"""Worktree service integration-style offline tests with temp git repos."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orkie.worktree import WorktreeError, WorktreeService


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _configure_identity(path: Path) -> None:
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _init_bare_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """Return (project_clone, bare_origin). Default branch is main."""
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _configure_identity(seed)
    (seed / "README").write_text("hi", encoding="utf-8")
    _git(seed, "add", "README")
    _git(seed, "commit", "-m", "init")

    bare = tmp_path / "origin.git"
    _git(tmp_path, "clone", "--bare", str(seed), str(bare))
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")

    project = tmp_path / "repo"
    _git(tmp_path, "clone", str(bare), str(project))
    _configure_identity(project)
    return project, bare


def _commit_on_bare(bare: Path, message: str, content: str) -> str:
    """Push a new commit onto bare main via a temporary clone; return tip sha."""
    helper = bare.parent / f"helper-{message.replace(' ', '-')}"
    _git(bare.parent, "clone", str(bare), str(helper))
    _configure_identity(helper)
    (helper / "README").write_text(content, encoding="utf-8")
    _git(helper, "add", "README")
    _git(helper, "commit", "-m", message)
    _git(helper, "push", "origin", "main")
    return _git(helper, "rev-parse", "HEAD")


@pytest.mark.integration
def test_create_and_remove_worktree(tmp_path: Path) -> None:
    project, _bare = _init_bare_and_clone(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    service = WorktreeService(state, project)
    sha, branch = service.resolve_base()
    assert len(sha) >= 7
    assert branch == "main"
    path = service.create("sess-1")
    assert path.exists()
    service.remove(path)
    assert not path.exists()


@pytest.mark.integration
def test_remove_discovers_git_dir_from_worktree(tmp_path: Path) -> None:
    """Removal must not require the creating process's project_root (ADR 008)."""
    project, _bare = _init_bare_and_clone(tmp_path)
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
    listed = _git(project, "worktree", "list", "--porcelain")
    assert str(path) not in listed


@pytest.mark.integration
def test_create_syncs_to_remote_tip_and_discards_local_commit(tmp_path: Path) -> None:
    project, bare = _init_bare_and_clone(tmp_path)
    remote_tip = _commit_on_bare(bare, "remote advance", "from-remote")

    (project / "README").write_text("local-only", encoding="utf-8")
    _git(project, "add", "README")
    _git(project, "commit", "-m", "local only")
    local_tip = _git(project, "rev-parse", "HEAD")
    assert local_tip != remote_tip

    state = tmp_path / "state"
    state.mkdir()
    service = WorktreeService(state, project)
    path = service.create("sess-sync")
    worktree_tip = _git(path, "rev-parse", "HEAD")
    project_tip = _git(project, "rev-parse", "HEAD")
    assert worktree_tip == remote_tip
    assert project_tip == remote_tip
    assert (path / "README").read_text(encoding="utf-8") == "from-remote"
    sha, branch = service.resolve_base()
    assert sha == remote_tip
    assert branch == "main"
    service.remove(path)


@pytest.mark.integration
def test_create_reattaches_detached_head_to_origin_default(tmp_path: Path) -> None:
    project, bare = _init_bare_and_clone(tmp_path)
    _git(project, "checkout", "--detach", "HEAD")
    detached_check = subprocess.run(
        ["git", "symbolic-ref", "-q", "HEAD"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert detached_check.returncode != 0

    remote_tip = _commit_on_bare(bare, "after detach", "reattach-content")

    state = tmp_path / "state"
    state.mkdir()
    service = WorktreeService(state, project)
    path = service.create("sess-detached")
    assert _git(project, "symbolic-ref", "--short", "HEAD") == "main"
    assert _git(path, "rev-parse", "HEAD") == remote_tip
    assert _git(project, "rev-parse", "HEAD") == remote_tip
    _, branch = service.resolve_base()
    assert branch == "main"
    service.remove(path)


@pytest.mark.integration
def test_create_fails_without_origin(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    _git(project, "init", "-b", "main")
    _configure_identity(project)
    (project / "README").write_text("hi", encoding="utf-8")
    _git(project, "add", "README")
    _git(project, "commit", "-m", "init")

    state = tmp_path / "state"
    state.mkdir()
    service = WorktreeService(state, project)
    with pytest.raises(WorktreeError):
        service.create("sess-no-origin")
    assert not (state / "worktrees" / "sess-no-origin").exists()
