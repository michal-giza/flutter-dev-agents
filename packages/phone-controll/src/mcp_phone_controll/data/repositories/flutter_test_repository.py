"""TestRepository implementation backed by the Flutter CLI."""

from __future__ import annotations

from pathlib import Path

from ...domain.entities import TestRun
from ...domain.failures import TestExecutionFailure
from ...domain.repositories import TestRepository
from ...domain.result import Result, err, ok
from ...infrastructure.flutter_cli import FlutterCli
from ..parsers.flutter_test_reporter_parser import parse_flutter_json_reporter


class FlutterTestRepository(TestRepository):
    def __init__(self, flutter: FlutterCli) -> None:
        self._flutter = flutter

    async def run_unit_tests(self, project_path: Path) -> Result[TestRun]:
        result = await self._flutter.test_unit(project_path)
        run = parse_flutter_json_reporter(result.stdout)
        if not result.ok and run.total == 0:
            return err(
                TestExecutionFailure(
                    message="flutter test did not produce results",
                    details={"stderr": result.stderr},
                )
            )
        return ok(run)

    async def run_integration_tests(
        self,
        project_path: Path,
        device_serial: str,
        test_path: str = "integration_test/",
    ) -> Result[TestRun]:
        result = await self._flutter.test_integration(
            project_path, device_serial=device_serial, test_path=test_path
        )
        run = parse_flutter_json_reporter(result.stdout)
        if not result.ok and run.total == 0:
            return err(
                TestExecutionFailure(
                    message="flutter integration test did not produce results",
                    details={"stderr": result.stderr},
                )
            )
        return ok(run)
