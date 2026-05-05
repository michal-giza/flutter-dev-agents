"""IdeRepository implementation for VS Code via the `code` CLI."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from ...domain.entities import IdeKind, IdeWindow
from ...domain.failures import (
    IdeNotFoundFailure,
    IdeWindowNotFoundFailure,
)
from ...domain.repositories import IdeRepository
from ...domain.result import Err, Result, err, ok
from ...infrastructure.ide_cli import IdeCli


class VsCodeIdeRepository(IdeRepository):
    def __init__(self, cli: IdeCli) -> None:
        self._cli = cli
        self._windows: dict[str, IdeWindow] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._mutex = asyncio.Lock()

    async def open_project(
        self,
        project_path: Path,
        ide: IdeKind = IdeKind.VSCODE,
        new_window: bool = True,
    ) -> Result[IdeWindow]:
        if ide is not IdeKind.VSCODE:
            return err(
                IdeNotFoundFailure(
                    message=f"unsupported IDE {ide.value}",
                    next_action="fix_arguments",
                )
            )
        try:
            proc = await self._cli.open_vscode(project_path, new_window=new_window)
        except FileNotFoundError as e:
            return err(
                IdeNotFoundFailure(
                    message=f"VS Code `code` CLI not found: {e}",
                    next_action="install_vscode_or_path",
                    details={
                        "hint": "Install VS Code and run Shell Command: Install 'code' command in PATH"
                    },
                )
            )
        except Exception as e:  # noqa: BLE001
            return err(
                IdeNotFoundFailure(
                    message=f"failed to spawn VS Code: {e}",
                )
            )
        window_id = uuid.uuid4().hex[:10]
        window = IdeWindow(
            window_id=window_id,
            project_path=project_path,
            ide=IdeKind.VSCODE,
            pid=proc.pid,
            opened_at=datetime.now(),
        )
        async with self._mutex:
            self._windows[window_id] = window
            self._processes[window_id] = proc
        return ok(window)

    async def list_windows(self) -> Result[list[IdeWindow]]:
        async with self._mutex:
            return ok(list(self._windows.values()))

    async def close_window(
        self,
        project_path: Path | None = None,
        window_id: str | None = None,
    ) -> Result[None]:
        async with self._mutex:
            target_id: str | None = None
            if window_id is not None:
                target_id = window_id if window_id in self._windows else None
            elif project_path is not None:
                for wid, win in self._windows.items():
                    if win.project_path == project_path:
                        target_id = wid
                        break
            if target_id is None:
                return err(
                    IdeWindowNotFoundFailure(
                        message="no IDE window matches",
                        details={"project_path": str(project_path) if project_path else None,
                                 "window_id": window_id},
                        next_action="list_ide_windows",
                    )
                )
            window = self._windows.pop(target_id)
            proc = self._processes.pop(target_id, None)
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
        return ok(None)

    async def focus_window(self, project_path: Path) -> Result[None]:
        try:
            await self._cli.focus_vscode_macos()
        except FileNotFoundError:
            return err(
                IdeNotFoundFailure(
                    message="osascript not available (macOS-only)",
                    next_action="ask_user",
                )
            )
        except Exception as e:  # noqa: BLE001
            return err(IdeNotFoundFailure(message=f"focus failed: {e}"))
        return ok(None)

    async def is_available(self, ide: IdeKind = IdeKind.VSCODE) -> Result[str]:
        if ide is not IdeKind.VSCODE:
            return err(
                IdeNotFoundFailure(
                    message=f"unsupported IDE {ide.value}",
                    next_action="fix_arguments",
                )
            )
        result = await self._cli.vscode_version()
        if not result.ok:
            return err(
                IdeNotFoundFailure(
                    message="VS Code `code` CLI not on PATH",
                    next_action="install_vscode_or_path",
                    details={"stderr": result.stderr},
                )
            )
        version = result.stdout.splitlines()[0] if result.stdout.strip() else "unknown"
        return ok(version)

    async def close_all(self) -> None:
        """For atexit cleanup."""
        async with self._mutex:
            procs = list(self._processes.values())
            self._processes.clear()
            self._windows.clear()
        for proc in procs:
            if proc.returncode is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    continue
