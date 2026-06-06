"""Widget testing — the daily-driver QA surface for Flutter apps.

`flutter test` runs everything under `test/` including unit tests +
widget tests (the `testWidgets(...)` blocks). The existing
`run_unit_tests` tool exposes that as a single run-everything-or-nothing
call, which is fine for CI but too coarse for the inner-dev-loop
workflow where an agent has just touched one widget file and wants
to re-run only its tests.

This module ships four widget-test-specific tools that map to the
flags `flutter test` already supports:

  • run_widget_test(test_path?, name_pattern?, tags?, plain_name?)
    — fine-grained test targeting.
  • list_widget_tests(project_path)
    — discovery without running. Scans `test/` for `testWidgets()`
      calls and returns the descriptions.
  • update_goldens(test_path?, name_pattern?)
    — regenerates golden images. Deliberately separate from
      run_widget_test because `--update-goldens` is dangerous (it
      silently overwrites the regression detection).
  • test_coverage_report(project_path)
    — runs with `--coverage`, parses `coverage/lcov.info`, returns
      line/branch coverage per file + overall totals + a paste-
      ready advice line.

Across a portfolio of Flutter apps this becomes the "did I break
anything?" loop after every change.

Design notes:

- **No new dependencies.** `flutter test --coverage` writes lcov,
  which is a simple line-based format. We parse it ourselves —
  no `coverage` or `lcov-parser` package needed.
- **Discovery via regex.** `list_widget_tests` greps for
  `testWidgets('description', ...)`. Imperfect (won't find
  computed test names) but fast and dependency-free. The Flutter
  team's own tools use the same pattern for the `flutter test
  --machine` test list.
- **Result shape mirrors run_unit_tests / run_integration_tests.**
  Same `TestRun` entity, same per-case `TestCase` shape. Agents
  that already handle the existing test envelopes don't need to
  learn new structures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..entities import TestRun
from ..failures import (
    FilesystemFailure,
    TestExecutionFailure,
)
from ..result import Result, err, ok
from .base import BaseUseCase

# ---------------- run_widget_test ----------------------------------------


@dataclass(frozen=True, slots=True)
class RunWidgetTestParams:
    project_path: Path
    # All optional — at least one of {test_path, name_pattern} should
    # be set to target a meaningful subset. If both are empty, this
    # falls through to "run every test in test/" — same as
    # run_unit_tests but with the structured-failure path the widget
    # workflow expects.
    test_path: str | None = None        # e.g. "test/widgets/login_test.dart"
    name_pattern: str | None = None     # e.g. "login button"
    plain_name: bool = False            # True → --plain-name (literal)
    tags: str | None = None             # e.g. "golden" or "smoke"
    coverage: bool = False
    update_goldens: bool = False
    # "auto" (default) runs on the VM, then retries on `--platform chrome`
    # if a web-only library (dart:html, …) isn't available on the VM.
    # "vm" / "chrome" force the platform.
    platform: str = "auto"


class RunWidgetTest(BaseUseCase[RunWidgetTestParams, TestRun]):
    """Targeted widget-test runner.

    Examples agents will run:

      # Just the login-widget tests:
      run_widget_test(test_path="test/widgets/login_test.dart")

      # Every test whose name contains 'navigation':
      run_widget_test(name_pattern="navigation")

      # The golden-tagged subset, with goldens refreshed:
      run_widget_test(tags="golden", update_goldens=True)
    """

    def __init__(self, flutter_cli) -> None:
        self._cli = flutter_cli

    async def execute(self, params: RunWidgetTestParams) -> Result[TestRun]:
        from ...data.parsers.flutter_test_reporter_parser import (
            looks_like_web_platform_error,
            parse_flutter_json_reporter,
        )

        async def _run(cli_platform: str | None):
            return await self._cli.test_widget(
                project_path=params.project_path,
                test_path=params.test_path,
                name_pattern=params.name_pattern,
                tags=params.tags,
                plain_name=params.plain_name,
                coverage=params.coverage,
                update_goldens=params.update_goldens,
                platform=cli_platform,
            )

        # platform: "auto" | "vm" | "chrome" — mirrors run_unit_tests.
        if params.platform == "chrome":
            result = await _run("chrome")
        elif params.platform == "vm":
            result = await _run(None)
        else:  # auto: VM first, retry on chrome if web-only-lib error
            result = await _run(None)
            if looks_like_web_platform_error(result.stdout, result.stderr):
                result = await _run("chrome")

        run = parse_flutter_json_reporter(result.stdout)
        if not result.ok and run.total == 0:
            details: dict = {
                "platform": params.platform,
                "stderr_tail": (result.stderr or "")[-2000:],
                "filter_used": {
                    "test_path": params.test_path,
                    "name_pattern": params.name_pattern,
                    "tags": params.tags,
                },
            }
            if looks_like_web_platform_error(result.stdout, result.stderr):
                # Only reachable with an explicit wrong platform — auto retries.
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


# ---------------- list_widget_tests --------------------------------------


@dataclass(frozen=True, slots=True)
class ListWidgetTestsParams:
    project_path: Path
    # Default scans `test/`. Override if you organize tests
    # elsewhere — e.g. `lib/` if you co-locate (uncommon but legal).
    test_root: str = "test"


@dataclass(frozen=True, slots=True)
class WidgetTestEntry:
    file_path: str                    # path relative to project_path
    test_name: str                    # the string passed to testWidgets(...)
    line_number: int                  # 1-indexed
    is_golden: bool                   # true if the file imports matchesGoldenFile or testWidgets uses tags: ['golden']


@dataclass(frozen=True, slots=True)
class ListWidgetTestsResult:
    project_path: str
    test_root: str
    entries: tuple[WidgetTestEntry, ...]
    total_test_files: int
    total_test_widgets: int           # sum of testWidgets across all files


class ListWidgetTests(
    BaseUseCase[ListWidgetTestsParams, ListWidgetTestsResult]
):
    """Discovery — what widget tests exist without running them.

    Implemented as a regex scan of `test_root/**/*.dart`. The
    regex matches:

      testWidgets('description', ... )
      testWidgets("description", ... )
      testWidgets('description', tags: ['golden'], ...)

    Imperfect — it won't find tests whose names are computed
    (e.g. `testWidgets(getName(), ...)`), but those are rare and
    the agent can fall back to running the file directly.

    Golden detection is heuristic: file imports
    `package:flutter_test/flutter_test.dart` AND contains either
    `matchesGoldenFile` or a `tags: [..., 'golden', ...]` literal.
    """

    async def execute(
        self, params: ListWidgetTestsParams
    ) -> Result[ListWidgetTestsResult]:
        root = params.project_path / params.test_root
        if not root.is_dir():
            return err(
                FilesystemFailure(
                    message=(
                        f"test root {root} not found. Default is 'test/'; "
                        "pass test_root='<your-dir>' if you put tests "
                        "elsewhere."
                    ),
                    next_action="check_test_dir",
                )
            )

        entries: list[WidgetTestEntry] = []
        files_with_tests: set[Path] = set()
        # testWidgets('xxx' OR "xxx", ...). We don't capture the
        # second argument; just the description string.
        # `?P<q>` lets the regex match same-quoted opener+closer.
        test_widgets_re = re.compile(
            r"testWidgets\(\s*(?P<q>['\"])(?P<name>.*?)(?P=q)\s*,",
            re.MULTILINE,
        )
        golden_re = re.compile(r"matchesGoldenFile|tags:\s*\[[^\]]*['\"]golden['\"]")

        for path in sorted(root.rglob("*.dart")):
            try:
                source = path.read_text(encoding="utf-8")
            except OSError:
                # Unreadable file — skip rather than fail the whole listing.
                continue
            file_has_golden = bool(golden_re.search(source))
            # Build line-number lookup for the matches.
            matches = list(test_widgets_re.finditer(source))
            if not matches:
                continue
            files_with_tests.add(path)
            for m in matches:
                line = source[: m.start()].count("\n") + 1
                entries.append(
                    WidgetTestEntry(
                        file_path=str(path.relative_to(params.project_path)),
                        test_name=m.group("name"),
                        line_number=line,
                        is_golden=file_has_golden,
                    )
                )

        return ok(
            ListWidgetTestsResult(
                project_path=str(params.project_path),
                test_root=params.test_root,
                entries=tuple(entries),
                total_test_files=len(files_with_tests),
                total_test_widgets=len(entries),
            )
        )


# ---------------- update_goldens -----------------------------------------


@dataclass(frozen=True, slots=True)
class UpdateGoldensParams:
    project_path: Path
    # Same targeting flags as run_widget_test — usually you'd
    # narrow this to the specific test(s) you've intentionally
    # changed, not the whole suite (which would mask regressions).
    test_path: str | None = None
    name_pattern: str | None = None
    plain_name: bool = False
    tags: str | None = None


class UpdateGoldens(BaseUseCase[UpdateGoldensParams, TestRun]):
    """Regenerate golden images for the targeted tests.

    Safety: this is the one widget-testing tool that can silently
    erase a regression. Use only when you've **deliberately** changed
    the visible output (font, padding, color) and want the new
    rendering accepted as the new baseline.

    The MCP doesn't add extra confirmation — that's the agent's
    job. The use case description in the tool registry warns
    explicitly.
    """

    def __init__(self, flutter_cli) -> None:
        self._cli = flutter_cli

    async def execute(self, params: UpdateGoldensParams) -> Result[TestRun]:
        from ...data.parsers.flutter_test_reporter_parser import (
            parse_flutter_json_reporter,
        )

        result = await self._cli.test_widget(
            project_path=params.project_path,
            test_path=params.test_path,
            name_pattern=params.name_pattern,
            tags=params.tags,
            plain_name=params.plain_name,
            update_goldens=True,
        )
        run = parse_flutter_json_reporter(result.stdout)
        if not result.ok and run.total == 0:
            return err(
                TestExecutionFailure(
                    message="flutter test --update-goldens did not produce results",
                    details={"stderr_tail": (result.stderr or "")[-2000:]},
                )
            )
        return ok(run)


# ---------------- test_coverage_report -----------------------------------


@dataclass(frozen=True, slots=True)
class TestCoverageReportParams:
    project_path: Path
    # Optional path filter (same as RunWidgetTestParams).
    test_path: str | None = None
    # Coverage is path-based. To get per-feature coverage, pass a
    # subfolder of `lib/` here — only files under it are reported.
    coverage_filter_prefix: str | None = None       # e.g. "lib/features/auth/"
    fail_under: float | None = None                 # 0.0-1.0; if set, ok=false when below


@dataclass(frozen=True, slots=True)
class CoverageFile:
    path: str
    lines_total: int
    lines_covered: int
    coverage_pct: float                # 0.0-1.0


@dataclass(frozen=True, slots=True)
class TestCoverageReportResult:
    total_lines: int
    covered_lines: int
    coverage_pct: float                # overall
    threshold_pct: float | None
    passed_threshold: bool             # always true if no threshold set
    files: tuple[CoverageFile, ...]    # sorted: lowest coverage first
    test_run: TestRun                  # the underlying test results
    advice: str                        # paste-ready PR-comment line


class TestCoverageReport(
    BaseUseCase[TestCoverageReportParams, TestCoverageReportResult]
):
    """Runs `flutter test --coverage`, parses lcov, returns the report.

    Two usage patterns:

      # Sanity-check: what's our coverage today?
      test_coverage_report(project_path=...)

      # PR gate: fail if features/auth went below 80%
      test_coverage_report(
        project_path=...,
        coverage_filter_prefix="lib/features/auth/",
        fail_under=0.80,
      )

    The `advice` field is a paste-ready summary the agent can drop
    into a PR comment — covers the overall % + worst-3 files +
    pass/fail vs threshold.
    """

    def __init__(self, flutter_cli) -> None:
        self._cli = flutter_cli

    async def execute(
        self, params: TestCoverageReportParams
    ) -> Result[TestCoverageReportResult]:
        from ...data.parsers.flutter_test_reporter_parser import (
            parse_flutter_json_reporter,
        )

        # Run with coverage on.
        cli_result = await self._cli.test_widget(
            project_path=params.project_path,
            test_path=params.test_path,
            coverage=True,
        )
        test_run = parse_flutter_json_reporter(cli_result.stdout)

        # Whether or not tests passed, lcov.info is written if the
        # build/compile phase succeeded. We surface coverage even on
        # test failure so the agent can see "coverage 73% but 4 tests
        # are red — fix those, retry."
        lcov_path = params.project_path / "coverage" / "lcov.info"
        if not lcov_path.exists():
            return err(
                FilesystemFailure(
                    message=(
                        "coverage/lcov.info not produced. Check that "
                        "`flutter test --coverage` ran (the test phase "
                        "may have errored before coverage was emitted)."
                    ),
                    next_action="check_test_compile_errors",
                    details={
                        "stderr_tail": (cli_result.stderr or "")[-2000:],
                        "test_run_total": test_run.total,
                    },
                )
            )

        try:
            files = _parse_lcov(
                lcov_path.read_text(encoding="utf-8"),
                filter_prefix=params.coverage_filter_prefix,
            )
        except (OSError, ValueError) as e:
            return err(
                FilesystemFailure(
                    message=f"could not parse lcov.info: {e}",
                    next_action="check_lcov_format",
                )
            )

        if not files:
            # Filter matched nothing — degenerate but not an error.
            # Return zero-coverage with a clear note.
            total = 0
            covered = 0
            pct = 0.0
            advice = (
                f"No files matched filter {params.coverage_filter_prefix!r}. "
                "Check the filter prefix; lcov tracks `lib/` paths relative "
                "to project root."
            )
        else:
            total = sum(f.lines_total for f in files)
            covered = sum(f.lines_covered for f in files)
            pct = covered / total if total > 0 else 0.0
            # Sort by lowest coverage first — that's the agent's
            # next-fix queue.
            files = tuple(sorted(files, key=lambda f: f.coverage_pct))
            worst = files[:3]
            worst_str = ", ".join(
                f"{f.path} ({f.coverage_pct * 100:.0f}%)" for f in worst
            )
            advice = (
                f"Overall coverage: {pct * 100:.1f}% ({covered}/{total} lines). "
                f"Lowest-covered files: {worst_str}."
            )

        passed_threshold = (
            params.fail_under is None or pct >= params.fail_under
        )
        if params.fail_under is not None and not passed_threshold:
            advice = (
                f"❌ Coverage {pct * 100:.1f}% below threshold "
                f"{params.fail_under * 100:.1f}%. " + advice
            )

        return ok(
            TestCoverageReportResult(
                total_lines=total,
                covered_lines=covered,
                coverage_pct=pct,
                threshold_pct=params.fail_under,
                passed_threshold=passed_threshold,
                files=files,
                test_run=test_run,
                advice=advice,
            )
        )


# ---- lcov.info parser --------------------------------------------------


def _parse_lcov(content: str, filter_prefix: str | None) -> tuple[CoverageFile, ...]:
    """Parse the subset of lcov.info we care about.

    Format (one section per source file):
        SF:<path-to-file>
        DA:<line>,<hits>
        DA:<line>,<hits>
        ...
        end_of_record

    We count any DA line with hits > 0 as covered. Branch coverage
    (BRDA) is ignored — Flutter's `--coverage` emits limited branch
    data and Flutter projects typically gate on line coverage only.
    """
    files: list[CoverageFile] = []
    current_path: str | None = None
    total = 0
    covered = 0
    for line in content.splitlines():
        if line.startswith("SF:"):
            current_path = line[3:]
            total = 0
            covered = 0
        elif line.startswith("DA:") and current_path is not None:
            try:
                _, hits = line[3:].split(",", 1)
                total += 1
                if int(hits) > 0:
                    covered += 1
            except (ValueError, IndexError):
                continue
        elif line == "end_of_record" and current_path is not None:
            if filter_prefix is None or current_path.startswith(filter_prefix):
                pct = covered / total if total > 0 else 0.0
                files.append(
                    CoverageFile(
                        path=current_path,
                        lines_total=total,
                        lines_covered=covered,
                        coverage_pct=pct,
                    )
                )
            current_path = None
            total = 0
            covered = 0
    return tuple(files)
