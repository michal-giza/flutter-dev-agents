"""patch_apply_safe — apply a unified diff and auto-rollback on quality regression.

Flow:

  1. project must be a git working tree with a clean status (or `force=True`).
  2. write the diff to a temp file, run `git apply --check`. On error, abort.
  3. apply the diff (`git apply`).
  4. run the injected quality gate.
  5. if the gate fails, roll back via `git checkout -- .` and surface both
     the gate's diagnosis AND the original diff for the agent to study.
  6. on success, leave changes uncommitted so a human reviewer can decide.

Designed for the Edit → Hot Reload → Observe → Decide loop: an agent can
propose a patch, see whether it survives the quality bar, and learn from
the rollback diagnostics if it doesn't.
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from ..failures import FilesystemFailure, UnexpectedFailure
from ..result import Err, Result, err, ok
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class PatchApplySafeParams:
    project_path: Path
    diff: str
    skip_gate: bool = False
    force: bool = False     # apply even if working tree is dirty


@dataclass(frozen=True, slots=True)
class PatchApplyResult:
    applied: bool
    rolled_back: bool
    files_changed: tuple[str, ...]
    gate_ok: bool | None
    gate_summary: str | None
    diagnosis: str


GateRunner = Callable[[Path], Awaitable[Result[dict]]]


async def _run(*cmd: str, cwd: Path) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, errb = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace"), errb.decode(errors="replace")


class PatchApplySafe(BaseUseCase[PatchApplySafeParams, PatchApplyResult]):
    def __init__(self, gate_runner: GateRunner | None = None) -> None:
        self._gate_runner = gate_runner

    async def execute(
        self, params: PatchApplySafeParams
    ) -> Result[PatchApplyResult]:
        project = Path(params.project_path).expanduser()
        if not (project / ".git").exists():
            return err(
                FilesystemFailure(
                    message="patch_apply_safe requires a git working tree",
                    next_action="init_git",
                    details={"project_path": str(project)},
                )
            )
        if not params.diff.strip():
            return err(
                FilesystemFailure(
                    message="empty diff",
                    next_action="fix_arguments",
                )
            )
        # Pre-flight: working tree must be clean (or force=True).
        if not params.force:
            rc, out, _ = await _run("git", "status", "--porcelain", cwd=project)
            if rc == 0 and out.strip():
                return err(
                    FilesystemFailure(
                        message=(
                            "working tree is dirty; commit or stash first, or "
                            "pass force=true"
                        ),
                        next_action="commit_or_stash",
                        details={"status_porcelain": out[:500]},
                    )
                )
        # Write diff to a temp file inside the project so paths resolve.
        diff_path = project / ".mcp-pending.patch"
        try:
            diff_path.write_text(params.diff)
            rc, _, errb = await _run(
                "git", "apply", "--check", str(diff_path), cwd=project
            )
            if rc != 0:
                return err(
                    FilesystemFailure(
                        message="patch does not apply cleanly",
                        next_action="fix_diff",
                        details={"git_apply_check": errb[:1000]},
                    )
                )
            rc, _, errb = await _run(
                "git", "apply", str(diff_path), cwd=project
            )
            if rc != 0:
                return err(
                    UnexpectedFailure(
                        message="git apply failed after --check passed",
                        details={"stderr": errb[:1000]},
                    )
                )
        finally:
            if diff_path.exists():
                diff_path.unlink()

        rc, out, _ = await _run(
            "git", "diff", "--name-only", "HEAD", cwd=project
        )
        files_changed = tuple(line for line in out.splitlines() if line.strip())

        gate_ok: bool | None = None
        gate_summary: str | None = None
        if not params.skip_gate and self._gate_runner is not None:
            gate_res = await self._gate_runner(project)
            if isinstance(gate_res, Err):
                gate_ok = False
                gate_summary = gate_res.failure.message
            else:
                report = gate_res.value
                gate_ok = bool(
                    report.get("ok") if isinstance(report, dict) else True
                )
                gate_summary = (
                    report.get("summary") if isinstance(report, dict) else None
                )

            if not gate_ok:
                # Roll back.
                await _run("git", "checkout", "--", ".", cwd=project)
                await _run("git", "clean", "-fd", cwd=project)
                return ok(
                    PatchApplyResult(
                        applied=True,
                        rolled_back=True,
                        files_changed=files_changed,
                        gate_ok=False,
                        gate_summary=gate_summary,
                        diagnosis=(
                            "patch applied cleanly but quality gate failed; "
                            "all changes rolled back"
                        ),
                    )
                )

        return ok(
            PatchApplyResult(
                applied=True,
                rolled_back=False,
                files_changed=files_changed,
                gate_ok=gate_ok,
                gate_summary=gate_summary,
                diagnosis=(
                    "patch applied; review with `git diff` and commit when ready"
                    if gate_ok or params.skip_gate
                    else "patch applied; gate not run"
                ),
            )
        )
