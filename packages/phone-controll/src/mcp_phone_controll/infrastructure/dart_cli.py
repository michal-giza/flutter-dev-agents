"""Async wrapper around the `dart` CLI for analyze / format / fix / pub.

Used by the code-quality use cases. Pure subprocess plumbing — no domain
knowledge. Fall-backs find `dart` in common locations when shutil.which fails
(e.g. when Claude Code spawns the MCP with a minimal PATH).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner

_DART_FALLBACKS = (
    "/opt/homebrew/bin/dart",
    "/usr/local/bin/dart",
    str(Path.home() / "fvm/default/bin/dart"),
    str(Path.home() / "flutter/bin/dart"),
    str(Path.home() / "development/flutter/bin/dart"),
)


def _default_dart_path() -> str:
    found = shutil.which("dart")
    if found:
        return found
    for candidate in _DART_FALLBACKS:
        if Path(candidate).exists():
            return candidate
    return "dart"


class DartCli:
    def __init__(self, runner: ProcessRunner, dart_path: str | None = None) -> None:
        self._runner = runner
        self._dart = dart_path or _default_dart_path()

    @property
    def binary(self) -> str:
        return self._dart

    async def analyze(
        self, project_path: Path, json_output: bool = True, timeout_s: float = 120.0
    ) -> ProcessResult:
        argv = [self._dart, "analyze"]
        if json_output:
            argv += ["--format=json"]
        return await self._runner.run(argv, cwd=project_path, timeout_s=timeout_s)

    async def format(
        self,
        target_path: Path,
        set_exit_if_changed: bool = False,
        dry_run: bool = False,
        timeout_s: float = 60.0,
    ) -> ProcessResult:
        argv = [self._dart, "format"]
        if set_exit_if_changed:
            argv.append("--set-exit-if-changed")
        if dry_run:
            argv.append("--output=show")  # show the diff, don't rewrite
        argv.append(str(target_path))
        return await self._runner.run(argv, timeout_s=timeout_s)

    async def fix(
        self, project_path: Path, apply: bool = False, timeout_s: float = 120.0
    ) -> ProcessResult:
        argv = [self._dart, "fix"]
        argv.append("--apply" if apply else "--dry-run")
        return await self._runner.run(argv, cwd=project_path, timeout_s=timeout_s)


class FlutterPubCli:
    """`flutter pub` subcommands. Lives separately because `pub get` updates
    pubspec.lock and lives under flutter, not dart, for Flutter projects."""

    def __init__(self, runner: ProcessRunner, flutter_path: str | None = None) -> None:
        self._runner = runner
        if flutter_path is None:
            from .flutter_cli import _default_flutter_path

            flutter_path = _default_flutter_path()
        self._flutter = flutter_path

    async def get(
        self, project_path: Path, timeout_s: float = 300.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._flutter, "pub", "get"], cwd=project_path, timeout_s=timeout_s
        )

    async def outdated(
        self, project_path: Path, timeout_s: float = 60.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._flutter, "pub", "outdated", "--show-all"],
            cwd=project_path,
            timeout_s=timeout_s,
        )
