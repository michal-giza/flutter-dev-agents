"""Parse Patrol's WEB results (a Playwright JSON report) into a TestRun.

Patrol 4 runs Flutter web through Playwright, and `patrol test -d chrome`
accepts `--web-reporter '["json"]'` + `--web-results-dir <dir>` (verified
in patrol_cli 4.5.1 `--help`: the reporter value is a JSON ARRAY STRING).
That gives us a real machine-readable result file — so web runs get exact
counts instead of the best-effort scraping the native path has to use.

Playwright's JSON report shape (stable across 1.x):

    {"suites": [{"specs": [{"title": "...", "tests": [
        {"results": [{"status": "passed|failed|timedOut|skipped",
                      "duration": 1234}]}]}],
      "suites": [ ...nested... ]}],
     "stats": {"expected": 3, "unexpected": 1, "skipped": 0, ...}}

We walk the suite tree for per-test detail and fall back to `stats` when
the tree isn't itemisable. Returns None when no usable report is found,
so the caller can fall back to the exit code rather than claim "0 tests".
"""

from __future__ import annotations

import json
from pathlib import Path

from ...domain.entities import TestCase, TestRun, TestStatus

# Playwright statuses → ours. `timedOut`/`interrupted` are failures;
# `expected`/`passed` pass; `unexpected` is a failure in stats-speak.
_STATUS = {
    "passed": TestStatus.PASSED,
    "expected": TestStatus.PASSED,
    "failed": TestStatus.FAILED,
    "unexpected": TestStatus.FAILED,
    "timedout": TestStatus.FAILED,
    "interrupted": TestStatus.FAILED,
    "skipped": TestStatus.SKIPPED,
}


def find_report(results_dir: Path) -> Path | None:
    """Locate the Playwright JSON report under `results_dir`.

    Patrol doesn't document the exact filename, so accept any *.json and
    prefer the conventional names. Newest wins on ties.
    """
    if not results_dir.is_dir():
        return None
    candidates = sorted(
        results_dir.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        return None
    for preferred in ("results.json", "report.json", "test-results.json"):
        for path in candidates:
            if path.name == preferred:
                return path
    return candidates[0]


def parse_playwright_report(path: Path) -> TestRun | None:
    """TestRun from a Playwright JSON report, or None if unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    cases: list[TestCase] = []
    _walk_suites(data.get("suites") or [], cases)

    if cases:
        passed = sum(1 for c in cases if c.status is TestStatus.PASSED)
        failed = sum(1 for c in cases if c.status is TestStatus.FAILED)
        skipped = sum(1 for c in cases if c.status is TestStatus.SKIPPED)
        return TestRun(
            total=len(cases),
            passed=passed,
            failed=failed,
            errored=0,
            skipped=skipped,
            duration_ms=sum(c.duration_ms for c in cases),
            cases=cases,
        )

    # No itemisable specs — fall back to the aggregate stats block.
    stats = data.get("stats")
    if isinstance(stats, dict):
        passed = int(stats.get("expected") or 0)
        failed = int(stats.get("unexpected") or 0)
        skipped = int(stats.get("skipped") or 0)
        flaky = int(stats.get("flaky") or 0)
        if passed or failed or skipped or flaky:
            return TestRun(
                total=passed + failed + skipped + flaky,
                passed=passed + flaky,   # flaky = passed on retry
                failed=failed,
                errored=0,
                skipped=skipped,
                duration_ms=int(stats.get("duration") or 0),
                cases=[],
            )
    return None


def _walk_suites(suites: list, out: list[TestCase]) -> None:
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        for spec in suite.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            title = str(spec.get("title") or "").strip() or "<unnamed>"
            status, duration = _spec_outcome(spec)
            out.append(TestCase(name=title, status=status, duration_ms=duration))
        _walk_suites(suite.get("suites") or [], out)


def _spec_outcome(spec: dict) -> tuple[TestStatus, int]:
    """A spec passes only if every attempt's final result passed. Playwright
    records one `results` entry per retry — the LAST is authoritative."""
    status = TestStatus.PASSED
    duration = 0
    saw_result = False
    for test in spec.get("tests") or []:
        if not isinstance(test, dict):
            continue
        results = [r for r in (test.get("results") or []) if isinstance(r, dict)]
        if not results:
            continue
        saw_result = True
        last = results[-1]
        duration += int(last.get("duration") or 0)
        mapped = _STATUS.get(str(last.get("status") or "").lower())
        if mapped is TestStatus.FAILED:
            status = TestStatus.FAILED
        elif mapped is TestStatus.SKIPPED and status is TestStatus.PASSED:
            status = TestStatus.SKIPPED
    if not saw_result:
        # Playwright marks a never-run spec as skipped via spec.ok/annotations.
        return (TestStatus.SKIPPED, 0)
    return (status, duration)
