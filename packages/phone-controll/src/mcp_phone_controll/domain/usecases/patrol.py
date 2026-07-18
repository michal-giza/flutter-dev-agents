"""Patrol-based Flutter integration test orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import BuildMode, PatrolTestFile, TestRun
from ..repositories import PatrolRepository, SessionStateRepository
from ..result import Err, Result
from ._helpers import resolve_serial
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class ListPatrolTestsParams:
    project_path: Path


class ListPatrolTests(BaseUseCase[ListPatrolTestsParams, list[PatrolTestFile]]):
    def __init__(self, patrol: PatrolRepository) -> None:
        self._patrol = patrol

    async def execute(self, params: ListPatrolTestsParams) -> Result[list[PatrolTestFile]]:
        return await self._patrol.list_tests(params.project_path)


# `platform="web"` runs the suite against Flutter web (Patrol >= 4.0.0,
# Playwright/Chromium). There is no device to select in that mode, so we
# skip serial resolution entirely — otherwise every web run would die on
# NoDeviceSelectedFailure.
_WEB = "web"


@dataclass(frozen=True, slots=True)
class RunPatrolTestParams:
    project_path: Path
    test_path: Path
    serial: str | None = None
    flavor: str | None = None
    build_mode: BuildMode = BuildMode.DEBUG
    platform: str = "mobile"   # "mobile" | "web"
    ci: bool = False           # headless-CI mode: unattended + deterministic
    tags: str | None = None
    exclude_tags: str | None = None


class RunPatrolTest(BaseUseCase[RunPatrolTestParams, TestRun]):
    def __init__(self, patrol: PatrolRepository, state: SessionStateRepository) -> None:
        self._patrol = patrol
        self._state = state

    async def execute(self, params: RunPatrolTestParams) -> Result[TestRun]:
        web = params.platform == _WEB
        serial = ""
        if not web:
            serial_res = await resolve_serial(params.serial, self._state)
            if isinstance(serial_res, Err):
                return serial_res
            serial = serial_res.value
        return await self._patrol.run_test(
            project_path=params.project_path,
            test_path=params.test_path,
            device_serial=serial,
            flavor=params.flavor,
            build_mode=params.build_mode,
            web=web,
            ci=params.ci,
            tags=params.tags,
            exclude_tags=params.exclude_tags,
        )


@dataclass(frozen=True, slots=True)
class RunPatrolSuiteParams:
    project_path: Path
    test_dir: Path = Path("integration_test")
    serial: str | None = None
    flavor: str | None = None
    build_mode: BuildMode = BuildMode.DEBUG
    platform: str = "mobile"   # "mobile" | "web"
    ci: bool = False           # headless-CI mode: unattended + deterministic
    tags: str | None = None
    exclude_tags: str | None = None


class RunPatrolSuite(BaseUseCase[RunPatrolSuiteParams, TestRun]):
    def __init__(self, patrol: PatrolRepository, state: SessionStateRepository) -> None:
        self._patrol = patrol
        self._state = state

    async def execute(self, params: RunPatrolSuiteParams) -> Result[TestRun]:
        web = params.platform == _WEB
        serial = ""
        if not web:
            serial_res = await resolve_serial(params.serial, self._state)
            if isinstance(serial_res, Err):
                return serial_res
            serial = serial_res.value
        return await self._patrol.run_suite(
            project_path=params.project_path,
            test_dir=params.test_dir,
            device_serial=serial,
            flavor=params.flavor,
            build_mode=params.build_mode,
            web=web,
            ci=params.ci,
            tags=params.tags,
            exclude_tags=params.exclude_tags,
        )
