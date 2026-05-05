"""Environment 'doctor' — checks every toolchain prerequisite in one call."""

from __future__ import annotations

from ..entities import EnvironmentReport
from ..repositories import EnvironmentRepository
from ..result import Result
from .base import BaseUseCase, NoParams


class CheckEnvironment(BaseUseCase[NoParams, EnvironmentReport]):
    def __init__(self, env: EnvironmentRepository) -> None:
        self._env = env

    async def execute(self, params: NoParams) -> Result[EnvironmentReport]:
        return await self._env.check()
