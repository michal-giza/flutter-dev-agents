"""write_junit_testrun — Patrol/Playwright TestRun -> JUnit XML for CI/PR.

The load-bearing case is the empty-parse safety net: a mobile Patrol run
that scrapes ZERO cases but exits non-zero must still emit RED XML, never
an empty (CI-green) suite. Everything else is faithful per-case mapping.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from mcp_phone_controll.domain.entities import TestCase, TestRun, TestStatus
from mcp_phone_controll.infrastructure.junit_writer import write_junit_testrun


def _run(cases, duration_ms=1000):
    passed = sum(1 for c in cases if c.status is TestStatus.PASSED)
    failed = sum(1 for c in cases if c.status is TestStatus.FAILED)
    errored = sum(1 for c in cases if c.status is TestStatus.ERRORED)
    skipped = sum(1 for c in cases if c.status is TestStatus.SKIPPED)
    return TestRun(
        total=len(cases),
        passed=passed,
        failed=failed,
        errored=errored,
        skipped=skipped,
        duration_ms=duration_ms,
        cases=cases,
    )


def _parse(path: Path):
    return ET.parse(path).getroot()


def test_per_case_mapping(tmp_path: Path):
    run = _run(
        [
            TestCase("logs in", TestStatus.PASSED, 1200),
            TestCase("checkout", TestStatus.FAILED, 800, error_message="expected cart empty"),
            TestCase("promo", TestStatus.SKIPPED, 0),
            TestCase("sync", TestStatus.ERRORED, 50, error_message="TimeoutException"),
        ]
    )
    out = write_junit_testrun(run, tmp_path / "r.xml", suite_name="app_test", overall_ok=False)
    root = _parse(out)
    assert root.tag == "testsuite"
    assert root.get("tests") == "4"
    assert root.get("failures") == "1"
    assert root.get("errors") == "1"
    assert root.get("skipped") == "1"
    cases = root.findall("testcase")
    assert [c.get("name") for c in cases] == ["logs in", "checkout", "promo", "sync"]
    # the failed case carries a <failure> with the message
    failed = cases[1]
    assert failed.find("failure") is not None
    assert failed.find("failure").get("message") == "expected cart empty"
    assert cases[2].find("skipped") is not None
    assert cases[3].find("error") is not None


def test_empty_cases_failed_run_stays_red(tmp_path: Path):
    """The safety net: no parsed cases + failing exit => a synthetic
    failing testcase, NOT an empty (green) suite."""
    run = _run([], duration_ms=4200)
    out = write_junit_testrun(run, tmp_path / "r.xml", suite_name="mobile_suite", overall_ok=False)
    root = _parse(out)
    assert root.get("tests") == "1"
    assert root.get("failures") == "1"
    case = root.find("testcase")
    assert case.get("name") == "mobile_suite"
    assert case.find("failure") is not None


def test_empty_cases_passing_run_is_green(tmp_path: Path):
    run = _run([], duration_ms=3000)
    out = write_junit_testrun(run, tmp_path / "r.xml", suite_name="mobile_suite", overall_ok=True)
    root = _parse(out)
    assert root.get("tests") == "1"
    assert root.get("failures") == "0"
    case = root.find("testcase")
    assert case.find("failure") is None
    assert case.find("error") is None


def test_failed_run_with_only_passing_cases_stays_red(tmp_path: Path):
    """The partial-scrape trap: the run FAILED (overall_ok=False) but the
    scraper only itemised the passing tests. A green suite here would hide a
    real CI failure — a synthetic failing case must be appended."""
    run = _run([TestCase("test_a", TestStatus.PASSED, 1200)])
    # emulate parse_patrol_output bumping failed without adding a case
    run = TestRun(
        total=2, passed=1, failed=1, errored=0, skipped=0,
        duration_ms=run.duration_ms, cases=list(run.cases),
    )
    out = write_junit_testrun(run, tmp_path / "r.xml", suite_name="mob", overall_ok=False)
    root = _parse(out)
    assert root.get("tests") == "2"       # the passing case + the synthetic one
    assert root.get("failures") == "1"    # NOT green
    names = [c.get("name") for c in root.findall("testcase")]
    assert "mob::run-verdict" in names


def test_failed_run_with_a_real_failing_case_adds_no_synthetic(tmp_path: Path):
    """If a case already carries the failure, don't double-count it."""
    run = _run(
        [
            TestCase("a", TestStatus.PASSED, 10),
            TestCase("b", TestStatus.FAILED, 20, error_message="boom"),
        ]
    )
    out = write_junit_testrun(run, tmp_path / "r.xml", suite_name="s", overall_ok=False)
    root = _parse(out)
    assert root.get("tests") == "2"       # no synthetic appended
    assert root.get("failures") == "1"


def test_creates_parent_dirs(tmp_path: Path):
    run = _run([TestCase("ok", TestStatus.PASSED, 10)])
    out = write_junit_testrun(
        run, tmp_path / "nested" / "deep" / "r.xml", suite_name="s", overall_ok=True
    )
    assert out.exists()
