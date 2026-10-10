"""Create and remove per-session detached git worktrees."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class WorktreeError(Exception):
    """Git worktree operation failed."""


class WorktreeService:
    def __init__(self, state_root: Path, project_root: Path) -> None:
        self._state_root = state_root
        self._project_root = project_root
        self._base: tuple[str, str] | None = None

    def resolve_base(self) -> tuple[str, str]:
        if self._base is not None:
            return self._base
        try:
            sha = self._run(
                ["git", "-C", str(self._project_root), "rev-parse", "HEAD"]
            ).strip()
        except WorktreeError:
            raise
        branch_or_detached = "detached"
        try:
            branch = self._run(
                [
                    "git",
                    "-C",
                    str(self._project_root),
                    "symbolic-ref",
                    "--short",
                    "-q",
                    "HEAD",
                ]
            ).strip()
            if branch:
                branch_or_detached = branch
        except WorktreeError:
            branch_or_detached = "detached"
        self._base = (sha, branch_or_detached)
        return self._base

    def create(self, session_id: str) -> Path:
        commit_sha, _ = self.resolve_base()
        path = self._state_root / "worktrees" / session_id
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._run(
                [
                    "git",
                    "-C",
                    str(self._project_root),
                    "worktree",
                    "add",
                    "--detach",
                    str(path),
                    commit_sha,
                ]
            )
        except WorktreeError:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
            raise
        return path

    def remove(self, worktree_path: Path) -> None:
        try:
            common = self._run(
                [
                    "git",
                    "-C",
                    str(worktree_path),
                    "rev-parse",
                    "--git-common-dir",
                ]
            ).strip()
            git_dir = Path(common)
            if not git_dir.is_absolute():
                git_dir = (worktree_path / git_dir).resolve()
            self._run(
                [
                    "git",
                    "--git-dir",
                    str(git_dir),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree_path),
                ]
            )
        except WorktreeError as exc:
            print(f"worktree remove failed for {worktree_path}: {exc}", file=sys.stderr)
            try:
                if worktree_path.exists():
                    shutil.rmtree(worktree_path)
            except OSError as rmtree_exc:
                print(
                    f"worktree rmtree failed for {worktree_path}: {rmtree_exc}",
                    file=sys.stderr,
                )

    def remove_leftovers(self) -> None:
        root = self._state_root / "worktrees"
        if not root.exists():
            return
        for child in root.iterdir():
            if child.is_dir():
                self.remove(child)

    def _run(self, command: list[str]) -> str:
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise WorktreeError("git executable not found on PATH") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise WorktreeError(detail or str(exc)) from exc
        return completed.stdout
