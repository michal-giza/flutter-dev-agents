"""Async wrapper for IDE CLIs (`code`, future `idea`, `studio`).

Spawns a new IDE window per call (`code -n <path>`) and tracks the spawned
PID so callers can later close it. Best-effort PID tracking — if VS Code
re-uses an existing process for a new window, the PID we have is the spawn
helper, not the editor.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner

_VSCODE_FALLBACKS = (
    "/usr/local/bin/code",
    "/opt/homebrew/bin/code",
    "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
    "/Applications/Visual Studio Code - Insiders.app/Contents/Resources/app/bin/code",
)


def _default_code_path() -> str:
    found = shutil.which("code")
    if found:
        return found
    for candidate in _VSCODE_FALLBACKS:
        if Path(candidate).exists():
            return candidate
    return "code"


class IdeCli:
    def __init__(self, runner: ProcessRunner, code_path: str | None = None) -> None:
        self._runner = runner
        self._code = code_path or _default_code_path()

    @property
    def vscode_binary(self) -> str:
        return self._code

    async def vscode_version(self, timeout_s: float = 5.0) -> ProcessResult:
        return await self._runner.run([self._code, "--version"], timeout_s=timeout_s)

    async def open_vscode(
        self, project_path: Path, new_window: bool = True
    ) -> asyncio.subprocess.Process:
        """Open a project in VS Code. Returns the spawned subprocess.

        With `new_window=True`, always opens a new window. Without, VS Code
        reuses the most-recent window (matches `code <path>` default).
        """
        argv = [self._code]
        if new_window:
            argv.append("-n")
        argv.append(str(project_path))
        return await self._runner.stream(argv)

    async def focus_vscode_macos(self, timeout_s: float = 3.0) -> ProcessResult:
        """Best-effort: bring VS Code to the foreground via osascript on macOS."""
        return await self._runner.run(
            [
                "osascript",
                "-e",
                'tell application "Visual Studio Code" to activate',
            ],
            timeout_s=timeout_s,
        )
