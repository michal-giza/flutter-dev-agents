"""TestRepository implementation backed by the Flutter CLI."""

from __future__ import annotations

from pathlib import Path

from ...domain.entities import TestRun
from ...domain.failures import TestExecutionFailure
from ...domain.repositories import TestRepository
from ...domain.result import Result, err, ok
from ...infrastructure.flutter_cli import FlutterCli
from ..parsers.flutter_test_reporter_parser import (
    looks_like_web_platform_error,
    parse_flutter_json_reporter,
)


class FlutterTestRepository(TestRepository):
    def __init__(self, flutter: FlutterCli) -> None:
        self._flutter = flutter

    async def run_unit_tests(
        self, project_path: Path, platform: str = "auto"
    ) -> Result[TestRun]:
        # platform: "auto" | "vm" | "chrome". "vm"/"chrome" are explicit;
        # "auto" tries the VM (Flutter's default) first, then transparently
        # retries on `--platform chrome` if the run failed because a
        # web-only Dart library (dart:html, …) isn't available on the VM.
        # This is what makes `run_unit_tests` work on Flutter *web* apps
        # without the agent having to know the project is web — and matches
        # the repo's own `flutter test --platform chrome`.
        if platform == "chrome":
            return await self._run(project_path, cli_platform="chrome")
        if platform == "vm":
            return await self._run(project_path, cli_platform=None)

        # auto
        first = await self._flutter.test_unit(project_path, platform=None)
        if looks_like_web_platform_error(first.stdout, first.stderr):
            from ...observability import emit as _emit

            _emit(
                "test_platform_autoswitch",
                level="info",
                reason="web-only library not available on vm",
                retry_platform="chrome",
            )
            return await self._run(project_path, cli_platform="chrome")
        return self._finish(first, attempted="vm")

    async def _run(self, project_path: Path, cli_platform: str | None) -> Result[TestRun]:
        result = await self._flutter.test_unit(project_path, platform=cli_platform)
        return self._finish(result, attempted=cli_platform or "vm")

    @staticmethod
    def _finish(result, attempted: str) -> Result[TestRun]:
        run = parse_flutter_json_reporter(result.stdout)
        if not result.ok and run.total == 0:
            details: dict = {"platform": attempted, "stderr": (result.stderr or "")[-2000:]}
            if looks_like_web_platform_error(result.stdout, result.stderr):
                # Reached only when an EXPLICIT platform was wrong (auto
                # would have retried). Point the caller at the fix.
                details["hint"] = (
                    "A web-only Dart library (e.g. dart:html) isn't available "
                    "on this test platform. Re-run with platform='chrome' (or "
                    "platform='auto')."
                )
            return err(
                TestExecutionFailure(
                    message="flutter test did not produce results",
                    details=details,
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
