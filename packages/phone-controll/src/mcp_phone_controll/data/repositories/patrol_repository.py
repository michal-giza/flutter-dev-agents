"""PatrolRepository implementation backed by the `patrol` CLI."""

from __future__ import annotations

from pathlib import Path

from ...domain.entities import BuildMode, PatrolTestFile, TestRun
from ...domain.failures import FlutterCliFailure, InvalidArgumentFailure, TestExecutionFailure
from ...domain.repositories import PatrolRepository, TestRepository
from ...domain.result import Result, err, ok
from ...infrastructure.patrol_cli import PatrolCli
from ..parsers.flutter_test_reporter_parser import parse_flutter_json_reporter


class PatrolTestRepository(PatrolRepository, TestRepository):
    """Patrol implementation. Also satisfies TestRepository so it can be used
    interchangeably with FlutterTestRepository when a project supports Patrol."""

    def __init__(self, cli: PatrolCli) -> None:
        self._cli = cli

    # ----- discovery -----------------------------------------------------

    async def list_tests(self, project_path: Path) -> Result[list[PatrolTestFile]]:
        if not project_path.exists():
            return err(InvalidArgumentFailure(message=f"project not found: {project_path}"))
        root = project_path / "integration_test"
        if not root.exists():
            return ok([])
        files: list[PatrolTestFile] = []
        for path in sorted(root.rglob("*_test.dart")):
            files.append(
                PatrolTestFile(
                    path=path.resolve(),
                    relative=path.relative_to(project_path),
                    name=path.stem,
                )
            )
        return ok(files)

    # ----- direct Patrol invocations -------------------------------------

    async def run_test(
        self,
        project_path: Path,
        test_path: Path,
        device_serial: str,
        flavor: str | None = None,
        build_mode: BuildMode = BuildMode.DEBUG,
    ) -> Result[TestRun]:
        return await self._run(
            project_path,
            target=test_path,
            device_serial=device_serial,
            flavor=flavor,
            build_mode=build_mode,
        )

    async def run_suite(
        self,
        project_path: Path,
        test_dir: Path,
        device_serial: str,
        flavor: str | None = None,
        build_mode: BuildMode = BuildMode.DEBUG,
    ) -> Result[TestRun]:
        return await self._run(
            project_path,
            target=test_dir,
            device_serial=device_serial,
            flavor=flavor,
            build_mode=build_mode,
        )

    # ----- TestRepository surface (drop-in replacement for FlutterTestRepository) ----

    async def run_unit_tests(self, project_path: Path) -> Result[TestRun]:
        # Patrol orchestrates integration tests; unit tests are still plain `flutter test`.
        # We expose this here so use cases that take a TestRepository can still call it,
        # delegating via the patrol CLI's underlying flutter (it accepts non-integration paths).
        return await self._run(
            project_path, target=Path("test"), device_serial=None, flavor=None,
            build_mode=BuildMode.DEBUG,
        )

    async def run_integration_tests(
        self,
        project_path: Path,
        device_serial: str,
        test_path: str = "integration_test/",
    ) -> Result[TestRun]:
        return await self.run_suite(
            project_path=project_path,
            test_dir=Path(test_path),
            device_serial=device_serial,
        )

    # ----- shared helpers ------------------------------------------------

    async def _run(
        self,
        project_path: Path,
        target: Path | None,
        device_serial: str | None,
        flavor: str | None,
        build_mode: BuildMode,
    ) -> Result[TestRun]:
        result = await self._cli.test(
            project_path=project_path,
            target=target,
            device_serial=device_serial,
            flavor=flavor,
            build_mode=build_mode.value,
            extra_flags=["--reporter=json"],
        )
        run = parse_flutter_json_reporter(result.stdout)
        if not result.ok and run.total == 0:
            return err(
                TestExecutionFailure(
                    message="patrol test produced no results",
                    details={
                        "stderr": result.stderr,
                        "stdout_tail": result.stdout[-1000:] if result.stdout else "",
                        "hint": "Run `patrol doctor` and confirm the project has a patrol_cli dev_dependency.",
                    },
                )
            )
        return ok(run)
