"""Unit tests for patch_apply_safe — apply, gate, rollback."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import ok
from mcp_phone_controll.domain.usecases.patch_safe import (
    PatchApplySafe,
    PatchApplySafeParams,
)


def _have_git() -> bool:
    return shutil.which("git") is not None


pytestmark = pytest.mark.skipif(not _have_git(), reason="git not installed")


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True
    )


def _init_repo(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "t@t.test")
    _git(project, "config", "user.name", "tester")
    (project / "a.txt").write_text("hello\n")
    _git(project, "add", "a.txt")
    _git(project, "commit", "-q", "-m", "init")
    return project


@pytest.mark.asyncio
async def test_applies_clean_diff(tmp_path: Path):
    project = _init_repo(tmp_path)
    diff = (
        "diff --git a/a.txt b/a.txt\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -1 +1 @@\n"
        "-hello\n"
        "+hello world\n"
    )
    res = await PatchApplySafe().execute(
        PatchApplySafeParams(project_path=project, diff=diff)
    )
    assert res.is_ok
    assert res.value.applied
    assert not res.value.rolled_back
    assert (project / "a.txt").read_text() == "hello world\n"


@pytest.mark.asyncio
async def test_rejects_non_git_directory(tmp_path: Path):
    res = await PatchApplySafe().execute(
        PatchApplySafeParams(project_path=tmp_path, diff="x")
    )
    assert not res.is_ok
    assert res.failure.next_action == "init_git"


@pytest.mark.asyncio
async def test_rolls_back_on_gate_failure(tmp_path: Path):
    project = _init_repo(tmp_path)
    diff = (
        "diff --git a/a.txt b/a.txt\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -1 +1 @@\n"
        "-hello\n"
        "+CHANGED\n"
    )

    async def failing_gate(_path):
        return ok({"ok": False, "summary": "fake gate said no"})

    uc = PatchApplySafe(gate_runner=failing_gate)
    res = await uc.execute(
        PatchApplySafeParams(project_path=project, diff=diff)
    )
    assert res.is_ok
    out = res.value
    assert out.applied
    assert out.rolled_back
    assert out.gate_ok is False
    assert (project / "a.txt").read_text() == "hello\n"


@pytest.mark.asyncio
async def test_rejects_dirty_tree(tmp_path: Path):
    project = _init_repo(tmp_path)
    (project / "a.txt").write_text("dirty\n")
    res = await PatchApplySafe().execute(
        PatchApplySafeParams(project_path=project, diff="x")
    )
    assert not res.is_ok
    assert res.failure.next_action == "commit_or_stash"
