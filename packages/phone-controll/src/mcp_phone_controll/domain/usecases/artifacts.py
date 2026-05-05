"""Artifact session use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import Session
from ..repositories import ArtifactRepository
from ..result import Err, Result, ok
from .base import BaseUseCase, NoParams


@dataclass(frozen=True, slots=True)
class NewSessionParams:
    label: str | None = None


class NewSession(BaseUseCase[NewSessionParams, Session]):
    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(self, params: NewSessionParams) -> Result[Session]:
        return await self._artifacts.new_session(params.label)


class GetArtifactsDir(BaseUseCase[NoParams, Path]):
    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(self, params: NoParams) -> Result[Path]:
        session_res = await self._artifacts.current_session()
        if isinstance(session_res, Err):
            return session_res
        return ok(session_res.value.root)
