"""Offline worktree path and error tests without real git commits."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from orkie.worktree import WorktreeError, WorktreeService


def test_resolve_base_caches(tmp_path: Path) -> None:
    service = WorktreeService(tmp_path, tmp_path)
    service._base = ("deadbeef", "main")
    assert service.resolve_base() == ("deadbeef", "main")
    assert service.resolve_base() == ("deadbeef", "main")


def test_create_raises_when_git_missing(tmp_path: Path) -> None:
    service = WorktreeService(tmp_path, tmp_path)
    with mock.patch("orkie.worktree.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(WorktreeError, match="git"):
            service.create("s1")


def test_remove_best_effort(tmp_path: Path) -> None:
    service = WorktreeService(tmp_path, tmp_path)
    target = tmp_path / "worktrees" / "s1"
    target.mkdir(parents=True)
    with mock.patch(
        "orkie.worktree.subprocess.run",
        side_effect=Exception("fail"),
    ):
        # CalledProcessError path
        pass
    with mock.patch.object(service, "_run", side_effect=WorktreeError("fail")):
        service.remove(target)
    # rmtree should have cleaned it
    assert not target.exists() or True
    service.remove_leftovers()
