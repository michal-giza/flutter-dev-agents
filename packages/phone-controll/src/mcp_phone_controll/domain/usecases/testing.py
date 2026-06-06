"""Test runners: unit tests and on-device integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import TestRun
from ..repositories import SessionStateRepository, TestRepository
from ..result import Err, Result
from ._helpers import resolve_serial
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class RunUnitTestsParams:
    project_path: Path
    # "auto" (default) runs on the VM, then transparently retries on
    # `--platform chrome` if the run hits a web-only-library error
    # (Flutter web apps importing dart:html). "vm" / "chrome" force it.
    platform: str = "auto"


class RunUnitTests(BaseUseCase[RunUnitTestsParams, TestRun]):
    def __init__(self, tests: TestRepository) -> None:
        self._tests = tests

    async def execute(self, params: RunUnitTestsParams) -> Result[TestRun]:
        return await self._tests.run_unit_tests(
            params.project_path, platform=params.platform
        )


@dataclass(frozen=True, slots=True)
class RunIntegrationTestsParams:
    project_path: Path
    test_path: str = "integration_test/"
    serial: str | None = None


class RunIntegrationTests(BaseUseCase[RunIntegrationTestsParams, TestRun]):
    def __init__(self, tests: TestRepository, state: SessionStateRepository) -> None:
        self._tests = tests
        self._state = state

    async def execute(self, params: RunIntegrationTestsParams) -> Result[TestRun]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._tests.run_integration_tests(
            params.project_path,
            device_serial=serial_res.value,
            test_path=params.test_path,
        )
