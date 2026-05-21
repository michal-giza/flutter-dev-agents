"""Tests for the v0.3.0 widget-testing module.

Coverage goals:

- run_widget_test composes the right flutter-test argv (filter
  flags + reporter), and structured failures surface when no
  output is produced.
- list_widget_tests scans a real tmpdir-built fake project,
  finds testWidgets() blocks, detects golden tests by
  matchesGoldenFile + tags markers.
- update_goldens always sets the --update-goldens flag (verified
  via the recording fake CLI).
- test_coverage_report parses lcov, applies filter_prefix
  correctly, returns a sorted-by-lowest-coverage file list,
  computes overall percentage, and toggles passed_threshold.
- _parse_lcov handles the canonical lcov shape + degenerate
  cases (empty file, sections with no DA lines, malformed DA).

Hermetic — uses a recording fake FlutterCli that returns scripted
stdout. No real `flutter test` invocation needed in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.widget_testing import (
    ListWidgetTests,
    ListWidgetTestsParams,
    RunWidgetTest,
    RunWidgetTestParams,
    TestCoverageReport,
    TestCoverageReportParams,
    UpdateGoldens,
    UpdateGoldensParams,
    _parse_lcov,
)
from mcp_phone_controll.infrastructure.process_runner import ProcessResult

# ---- fake FlutterCli ---------------------------------------------------


class _FakeFlutterCli:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.calls: list[dict] = []

    async def test_widget(self, **kwargs):
        self.calls.append(kwargs)
        return ProcessResult(
            stdout=self.stdout,
            stderr=self.stderr,
            returncode=self.returncode,
        )


def _make_json_reporter_stdout(passed: int, failed: int = 0) -> str:
    """Build a minimal `flutter test --reporter=json` output."""
    lines = []
    # Suite start
    lines.append(json.dumps({
        "type": "suite",
        "suite": {"id": 0, "path": "test/widget_test.dart", "platform": "vm"},
    }))
    for i in range(passed + failed):
        # Test start
        lines.append(json.dumps({
            "type": "testStart",
            "test": {"id": i, "name": f"test_{i}", "suiteID": 0, "url": "file:///x"},
        }))
        # Test done
        lines.append(json.dumps({
            "type": "testDone",
            "testID": i,
            "result": "success" if i < passed else "failure",
            "time": 1000,
        }))
    # Final done event with totals
    lines.append(json.dumps({"type": "done", "success": failed == 0, "time": 1500}))
    return "\n".join(lines)


# ---- run_widget_test ---------------------------------------------------


@pytest.mark.asyncio
async def test_run_widget_test_passes_filters_to_cli(tmp_path: Path):
    """Every targeting flag set in params must reach the CLI."""
    cli = _FakeFlutterCli(stdout=_make_json_reporter_stdout(passed=3))
    res = await RunWidgetTest(cli)(
        RunWidgetTestParams(
            project_path=tmp_path,
            test_path="test/widgets/login_test.dart",
            name_pattern="login button",
            plain_name=True,
            tags="smoke",
            coverage=False,
            update_goldens=False,
        )
    )
    assert isinstance(res, Ok)
    call = cli.calls[0]
    assert call["test_path"] == "test/widgets/login_test.dart"
    assert call["name_pattern"] == "login button"
    assert call["plain_name"] is True
    assert call["tags"] == "smoke"
    assert call["coverage"] is False
    assert call["update_goldens"] is False


@pytest.mark.asyncio
async def test_run_widget_test_surfaces_failure_when_no_output(tmp_path: Path):
    """flutter test compile error + zero structured output → typed
    TestExecutionFailure with the filter context surfaced for
    debugging."""
    cli = _FakeFlutterCli(stdout="", stderr="error: kotlin compile failed", returncode=1)
    res = await RunWidgetTest(cli)(
        RunWidgetTestParams(
            project_path=tmp_path,
            test_path="test/widgets/login_test.dart",
        )
    )
    assert isinstance(res, Err)
    assert "filter_used" in res.failure.details
    assert res.failure.details["filter_used"]["test_path"] == "test/widgets/login_test.dart"


# ---- list_widget_tests -------------------------------------------------


@pytest.mark.asyncio
async def test_list_widget_tests_finds_testwidgets_blocks(tmp_path: Path):
    """Scan a real tmpdir-built project: 2 testWidgets in 1 file, 1
    in another. Should report 3 entries across 2 files."""
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    (test_dir / "login_test.dart").write_text(
        """
        import 'package:flutter_test/flutter_test.dart';

        void main() {
          testWidgets('login button shows', (WidgetTester tester) async {});
          testWidgets("password field accepts text", (WidgetTester tester) async {});
        }
        """
    )
    (test_dir / "home_test.dart").write_text(
        """
        testWidgets('home greeting renders', (WidgetTester tester) async {});
        """
    )

    res = await ListWidgetTests()(ListWidgetTestsParams(project_path=tmp_path))
    assert isinstance(res, Ok)
    v = res.value
    assert v.total_test_files == 2
    assert v.total_test_widgets == 3
    names = {e.test_name for e in v.entries}
    assert "login button shows" in names
    assert "password field accepts text" in names
    assert "home greeting renders" in names


@pytest.mark.asyncio
async def test_list_widget_tests_detects_golden_files(tmp_path: Path):
    """A file using matchesGoldenFile is flagged as golden."""
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    (test_dir / "golden_test.dart").write_text(
        """
        import 'package:flutter_test/flutter_test.dart';
        testWidgets('login screen golden', (WidgetTester tester) async {
          await expectLater(find.byType(MaterialApp), matchesGoldenFile('login.png'));
        });
        """
    )
    (test_dir / "plain_test.dart").write_text(
        """
        testWidgets('counter increments', (WidgetTester tester) async {});
        """
    )

    res = await ListWidgetTests()(ListWidgetTestsParams(project_path=tmp_path))
    assert isinstance(res, Ok)
    by_file = {e.file_path: e for e in res.value.entries}
    assert by_file["test/golden_test.dart"].is_golden is True
    assert by_file["test/plain_test.dart"].is_golden is False


@pytest.mark.asyncio
async def test_list_widget_tests_missing_root_returns_typed_failure(tmp_path: Path):
    res = await ListWidgetTests()(
        ListWidgetTestsParams(project_path=tmp_path, test_root="nonexistent_dir")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "check_test_dir"


# ---- update_goldens ----------------------------------------------------


@pytest.mark.asyncio
async def test_update_goldens_always_sets_flag(tmp_path: Path):
    """The whole point of this tool: the --update-goldens flag MUST
    reach the CLI, even when the agent forgets to pass it
    explicitly."""
    cli = _FakeFlutterCli(stdout=_make_json_reporter_stdout(passed=1))
    res = await UpdateGoldens(cli)(
        UpdateGoldensParams(
            project_path=tmp_path,
            test_path="test/widgets/login_test.dart",
        )
    )
    assert isinstance(res, Ok)
    assert cli.calls[0]["update_goldens"] is True


# ---- _parse_lcov -------------------------------------------------------


def test_parse_lcov_basic():
    """Canonical lcov shape — 2 files, computes line coverage."""
    lcov = """SF:lib/main.dart
DA:1,1
DA:2,1
DA:3,0
DA:4,2
end_of_record
SF:lib/foo.dart
DA:10,0
DA:11,0
end_of_record
"""
    files = _parse_lcov(lcov, filter_prefix=None)
    by_path = {f.path: f for f in files}
    assert by_path["lib/main.dart"].lines_total == 4
    assert by_path["lib/main.dart"].lines_covered == 3
    assert abs(by_path["lib/main.dart"].coverage_pct - 0.75) < 0.01
    assert by_path["lib/foo.dart"].lines_covered == 0
    assert by_path["lib/foo.dart"].coverage_pct == 0.0


def test_parse_lcov_filter_prefix():
    """filter_prefix='lib/features/' includes only matching paths."""
    lcov = """SF:lib/features/auth/login.dart
DA:1,1
end_of_record
SF:lib/main.dart
DA:1,1
end_of_record
"""
    files = _parse_lcov(lcov, filter_prefix="lib/features/")
    paths = {f.path for f in files}
    assert "lib/features/auth/login.dart" in paths
    assert "lib/main.dart" not in paths


def test_parse_lcov_handles_malformed_DA_gracefully():
    """A malformed DA line shouldn't crash the parser."""
    lcov = """SF:lib/main.dart
DA:badly_formatted
DA:1,1
end_of_record
"""
    files = _parse_lcov(lcov, filter_prefix=None)
    assert len(files) == 1
    # Malformed DA skipped; second DA counted
    assert files[0].lines_total == 1
    assert files[0].lines_covered == 1


def test_parse_lcov_empty_input():
    assert _parse_lcov("", filter_prefix=None) == ()


# ---- test_coverage_report ----------------------------------------------


@pytest.mark.asyncio
async def test_coverage_report_happy(tmp_path: Path):
    """Tests pass, lcov exists, parses cleanly, advice line forms."""
    coverage_dir = tmp_path / "coverage"
    coverage_dir.mkdir()
    (coverage_dir / "lcov.info").write_text(
        """SF:lib/main.dart
DA:1,1
DA:2,1
DA:3,0
end_of_record
SF:lib/features/auth/login.dart
DA:1,1
DA:2,0
DA:3,0
DA:4,0
end_of_record
"""
    )
    cli = _FakeFlutterCli(stdout=_make_json_reporter_stdout(passed=5))
    res = await TestCoverageReport(cli)(
        TestCoverageReportParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    v = res.value
    # 2/3 main + 1/4 login = 3/7 lines covered overall
    assert v.total_lines == 7
    assert v.covered_lines == 3
    assert abs(v.coverage_pct - 3 / 7) < 0.01
    # Sorted ascending → login (25%) before main (66%)
    assert v.files[0].path == "lib/features/auth/login.dart"
    assert v.passed_threshold is True  # no threshold set


@pytest.mark.asyncio
async def test_coverage_report_filter_prefix_narrows_files(tmp_path: Path):
    coverage_dir = tmp_path / "coverage"
    coverage_dir.mkdir()
    (coverage_dir / "lcov.info").write_text(
        """SF:lib/features/auth/login.dart
DA:1,1
DA:2,0
end_of_record
SF:lib/main.dart
DA:1,1
end_of_record
"""
    )
    cli = _FakeFlutterCli(stdout=_make_json_reporter_stdout(passed=1))
    res = await TestCoverageReport(cli)(
        TestCoverageReportParams(
            project_path=tmp_path,
            coverage_filter_prefix="lib/features/auth/",
        )
    )
    assert isinstance(res, Ok)
    v = res.value
    assert len(v.files) == 1
    assert v.files[0].path == "lib/features/auth/login.dart"
    assert v.total_lines == 2


@pytest.mark.asyncio
async def test_coverage_report_threshold_fail(tmp_path: Path):
    """fail_under=0.80, actual coverage 50% → passed_threshold=False."""
    coverage_dir = tmp_path / "coverage"
    coverage_dir.mkdir()
    (coverage_dir / "lcov.info").write_text(
        """SF:lib/main.dart
DA:1,1
DA:2,0
end_of_record
"""
    )
    cli = _FakeFlutterCli(stdout=_make_json_reporter_stdout(passed=1))
    res = await TestCoverageReport(cli)(
        TestCoverageReportParams(project_path=tmp_path, fail_under=0.80)
    )
    assert isinstance(res, Ok)
    assert res.value.passed_threshold is False
    assert "below threshold" in res.value.advice.lower()


@pytest.mark.asyncio
async def test_coverage_report_missing_lcov_returns_typed_failure(tmp_path: Path):
    """If lcov.info wasn't written (compile error before coverage
    phase), surface a clear next_action."""
    cli = _FakeFlutterCli(stdout="", stderr="error: compile failed", returncode=1)
    res = await TestCoverageReport(cli)(
        TestCoverageReportParams(project_path=tmp_path)
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "check_test_compile_errors"
