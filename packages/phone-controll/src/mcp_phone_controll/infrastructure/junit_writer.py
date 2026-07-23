"""Minimal JUnit XML emitter for PlanRun.

Targets the JUnit-XML schema understood by GitHub Actions, GitLab Runners,
Jenkins, Buildkite, etc. — one <testsuite> per plan, one <testcase> per phase.

Failures and errors are distinguished:
- A failed phase whose error_code suggests *test* failure (TestExecutionFailure,
  HotReloadFailure, UiElementNotFoundFailure) becomes <failure>.
- Anything else (DeviceBusyFailure, FlutterCliFailure, etc.) becomes <error>.

VERDICT_BLOCKED auto-injected phases are skipped from the report — they're
just propagation markers, not real test cases.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..domain.entities import PlanRun, TestCase, TestRun, TestStatus

_FAILURE_CODES = frozenset(
    {
        "TestExecutionFailure",
        "HotReloadFailure",
        "UiElementNotFoundFailure",
        "TimeoutFailure",
        "VisionFailure",
    }
)


def write_junit(run: PlanRun, output_path: Path) -> Path:
    """Emit a JUnit-XML file at output_path. Returns the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suite = ET.Element("testsuite")
    suite.set("name", run.plan_name)
    suite.set("timestamp", run.started_at.isoformat())
    suite.set("time", f"{run.duration_ms / 1000.0:.3f}")

    real_phases = [p for p in run.phases if p.phase != "VERDICT_BLOCKED"]
    failures = [p for p in real_phases if not p.ok and (p.error_code in _FAILURE_CODES)]
    errors = [p for p in real_phases if not p.ok and p.error_code not in _FAILURE_CODES]
    skipped = [p for p in real_phases if p.actual_outcome == "skipped_after_terminal"]

    suite.set("tests", str(len(real_phases)))
    suite.set("failures", str(len(failures)))
    suite.set("errors", str(len(errors)))
    suite.set("skipped", str(len(skipped)))

    for phase in real_phases:
        case = ET.SubElement(suite, "testcase")
        case.set("name", phase.phase)
        case.set("classname", run.plan_name)
        case.set("time", f"{phase.duration_ms / 1000.0:.3f}")

        if phase in skipped:
            ET.SubElement(case, "skipped").text = phase.notes or "skipped"
            continue
        if not phase.ok:
            tag = "failure" if phase.error_code in _FAILURE_CODES else "error"
            element = ET.SubElement(case, tag)
            element.set("type", phase.error_code or "Failure")
            element.set("message", phase.error_message or "")

    tree = ET.ElementTree(suite)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path


def write_junit_testrun(
    run: TestRun,
    output_path: Path,
    *,
    suite_name: str = "patrol",
    overall_ok: bool = True,
) -> Path:
    """Emit JUnit XML for a Patrol/Playwright `TestRun` — one `<testcase>`
    per parsed case — so a web or mobile Patrol run becomes PR status in
    GitHub Actions / GitLab / Bitbucket Pipelines / Jenkins.

    This is distinct from `write_junit` (which maps a `PlanRun`'s phases):
    a Patrol run carries real per-test cases (name/status/duration/error),
    populated by both the Playwright-JSON parser (web) and the output
    scraper (mobile).

    Safety net — the load-bearing subtlety: Patrol's *mobile* output is
    scraped best-effort and can yield ZERO cases even on a genuine
    failure. An empty `<testsuite>` reads as GREEN in CI, the exact
    opposite of the truth. So when `run.cases` is empty we synthesize one
    testcase whose verdict follows the AUTHORITATIVE process exit code
    (`overall_ok`) — a failing run always produces red XML, never a silent
    pass.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suite = ET.Element("testsuite")
    suite.set("name", suite_name)
    suite.set("time", f"{run.duration_ms / 1000.0:.3f}")

    cases = list(run.cases)
    if not cases:
        status = TestStatus.PASSED if overall_ok else TestStatus.FAILED
        cases = [
            TestCase(
                name=suite_name,
                status=status,
                duration_ms=run.duration_ms,
                error_message=(
                    None
                    if overall_ok
                    else (
                        "patrol run failed (non-zero exit); per-test detail "
                        "unavailable — see the run logs"
                    )
                ),
            )
        ]

    failures = errors = skipped = 0
    for c in cases:
        case = ET.SubElement(suite, "testcase")
        case.set("name", c.name)
        case.set("classname", suite_name)
        case.set("time", f"{c.duration_ms / 1000.0:.3f}")
        if c.status is TestStatus.SKIPPED:
            skipped += 1
            ET.SubElement(case, "skipped").text = c.error_message or "skipped"
        elif c.status is TestStatus.ERRORED:
            errors += 1
            el = ET.SubElement(case, "error")
            el.set("message", c.error_message or "errored")
            if c.stack_trace:
                el.text = c.stack_trace
        elif c.status is TestStatus.FAILED:
            failures += 1
            el = ET.SubElement(case, "failure")
            el.set("message", c.error_message or "failed")
            if c.stack_trace:
                el.text = c.stack_trace

    total = len(cases)
    # The other half of the safety net: the run FAILED (non-zero exit) but
    # not one emitted case carries a failing/erroring status — e.g. Patrol's
    # mobile scraper matched only the passing `✓` lines and missed the one
    # that failed/crashed. Emitting failures=0 would read as GREEN in CI on a
    # genuinely failed run. Append a synthetic failure so the exit code (the
    # authoritative verdict) always wins. Mirrors the empty-cases branch
    # above, for the partial-parse case.
    if not overall_ok and failures == 0 and errors == 0:
        case = ET.SubElement(suite, "testcase")
        case.set("name", f"{suite_name}::run-verdict")
        case.set("classname", suite_name)
        case.set("time", "0.000")
        el = ET.SubElement(case, "failure")
        el.set(
            "message",
            "patrol run failed (non-zero exit) but no individual test was "
            "reported as failing — see the run logs; per-test detail may be "
            "incomplete.",
        )
        failures += 1
        total += 1

    suite.set("tests", str(total))
    suite.set("failures", str(failures))
    suite.set("errors", str(errors))
    suite.set("skipped", str(skipped))

    tree = ET.ElementTree(suite)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path
