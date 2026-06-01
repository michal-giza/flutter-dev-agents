"""Ingest Maestro execution reports.

Maestro emits JUnit XML by default (`maestro test --format junit
--output report.xml`) or JSON via `--format json`. This use case
parses either, computes flake / pass / fail signals, and
surfaces them so the agent can:

  - Pick the worst-offender flow to fix first
  - Feed the result into `audit_release_readiness` as a 6th
    `test_execution` domain (phase 14.5)

Why this is "ingest" not "run":

  Maestro's own MCP has `run` — they execute. We don't compete.
  We're the layer that interprets the report. Same posture as
  `audit_test_quality` (we don't run `flutter test`; we audit
  the test code).

What this catches:

  - Total flow count + pass / fail / flaky breakdown
  - Per-flow runtime (slowest flow + outliers)
  - Regressions (passed in prior, failed now)
  - Failure clusters by file or by error message

What this is NOT:

  - Not a runner — invoke Maestro for that
  - Not a CI integrator — you bring the report path, we parse
  - Not a Maestro Cloud client — local + cloud-exported reports
    both work via the JUnit XML or JSON format

Pure compute. Stdlib XML + json parsing only.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from .base import BaseUseCase


class FlowOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    FLAKY = "flaky"      # passed on retry
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FlowExecution:
    name: str
    file: str | None
    outcome: str             # FlowOutcome value
    runtime_s: float
    error_message: str | None
    retries: int             # 0 if first pass


@dataclass(frozen=True, slots=True)
class IngestMaestroReportParams:
    # Path to JUnit XML report OR JSON report, OR a directory
    # that Maestro wrote (we find the report inside).
    report_path: Path
    # Optional: a prior report to diff against for regression
    # detection (passed_then → failed_now).
    prior_report_path: Path | None = None


@dataclass(frozen=True, slots=True)
class IngestMaestroReportResult:
    grade: str                       # clean / acceptable / at_risk / blocked
    score: float                     # weighted failures per flow
    flows_total: int
    flows_passed: int
    flows_failed: int
    flows_flaky: int
    flows_skipped: int
    flake_rate: float                # flaky / total
    pass_rate: float                 # passed / (passed + failed)
    average_runtime_s: float
    slowest_flow: str | None
    slowest_runtime_s: float
    flows: tuple[FlowExecution, ...]
    regressions: tuple[str, ...]     # flow names that passed_then → failed_now
    top_failures: tuple[str, ...]    # paste-ready: "name — error preview"
    advice: str


class IngestMaestroReport(
    BaseUseCase[IngestMaestroReportParams, IngestMaestroReportResult]
):
    """Parse a Maestro JUnit XML or JSON report, surface signals.

    Pure compute. Stdlib only. No PyYAML, no external XML libs.
    """

    async def execute(
        self, params: IngestMaestroReportParams
    ) -> Result[IngestMaestroReportResult]:
        report_file = _resolve_report_file(params.report_path)
        if report_file is None or not report_file.is_file():
            return err(FilesystemFailure(
                message=(
                    f"report not found at {params.report_path}. "
                    "Pass a .xml (JUnit) or .json (Maestro) file, or "
                    "a directory containing one."
                ),
                next_action="fix_arguments",
            ))

        try:
            text = report_file.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return err(FilesystemFailure(
                message=f"could not read report: {e}",
                next_action="fix_arguments",
            ))

        if report_file.suffix.lower() == ".xml" or "<testsuite" in text:
            try:
                flows = _parse_junit_xml(text)
            except ET.ParseError as e:
                return err(FilesystemFailure(
                    message=f"malformed JUnit XML: {e}",
                    next_action="fix_arguments",
                ))
        elif report_file.suffix.lower() == ".json" or text.lstrip().startswith("{"):
            try:
                flows = _parse_maestro_json(text)
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                return err(FilesystemFailure(
                    message=f"malformed Maestro JSON: {e}",
                    next_action="fix_arguments",
                ))
        else:
            return err(FilesystemFailure(
                message=(
                    f"unsupported report format {report_file.suffix!r}. "
                    "Expected .xml or .json."
                ),
                next_action="fix_arguments",
            ))

        prior_passed: set[str] = set()
        if params.prior_report_path is not None:
            prior_file = _resolve_report_file(params.prior_report_path)
            if prior_file is not None and prior_file.is_file():
                try:
                    prior_text = prior_file.read_text(
                        encoding="utf-8", errors="replace",
                    )
                    if prior_file.suffix.lower() == ".xml" or "<testsuite" in prior_text:
                        prior_flows = _parse_junit_xml(prior_text)
                    else:
                        prior_flows = _parse_maestro_json(prior_text)
                    prior_passed = {
                        f.name for f in prior_flows
                        if f.outcome == FlowOutcome.PASSED.value
                    }
                except (ET.ParseError, json.JSONDecodeError, OSError):
                    # Silently skip — regression detection is optional
                    pass

        # Aggregate
        flows_passed = sum(1 for f in flows if f.outcome == "passed")
        flows_failed = sum(1 for f in flows if f.outcome == "failed")
        flows_flaky = sum(1 for f in flows if f.outcome == "flaky")
        flows_skipped = sum(1 for f in flows if f.outcome == "skipped")
        flows_total = len(flows)

        flake_rate = (
            flows_flaky / flows_total if flows_total > 0 else 0.0
        )
        denom = flows_passed + flows_failed
        pass_rate = flows_passed / denom if denom > 0 else 0.0
        runtimes = [f.runtime_s for f in flows if f.runtime_s > 0]
        average_runtime_s = (
            sum(runtimes) / len(runtimes) if runtimes else 0.0
        )
        if flows:
            slowest = max(flows, key=lambda f: f.runtime_s)
            slowest_flow = slowest.name
            slowest_runtime_s = slowest.runtime_s
        else:
            slowest_flow = None
            slowest_runtime_s = 0.0

        # Regressions
        regressions = tuple(sorted({
            f.name for f in flows
            if f.outcome == "failed" and f.name in prior_passed
        }))

        # Top failures (with brief error preview)
        top_failures = _build_top_failures(flows)

        # Grade
        grade = _grade_for(
            flows_failed, flake_rate, pass_rate, flows_total,
        )
        score = (
            flows_failed * 10 + flows_flaky * 4
        ) / max(flows_total, 1)

        return ok(IngestMaestroReportResult(
            grade=grade,
            score=round(score, 2),
            flows_total=flows_total,
            flows_passed=flows_passed,
            flows_failed=flows_failed,
            flows_flaky=flows_flaky,
            flows_skipped=flows_skipped,
            flake_rate=round(flake_rate, 3),
            pass_rate=round(pass_rate, 3),
            average_runtime_s=round(average_runtime_s, 2),
            slowest_flow=slowest_flow,
            slowest_runtime_s=round(slowest_runtime_s, 2),
            flows=tuple(flows),
            regressions=regressions,
            top_failures=top_failures,
            advice=_build_advice(
                grade, flows_total, flows_passed, flows_failed,
                flows_flaky, flake_rate, len(regressions),
            ),
        ))


# ============================================================
# File resolution
# ============================================================


def _resolve_report_file(path: Path) -> Path | None:
    """Accept a file directly OR a directory containing a
    Maestro report. Maestro CLI writes `report.xml` /
    `report.json` by default."""
    if path.is_file():
        return path
    if path.is_dir():
        # Search common names + extensions
        for candidate in (
            "report.xml", "junit.xml", "maestro.xml",
            "report.json", "maestro.json",
            "test-results.xml",
        ):
            f = path / candidate
            if f.is_file():
                return f
        # Otherwise pick the first XML or JSON we find
        for ext in (".xml", ".json"):
            for f in sorted(path.glob(f"*{ext}")):
                return f
    return None


# ============================================================
# JUnit XML parser
# ============================================================


def _parse_junit_xml(text: str) -> list[FlowExecution]:
    """Parse JUnit-style `<testsuite><testcase>` structure.
    Maestro emits one testcase per flow."""
    root = ET.fromstring(text)
    # root could be <testsuites> or <testsuite>
    suites = (
        list(root.findall("testsuite"))
        if root.tag == "testsuites"
        else [root]
    )

    out: list[FlowExecution] = []
    for suite in suites:
        for case in suite.findall("testcase"):
            name = case.get("name", "<unnamed>")
            classname = case.get("classname")
            file_hint = classname if classname and "." in classname else None
            time_s_str = case.get("time", "0")
            try:
                runtime_s = float(time_s_str)
            except ValueError:
                runtime_s = 0.0

            outcome = FlowOutcome.PASSED
            error_message: str | None = None
            retries = 0

            # JUnit conventions:
            #   <failure> / <error> child → failed
            #   <skipped> child → skipped
            #   <flaky-failure> (some emitters) → flaky
            #   <rerunFailure> (Maven Surefire convention) → flaky
            failure_el = case.find("failure")
            error_el = case.find("error")
            skipped_el = case.find("skipped")
            flaky_el = case.find("flaky-failure")
            rerun_el = case.find("rerunFailure")

            if skipped_el is not None:
                outcome = FlowOutcome.SKIPPED
            elif flaky_el is not None or rerun_el is not None:
                outcome = FlowOutcome.FLAKY
                src_el = flaky_el if flaky_el is not None else rerun_el
                error_message = (
                    src_el.get("message")
                    or (src_el.text or "").strip()[:200]
                    or None
                )
                retries = 1
            elif failure_el is not None or error_el is not None:
                outcome = FlowOutcome.FAILED
                src_el = failure_el if failure_el is not None else error_el
                error_message = (
                    src_el.get("message")
                    or (src_el.text or "").strip()[:200]
                    or None
                )

            out.append(FlowExecution(
                name=name,
                file=file_hint,
                outcome=outcome.value,
                runtime_s=runtime_s,
                error_message=error_message,
                retries=retries,
            ))
    return out


# ============================================================
# Maestro JSON parser
# ============================================================


def _parse_maestro_json(text: str) -> list[FlowExecution]:
    """Parse Maestro's JSON report format.

    Shape is roughly:
        {
          "summary": {...},
          "flows": [
            {"name": "...", "status": "passed|failed|skipped",
             "duration": 12.3, "error": "...", "retries": 0,
             "file": "..."}
          ]
        }

    Older Maestro versions emit a flat list. Handle both.
    """
    data = json.loads(text)
    raw_flows = data.get("flows") if isinstance(data, dict) else None
    if raw_flows is None and isinstance(data, list):
        raw_flows = data
    if not raw_flows:
        return []

    out: list[FlowExecution] = []
    for item in raw_flows:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("flow") or "<unnamed>"
        status = (item.get("status") or item.get("outcome") or "").lower()
        if status in ("pass", "passed", "success"):
            outcome = FlowOutcome.PASSED
        elif status in ("fail", "failed", "error"):
            outcome = FlowOutcome.FAILED
        elif status in ("skip", "skipped"):
            outcome = FlowOutcome.SKIPPED
        elif status in ("flaky", "passed_with_retry"):
            outcome = FlowOutcome.FLAKY
        else:
            outcome = FlowOutcome.UNKNOWN

        try:
            runtime_s = float(
                item.get("duration") or item.get("durationSeconds")
                or item.get("durationMs", 0) / 1000.0
                or 0.0
            )
        except (TypeError, ValueError):
            runtime_s = 0.0

        out.append(FlowExecution(
            name=str(name),
            file=item.get("file") or item.get("path"),
            outcome=outcome.value,
            runtime_s=runtime_s,
            error_message=(
                str(item["error"])[:200] if item.get("error") else None
            ),
            retries=int(item.get("retries", 0) or 0),
        ))
    return out


# ============================================================
# Aggregations / grading
# ============================================================


def _build_top_failures(
    flows: list[FlowExecution],
) -> tuple[str, ...]:
    """Top 5 failed flows formatted for the report."""
    failed = [f for f in flows if f.outcome == "failed"]
    failed.sort(key=lambda f: -f.runtime_s)  # slowest failures first
    out: list[str] = []
    for f in failed[:5]:
        err_preview = (
            re.sub(r"\s+", " ", f.error_message)[:100]
            if f.error_message else "(no error message)"
        )
        out.append(f"{f.name} — {err_preview}")
    return tuple(out)


def _grade_for(
    failed: int, flake_rate: float, pass_rate: float, total: int,
) -> str:
    if total == 0:
        return "clean"  # empty report — no signal either way
    if failed > 0:
        return "blocked"
    if flake_rate >= 0.10:  # 10%+ flake rate
        return "at_risk"
    if pass_rate < 1.0 or flake_rate > 0:
        return "acceptable"
    return "clean"


def _build_advice(
    grade: str, total: int, passed: int, failed: int, flaky: int,
    flake_rate: float, regressions: int,
) -> str:
    parts = [
        f"Maestro execution grade: {grade}.",
        f"{passed}/{total} passed, {failed} failed, {flaky} flaky "
        f"({flake_rate * 100:.0f}% flake rate).",
    ]
    if regressions > 0:
        parts.append(
            f"⚠ {regressions} regression(s) vs prior report — these "
            "passed last run."
        )
    if failed > 0:
        parts.append("STOP — resolve failures before merging.")
    elif flake_rate >= 0.10:
        parts.append(
            "Flake rate above 10% — investigate / tag with @flaky / "
            "stabilise before adding more flows."
        )
    return " ".join(parts)
