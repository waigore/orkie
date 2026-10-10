"""Worktree resolve_base with mocked git."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from orkie.worktree import WorktreeError, WorktreeService


def test_resolve_base_branch(tmp_path: Path) -> None:
    service = WorktreeService(tmp_path, tmp_path)

    def fake_run(command: list[str]) -> str:
        if "rev-parse" in command:
            return "abcdef\n"
        if "symbolic-ref" in command:
            return "main\n"
        raise WorktreeError("unexpected")

    with mock.patch.object(service, "_run", side_effect=fake_run):
        sha, branch = service.resolve_base()
    assert sha == "abcdef"
    assert branch == "main"


def test_resolve_base_detached(tmp_path: Path) -> None:
    service = WorktreeService(tmp_path, tmp_path)

    def fake_run(command: list[str]) -> str:
        if "rev-parse" in command:
            return "abcdef\n"
        raise WorktreeError("detached")

    with mock.patch.object(service, "_run", side_effect=fake_run):
        sha, branch = service.resolve_base()
    assert branch == "detached"


def test_create_success(tmp_path: Path) -> None:
    service = WorktreeService(tmp_path, tmp_path)
    service._base = ("abc", "main")
    with mock.patch.object(service, "_run", return_value=""):
        path = service.create("s1")
    assert path.name == "s1"
