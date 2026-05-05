"""Patrol-based Flutter integration test orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import BuildMode, PatrolTestFile, TestRun
from ..repositories import PatrolRepository, SessionStateRepository
from ..result import Err, Result
from .base import BaseUseCase
from ._helpers import resolve_serial


@dataclass(frozen=True, slots=True)
class ListPatrolTestsParams:
    project_path: Path


class ListPatrolTests(BaseUseCase[ListPatrolTestsParams, list[PatrolTestFile]]):
    def __init__(self, patrol: PatrolRepository) -> None:
        self._patrol = patrol

    async def execute(self, params: ListPatrolTestsParams) -> Result[list[PatrolTestFile]]:
        return await self._patrol.list_tests(params.project_path)


@dataclass(frozen=True, slots=True)
class RunPatrolTestParams:
    project_path: Path
    test_path: Path
    serial: str | None = None
    flavor: str | None = None
    build_mode: BuildMode = BuildMode.DEBUG


class RunPatrolTest(BaseUseCase[RunPatrolTestParams, TestRun]):
    def __init__(self, patrol: PatrolRepository, state: SessionStateRepository) -> None:
        self._patrol = patrol
        self._state = state

    async def execute(self, params: RunPatrolTestParams) -> Result[TestRun]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._patrol.run_test(
            project_path=params.project_path,
            test_path=params.test_path,
            device_serial=serial_res.value,
            flavor=params.flavor,
            build_mode=params.build_mode,
        )


@dataclass(frozen=True, slots=True)
class RunPatrolSuiteParams:
    project_path: Path
    test_dir: Path = Path("integration_test")
    serial: str | None = None
    flavor: str | None = None
    build_mode: BuildMode = BuildMode.DEBUG


class RunPatrolSuite(BaseUseCase[RunPatrolSuiteParams, TestRun]):
    def __init__(self, patrol: PatrolRepository, state: SessionStateRepository) -> None:
        self._patrol = patrol
        self._state = state

    async def execute(self, params: RunPatrolSuiteParams) -> Result[TestRun]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._patrol.run_suite(
            project_path=params.project_path,
            test_dir=params.test_dir,
            device_serial=serial_res.value,
            flavor=params.flavor,
            build_mode=params.build_mode,
        )
