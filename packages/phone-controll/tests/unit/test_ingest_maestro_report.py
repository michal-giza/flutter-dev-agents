"""Tests for v0.4.0 phase-14 Maestro report ingestion.

JUnit XML + Maestro JSON parsing, flake/regression detection,
grading. We don't run Maestro; we parse what it produces.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.ingest_maestro_report import (
    IngestMaestroReport,
    IngestMaestroReportParams,
)


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


async def _run(**kwargs) -> Ok | Err:
    return await IngestMaestroReport()(
        IngestMaestroReportParams(**kwargs)
    )


# ---- error handling ----------------------------------------------------


@pytest.mark.asyncio
async def test_missing_report_returns_failure(tmp_path: Path):
    res = await _run(report_path=tmp_path / "nope.xml")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_malformed_xml_returns_failure(tmp_path: Path):
    bad = _write(tmp_path / "report.xml", "<testsuite><not-closed>")
    res = await _run(report_path=bad)
    assert isinstance(res, Err)
    assert "malformed" in res.failure.message.lower()


@pytest.mark.asyncio
async def test_malformed_json_returns_failure(tmp_path: Path):
    bad = _write(tmp_path / "report.json", "{not valid json")
    res = await _run(report_path=bad)
    assert isinstance(res, Err)


@pytest.mark.asyncio
async def test_unsupported_extension_returns_failure(tmp_path: Path):
    bad = _write(tmp_path / "report.txt", "passed")
    res = await _run(report_path=bad)
    assert isinstance(res, Err)


@pytest.mark.asyncio
async def test_directory_with_report_xml_resolved(tmp_path: Path):
    """When given a directory, find report.xml inside."""
    _write(
        tmp_path / "report.xml",
        "<testsuite name='maestro' tests='1'>"
        "<testcase name='login' classname='login.yaml' time='2.5'/>"
        "</testsuite>",
    )
    res = await _run(report_path=tmp_path)
    assert isinstance(res, Ok)
    assert res.value.flows_total == 1


# ---- JUnit XML parsing -------------------------------------------------


@pytest.mark.asyncio
async def test_junit_all_passed_returns_clean(tmp_path: Path):
    _write(
        tmp_path / "report.xml",
        "<testsuites>"
        "<testsuite name='maestro' tests='3'>"
        "<testcase name='login' classname='login.yaml' time='2.5'/>"
        "<testcase name='signup' classname='signup.yaml' time='3.1'/>"
        "<testcase name='checkout' classname='checkout.yaml' time='5.7'/>"
        "</testsuite>"
        "</testsuites>",
    )
    res = await _run(report_path=tmp_path / "report.xml")
    assert isinstance(res, Ok)
    v = res.value
    assert v.flows_total == 3
    assert v.flows_passed == 3
    assert v.flows_failed == 0
    assert v.flows_flaky == 0
    assert v.grade == "clean"
    assert v.pass_rate == 1.0
    assert v.slowest_flow == "checkout"


@pytest.mark.asyncio
async def test_junit_with_failure_returns_blocked(tmp_path: Path):
    _write(
        tmp_path / "report.xml",
        "<testsuite name='maestro' tests='2'>"
        "<testcase name='login' time='2.5'/>"
        "<testcase name='checkout' time='3.0'>"
        "<failure message='element not found'>Element &quot;Buy&quot; not visible</failure>"
        "</testcase>"
        "</testsuite>",
    )
    res = await _run(report_path=tmp_path / "report.xml")
    assert isinstance(res, Ok)
    v = res.value
    assert v.flows_failed == 1
    assert v.grade == "blocked"
    assert "STOP" in v.advice
    # error message preserved (truncated to 200 chars)
    failed = next(f for f in v.flows if f.name == "checkout")
    assert failed.outcome == "failed"
    assert failed.error_message is not None
    assert "Buy" in failed.error_message or "element not found" in failed.error_message


@pytest.mark.asyncio
async def test_junit_with_skipped_counted_separately(tmp_path: Path):
    _write(
        tmp_path / "report.xml",
        "<testsuite name='maestro' tests='2'>"
        "<testcase name='login' time='2.5'/>"
        "<testcase name='offline_test' time='0'>"
        "<skipped message='requires offline harness'/>"
        "</testcase>"
        "</testsuite>",
    )
    res = await _run(report_path=tmp_path / "report.xml")
    assert isinstance(res, Ok)
    v = res.value
    assert v.flows_skipped == 1
    assert v.flows_passed == 1


@pytest.mark.asyncio
async def test_junit_flaky_failure_treated_as_flaky(tmp_path: Path):
    _write(
        tmp_path / "report.xml",
        "<testsuite name='maestro' tests='2'>"
        "<testcase name='login' time='2.5'/>"
        "<testcase name='shaky' time='3.0'>"
        "<flaky-failure message='timing'>Element appeared late</flaky-failure>"
        "</testcase>"
        "</testsuite>",
    )
    res = await _run(report_path=tmp_path / "report.xml")
    assert isinstance(res, Ok)
    v = res.value
    assert v.flows_flaky == 1
    assert v.flake_rate == 0.5
    # flake_rate 50% >= 10% threshold → at_risk (no failures so not blocked)
    assert v.grade == "at_risk"


# ---- Maestro JSON parsing ----------------------------------------------


@pytest.mark.asyncio
async def test_maestro_json_all_passed(tmp_path: Path):
    report = {
        "summary": {"total": 2, "passed": 2, "failed": 0},
        "flows": [
            {"name": "login", "status": "passed", "duration": 2.5,
             "file": "login.yaml"},
            {"name": "signup", "status": "passed", "duration": 3.1,
             "file": "signup.yaml"},
        ],
    }
    _write(tmp_path / "report.json", json.dumps(report))
    res = await _run(report_path=tmp_path / "report.json")
    assert isinstance(res, Ok)
    v = res.value
    assert v.flows_total == 2
    assert v.flows_passed == 2
    assert v.grade == "clean"


@pytest.mark.asyncio
async def test_maestro_json_with_failure(tmp_path: Path):
    report = {
        "flows": [
            {"name": "login", "status": "passed", "duration": 2.0},
            {"name": "buy", "status": "failed", "duration": 3.5,
             "error": "Tap target not found within 10s"},
        ],
    }
    _write(tmp_path / "report.json", json.dumps(report))
    res = await _run(report_path=tmp_path / "report.json")
    assert isinstance(res, Ok)
    assert res.value.flows_failed == 1
    assert res.value.grade == "blocked"


@pytest.mark.asyncio
async def test_maestro_json_flat_list_format(tmp_path: Path):
    """Older Maestro versions emit a top-level list, not a dict."""
    report = [
        {"name": "a", "status": "passed", "duration": 1.0},
        {"name": "b", "status": "passed", "duration": 2.0},
    ]
    _write(tmp_path / "report.json", json.dumps(report))
    res = await _run(report_path=tmp_path / "report.json")
    assert isinstance(res, Ok)
    assert res.value.flows_total == 2


@pytest.mark.asyncio
async def test_maestro_json_duration_ms_fallback(tmp_path: Path):
    """Some Maestro outputs use durationMs (millis) instead of
    duration (seconds)."""
    report = {
        "flows": [
            {"name": "fast", "status": "passed", "durationMs": 1500},
        ],
    }
    _write(tmp_path / "report.json", json.dumps(report))
    res = await _run(report_path=tmp_path / "report.json")
    assert isinstance(res, Ok)
    # 1500ms = 1.5s
    assert res.value.flows[0].runtime_s == pytest.approx(1.5, abs=0.01)


# ---- Regression detection ----------------------------------------------


@pytest.mark.asyncio
async def test_regression_detected_when_prior_passed(tmp_path: Path):
    prior = (
        "<testsuite name='m' tests='2'>"
        "<testcase name='login' time='2.0'/>"
        "<testcase name='checkout' time='3.0'/>"
        "</testsuite>"
    )
    now = (
        "<testsuite name='m' tests='2'>"
        "<testcase name='login' time='2.0'/>"
        "<testcase name='checkout' time='3.5'>"
        "<failure message='ohno'>broken</failure>"
        "</testcase>"
        "</testsuite>"
    )
    _write(tmp_path / "prior.xml", prior)
    _write(tmp_path / "now.xml", now)
    res = await _run(
        report_path=tmp_path / "now.xml",
        prior_report_path=tmp_path / "prior.xml",
    )
    assert isinstance(res, Ok)
    assert "checkout" in res.value.regressions
    assert "regression" in res.value.advice.lower()


@pytest.mark.asyncio
async def test_first_time_failure_not_regression(tmp_path: Path):
    """If a flow wasn't in the prior report, failing now isn't
    a regression — it's a new failure."""
    prior = (
        "<testsuite name='m' tests='1'>"
        "<testcase name='login' time='2.0'/>"
        "</testsuite>"
    )
    now = (
        "<testsuite name='m' tests='1'>"
        "<testcase name='brand_new' time='3.0'>"
        "<failure message='x'>x</failure>"
        "</testcase>"
        "</testsuite>"
    )
    _write(tmp_path / "prior.xml", prior)
    _write(tmp_path / "now.xml", now)
    res = await _run(
        report_path=tmp_path / "now.xml",
        prior_report_path=tmp_path / "prior.xml",
    )
    assert isinstance(res, Ok)
    assert "brand_new" not in res.value.regressions


# ---- Aggregates --------------------------------------------------------


@pytest.mark.asyncio
async def test_top_failures_capped_at_5(tmp_path: Path):
    cases = []
    for i in range(10):
        cases.append(
            f"<testcase name='fail_{i}' time='{i + 1}.0'>"
            f"<failure message='error {i}'>e</failure>"
            f"</testcase>"
        )
    _write(
        tmp_path / "report.xml",
        f"<testsuite name='m' tests='10'>{''.join(cases)}</testsuite>",
    )
    res = await _run(report_path=tmp_path / "report.xml")
    assert isinstance(res, Ok)
    assert len(res.value.top_failures) == 5


@pytest.mark.asyncio
async def test_slowest_flow_identified(tmp_path: Path):
    _write(
        tmp_path / "report.xml",
        "<testsuite name='m' tests='3'>"
        "<testcase name='fast' time='1.0'/>"
        "<testcase name='medium' time='5.0'/>"
        "<testcase name='slowest_one' time='15.0'/>"
        "</testsuite>",
    )
    res = await _run(report_path=tmp_path / "report.xml")
    assert isinstance(res, Ok)
    assert res.value.slowest_flow == "slowest_one"
    assert res.value.slowest_runtime_s == 15.0


@pytest.mark.asyncio
async def test_advice_mentions_grade_and_counts(tmp_path: Path):
    _write(
        tmp_path / "report.xml",
        "<testsuite name='m' tests='2'>"
        "<testcase name='a' time='1.0'/>"
        "<testcase name='b' time='2.0'/>"
        "</testsuite>",
    )
    res = await _run(report_path=tmp_path / "report.xml")
    assert isinstance(res, Ok)
    assert "clean" in res.value.advice
    assert "2/2 passed" in res.value.advice
