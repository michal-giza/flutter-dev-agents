"""Project inspection — what kind of project and which test frameworks apply."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import ProjectInfo
from ..repositories import ProjectInspector
from ..result import Result
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class InspectProjectParams:
    project_path: Path


class InspectProject(BaseUseCase[InspectProjectParams, ProjectInfo]):
    def __init__(self, inspector: ProjectInspector) -> None:
        self._inspector = inspector

    async def execute(self, params: InspectProjectParams) -> Result[ProjectInfo]:
        return await self._inspector.inspect(params.project_path)
