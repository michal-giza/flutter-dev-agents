"""IDE multi-window orchestration use cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..entities import IdeKind, IdeWindow
from ..failures import FilesystemFailure
from ..repositories import IdeRepository
from ..result import Result, err, ok
from .base import BaseUseCase, NoParams


@dataclass(frozen=True, slots=True)
class OpenProjectInIdeParams:
    project_path: Path
    ide: IdeKind = IdeKind.VSCODE
    new_window: bool = True


class OpenProjectInIde(BaseUseCase[OpenProjectInIdeParams, IdeWindow]):
    def __init__(self, repo: IdeRepository) -> None:
        self._repo = repo

    async def execute(self, params: OpenProjectInIdeParams) -> Result[IdeWindow]:
        return await self._repo.open_project(
            params.project_path, params.ide, params.new_window
        )


class ListIdeWindows(BaseUseCase[NoParams, list[IdeWindow]]):
    def __init__(self, repo: IdeRepository) -> None:
        self._repo = repo

    async def execute(self, params: NoParams) -> Result[list[IdeWindow]]:
        return await self._repo.list_windows()


@dataclass(frozen=True, slots=True)
class CloseIdeWindowParams:
    project_path: Path | None = None
    window_id: str | None = None


class CloseIdeWindow(BaseUseCase[CloseIdeWindowParams, None]):
    def __init__(self, repo: IdeRepository) -> None:
        self._repo = repo

    async def execute(self, params: CloseIdeWindowParams) -> Result[None]:
        return await self._repo.close_window(params.project_path, params.window_id)


@dataclass(frozen=True, slots=True)
class FocusIdeWindowParams:
    project_path: Path


class FocusIdeWindow(BaseUseCase[FocusIdeWindowParams, None]):
    def __init__(self, repo: IdeRepository) -> None:
        self._repo = repo

    async def execute(self, params: FocusIdeWindowParams) -> Result[None]:
        return await self._repo.focus_window(params.project_path)


@dataclass(frozen=True, slots=True)
class IsIdeAvailableParams:
    ide: IdeKind = IdeKind.VSCODE


class IsIdeAvailable(BaseUseCase[IsIdeAvailableParams, str]):
    def __init__(self, repo: IdeRepository) -> None:
        self._repo = repo

    async def execute(self, params: IsIdeAvailableParams) -> Result[str]:
        return await self._repo.is_available(params.ide)


@dataclass(frozen=True, slots=True)
class WriteVscodeLaunchConfigParams:
    project_path: Path
    flavor: str | None = None
    target: str = "lib/main.dart"
    debug_mode: str = "debug"   # "debug" | "profile" | "release"
    overwrite: bool = False


@dataclass(frozen=True, slots=True)
class VscodeLaunchConfigWritten:
    path: Path
    created: bool


def render_vscode_launch_config(
    flavor: str | None,
    target: str,
    debug_mode: str,
) -> dict:
    """Build a Flutter `launch.json` payload — same shape Dart-Code produces.

    Three configurations: debug, profile, release. The active one mirrors
    `debug_mode` so F5 in VS Code launches the same configuration the
    headless dev session uses.
    """
    base_args: list[str] = []
    if flavor:
        base_args = ["--flavor", flavor]
    configurations = []
    for mode in ("debug", "profile", "release"):
        cfg = {
            "name": f"Flutter ({mode}{f' / {flavor}' if flavor else ''})",
            "type": "dart",
            "request": "launch",
            "program": target,
            "flutterMode": mode,
        }
        if base_args:
            cfg["args"] = list(base_args)
        configurations.append(cfg)
    return {
        "version": "0.2.0",
        "configurations": configurations,
        "compounds": [],
        "// generated_by": "mcp-phone-controll write_vscode_launch_config",
    }


class WriteVscodeLaunchConfig(
    BaseUseCase[WriteVscodeLaunchConfigParams, VscodeLaunchConfigWritten]
):
    """Write a `.vscode/launch.json` so F5 mirrors the agent's debug session.

    Idempotent unless `overwrite=True`. We never clobber an existing file by
    default — humans tend to hand-tune these and we don't want to lose
    customisations.
    """

    async def execute(
        self, params: WriteVscodeLaunchConfigParams
    ) -> Result[VscodeLaunchConfigWritten]:
        project = Path(params.project_path).expanduser()
        if not project.is_dir():
            return err(
                FilesystemFailure(
                    message=f"project_path is not a directory: {project}",
                    next_action="fix_arguments",
                )
            )
        out_dir = project / ".vscode"
        out_path = out_dir / "launch.json"
        if out_path.exists() and not params.overwrite:
            return ok(VscodeLaunchConfigWritten(path=out_path, created=False))
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = render_vscode_launch_config(
                params.flavor, params.target, params.debug_mode
            )
            out_path.write_text(json.dumps(payload, indent=2) + "\n")
        except OSError as exc:
            return err(
                FilesystemFailure(
                    message=f"failed to write launch.json: {exc}",
                    next_action="check_permissions",
                    details={"path": str(out_path)},
                )
            )
        return ok(VscodeLaunchConfigWritten(path=out_path, created=True))
