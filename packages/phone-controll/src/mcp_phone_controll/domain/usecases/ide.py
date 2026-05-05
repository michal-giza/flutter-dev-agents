"""IDE multi-window orchestration use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import IdeKind, IdeWindow
from ..repositories import IdeRepository
from ..result import Result
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
