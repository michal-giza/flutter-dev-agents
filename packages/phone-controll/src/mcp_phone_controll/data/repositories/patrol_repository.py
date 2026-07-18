"""PatrolRepository implementation backed by the `patrol` CLI."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ...domain.entities import BuildMode, PatrolTestFile, TestRun, TestStatus
from ...domain.failures import InvalidArgumentFailure, TestExecutionFailure
from ...domain.repositories import PatrolRepository, TestRepository
from ...domain.result import Result, err, ok
from ...infrastructure.patrol_cli import MIN_WEB_CLI_VERSION, PatrolCli
from ..parsers.patrol_output_parser import parse_patrol_output
from ..parsers.playwright_report_parser import find_report, parse_playwright_report

# Headless-CI defaults. Unattended runs need retries (headless browsers
# flake more), a hard ceiling so a hung run can't wedge the job, and
# --no-sandbox because most CI containers run as root without user
# namespaces.
_CI_WEB_RETRIES = 2
_CI_GLOBAL_TIMEOUT_MS = 30 * 60 * 1000   # 30 min for the whole run
_CI_BROWSER_ARGS = ("--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage")

# Patrol CLI errors worth quoting verbatim instead of guessing. An
# unknown-option error means WE built bad argv — never blame the user's
# toolchain for it (the old code's "run patrol doctor" hint did exactly
# that, and hid a 100%-reproducible bug for months).
_UNKNOWN_OPTION = 'could not find an option named'
_NO_DEVICES = "no devices"


def _failure_message(result, run: TestRun) -> str:
    blob = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    if _UNKNOWN_OPTION in blob:
        return (
            "patrol rejected an argument phone-controll passed (see stderr) — "
            "this is a tool bug, not your project. Please report it."
        )
    if _NO_DEVICES in blob:
        return (
            "patrol found no devices. Boot a simulator/emulator or connect a "
            "device, then select_device."
        )
    if run.failed:
        names = ", ".join(
            c.name for c in run.cases if c.status is TestStatus.FAILED
        )[:200]
        return f"patrol test: {run.failed} test(s) failed{f' — {names}' if names else ''}"
    return (
        f"patrol test exited {result.returncode}. See stderr/stdout_tail — Patrol "
        "prints human-readable output, so per-test counts may be unavailable "
        "even when the run genuinely failed."
    )


class PatrolTestRepository(PatrolRepository, TestRepository):
    """Patrol implementation. Also satisfies TestRepository so it can be used
    interchangeably with FlutterTestRepository when a project supports Patrol."""

    def __init__(self, cli: PatrolCli) -> None:
        self._cli = cli

    # ----- discovery -----------------------------------------------------

    async def list_tests(self, project_path: Path) -> Result[list[PatrolTestFile]]:
        if not project_path.exists():
            return err(InvalidArgumentFailure(message=f"project not found: {project_path}"))
        # Patrol 4 moved the default test directory from `integration_test/`
        # to `patrol_test/`. Scan BOTH so discovery doesn't silently return
        # [] on a Patrol 4 project (or on a repo mid-migration with both).
        files: list[PatrolTestFile] = []
        seen: set[Path] = set()
        for dir_name in ("integration_test", "patrol_test"):
            root = project_path / dir_name
            if not root.exists():
                continue
            for path in sorted(root.rglob("*_test.dart")):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(
                    PatrolTestFile(
                        path=resolved,
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
        web: bool = False,
        ci: bool = False,
        tags: str | None = None,
        exclude_tags: str | None = None,
    ) -> Result[TestRun]:
        return await self._run(
            project_path,
            target=test_path,
            device_serial=device_serial,
            flavor=flavor,
            build_mode=build_mode,
            web=web,
            ci=ci,
            tags=tags,
            exclude_tags=exclude_tags,
        )

    async def run_suite(
        self,
        project_path: Path,
        test_dir: Path,
        device_serial: str,
        flavor: str | None = None,
        build_mode: BuildMode = BuildMode.DEBUG,
        web: bool = False,
        ci: bool = False,
        tags: str | None = None,
        exclude_tags: str | None = None,
    ) -> Result[TestRun]:
        return await self._run(
            project_path,
            target=test_dir,
            device_serial=device_serial,
            flavor=flavor,
            build_mode=build_mode,
            web=web,
            ci=ci,
            tags=tags,
            exclude_tags=exclude_tags,
        )

    # ----- TestRepository surface (drop-in replacement for FlutterTestRepository) ----

    async def run_unit_tests(
        self, project_path: Path, platform: str = "auto"
    ) -> Result[TestRun]:
        # Patrol orchestrates integration tests; unit tests are still plain `flutter test`.
        # We expose this here so use cases that take a TestRepository can still call it,
        # delegating via the patrol CLI's underlying flutter (it accepts non-integration paths).
        # `platform` is accepted for protocol compatibility but not applied — Patrol drives
        # its own runner; the FlutterTestRepository path is where --platform chrome lands.
        del platform
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

    async def _web_gate(self) -> Result[None] | None:
        """Fail CLOSED when the installed patrol_cli can't do web.

        Web landed in patrol_cli 4.0.0 (+ patrol 4.0.0, Playwright-driven).
        An unparsable version is also a failure — better an actionable
        error than silently emitting --web-* flags an old CLI rejects.
        """
        version = await self._cli.version()
        if version is not None and version >= MIN_WEB_CLI_VERSION:
            return None
        found = ".".join(str(p) for p in version) if version else "unknown"
        want = ".".join(str(p) for p in MIN_WEB_CLI_VERSION)
        return err(
            TestExecutionFailure(
                message=(
                    f"Patrol web tests require patrol_cli >= {want}; found "
                    f"{found} at {self._cli.binary}. Run "
                    "`dart pub global activate patrol_cli` to upgrade, and bump "
                    "`patrol` in the app's pubspec.yaml (patrol and patrol_cli "
                    "are lockstep version-checked — e.g. patrol_cli 4.5.x "
                    "requires patrol 4.7.0). Web also needs Flutter >= 3.32.0 "
                    "and Node.js installed; Patrol installs Playwright itself "
                    "on first run. Note: patrol_cli 4.0 moved the default test "
                    "directory from integration_test/ to patrol_test/."
                ),
                details={
                    "found_version": found,
                    "required_version": want,
                    "patrol_binary": self._cli.binary,
                },
                next_action="upgrade_patrol_cli",
            )
        )

    async def _run(
        self,
        project_path: Path,
        target: Path | None,
        device_serial: str | None,
        flavor: str | None,
        build_mode: BuildMode,
        web: bool = False,
        ci: bool = False,
        tags: str | None = None,
        exclude_tags: str | None = None,
    ) -> Result[TestRun]:
        if web:
            gate = await self._web_gate()
            if gate is not None:
                return gate
        # Web: ask Patrol for a machine-readable Playwright JSON report so
        # counts are EXACT rather than scraped from human output. Written to
        # a temp dir we don't delete — the report is useful evidence and the
        # OS reaps /tmp.
        results_dir: Path | None = None
        if web:
            results_dir = Path(tempfile.mkdtemp(prefix="patrol-web-results-"))
        result = await self._cli.test(
            project_path=project_path,
            target=target,
            device_serial=device_serial,
            flavor=flavor,
            build_mode=build_mode.value,
            web=web,
            web_results_dir=results_dir,
            # CI mode: unattended + deterministic. Retries absorb the flake
            # a headless browser adds; --no-sandbox is required in most
            # containers; a global timeout stops a hung run wedging the job.
            web_retries=_CI_WEB_RETRIES if (ci and web) else None,
            web_global_timeout_ms=_CI_GLOBAL_TIMEOUT_MS if (ci and web) else None,
            web_browser_args=list(_CI_BROWSER_ARGS) if (ci and web) else None,
            web_video="retain-on-failure" if (ci and web) else None,
            # Native-only hermeticity (Patrol 4). In CI we want each test to
            # start from a clean install and clean permission grants.
            clear_permissions=ci and not web,
            full_isolation=ci and not web,
            tags=tags,
            exclude_tags=exclude_tags,
            # NOTE: do NOT pass `--reporter=json` here. `patrol test` has
            # never had a --reporter flag — passing one exits 1 with
            # `Could not find an option named "--reporter"`, which made
            # EVERY Patrol run fail (masked by a generic patrol-doctor
            # hint). Patrol's output is human-readable; we parse it
            # best-effort and treat the exit code as authoritative.
        )
        # Prefer the exact Playwright report; fall back to scraping.
        run: TestRun | None = None
        report_path: Path | None = None
        if results_dir is not None:
            report_path = find_report(results_dir)
            if report_path is not None:
                run = parse_playwright_report(report_path)
        if run is None:
            run = parse_patrol_output(result.stdout, result.stderr)
        if not result.ok:
            return err(
                TestExecutionFailure(
                    message=_failure_message(result, run),
                    details={
                        "exit_code": result.returncode,
                        "stderr": (result.stderr or "")[-2000:],
                        "stdout_tail": (result.stdout or "")[-2000:],
                        "parsed": {
                            "total": run.total,
                            "passed": run.passed,
                            "failed": run.failed,
                        },
                        "failed_tests": [
                            c.name for c in run.cases if c.status is TestStatus.FAILED
                        ],
                        **(
                            {"playwright_report": str(report_path)}
                            if report_path is not None
                            else {}
                        ),
                    },
                    next_action="inspect_test_output",
                )
            )
        return ok(run)
