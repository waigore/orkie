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

    def fake_run(command: list[str]) -> str:
        joined = " ".join(command)
        if "fetch" in command:
            return ""
        if "refs/remotes/origin/HEAD" in joined:
            return "origin/main\n"
        if "symbolic-ref" in command:
            return "main\n"
        if "checkout" in command or "reset" in command:
            return ""
        if "rev-parse" in command:
            return "abc123\n"
        if "worktree" in command:
            return ""
        raise WorktreeError(f"unexpected: {command}")

    with mock.patch.object(service, "_run", side_effect=fake_run):
        path = service.create("s1")
    assert path.name == "s1"
    assert service.resolve_base() == ("abc123", "main")
