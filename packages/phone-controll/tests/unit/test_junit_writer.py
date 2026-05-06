"""Tests for the JUnit XML emitter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from mcp_phone_controll.domain.entities import PhaseOutcome, PlanRun
from mcp_phone_controll.infrastructure.junit_writer import write_junit


def _run_with(*phases: PhaseOutcome) -> PlanRun:
    now = datetime.now()
    return PlanRun(
        plan_name="t",
        started_at=now,
        finished_at=now,
        overall_ok=all(p.ok for p in phases),
        phases=phases,
        duration_ms=42,
    )


def test_writes_passing_run(tmp_path: Path):
    run = _run_with(
        PhaseOutcome(phase="PRE_FLIGHT", ok=True, planned_outcome=None,
                     actual_outcome="ready", duration_ms=5),
        PhaseOutcome(phase="LAUNCHED", ok=True, planned_outcome=None,
                     actual_outcome="launched", duration_ms=120),
    )
    out = write_junit(run, tmp_path / "r.xml")
    tree = ET.parse(out)
    suite = tree.getroot()
    assert suite.tag == "testsuite"
    assert suite.get("tests") == "2"
    assert suite.get("failures") == "0"
    assert suite.get("errors") == "0"
    cases = suite.findall("testcase")
    assert [c.get("name") for c in cases] == ["PRE_FLIGHT", "LAUNCHED"]
    assert cases[0].get("time") == "0.005"
    assert cases[1].get("time") == "0.120"


def test_distinguishes_failure_from_error(tmp_path: Path):
    run = _run_with(
        PhaseOutcome(phase="UNDER_TEST", ok=False, planned_outcome=None,
                     actual_outcome="failed", error_code="TestExecutionFailure",
                     error_message="3 failed", duration_ms=200),
        PhaseOutcome(phase="LAUNCHED", ok=False, planned_outcome=None,
                     actual_outcome="failed", error_code="DeviceBusyFailure",
                     error_message="held", duration_ms=10),
    )
    out = write_junit(run, tmp_path / "r.xml")
    suite = ET.parse(out).getroot()
    assert suite.get("failures") == "1"
    assert suite.get("errors") == "1"
    cases = suite.findall("testcase")
    failure = cases[0].find("failure")
    error = cases[1].find("error")
    assert failure is not None and failure.get("type") == "TestExecutionFailure"
    assert error is not None and error.get("type") == "DeviceBusyFailure"


def test_skipped_phases_emit_skipped_element(tmp_path: Path):
    run = _run_with(
        PhaseOutcome(phase="PRE_FLIGHT", ok=True, planned_outcome=None,
                     actual_outcome="ready", duration_ms=5),
        PhaseOutcome(phase="UNDER_TEST", ok=False, planned_outcome=None,
                     actual_outcome="skipped_after_terminal",
                     notes="prior phase reached terminal"),
    )
    out = write_junit(run, tmp_path / "r.xml")
    suite = ET.parse(out).getroot()
    assert suite.get("skipped") == "1"
    skipped = suite.findall("testcase")[1].find("skipped")
    assert skipped is not None


def test_verdict_blocked_phases_excluded(tmp_path: Path):
    run = _run_with(
        PhaseOutcome(phase="PRE_FLIGHT", ok=True, planned_outcome=None,
                     actual_outcome="ready"),
        PhaseOutcome(phase="VERDICT_BLOCKED", ok=False, planned_outcome=None,
                     actual_outcome="blocked", error_code="LaunchFailure"),
    )
    out = write_junit(run, tmp_path / "r.xml")
    suite = ET.parse(out).getroot()
    # Only PRE_FLIGHT counts; VERDICT_BLOCKED is propagation noise.
    assert suite.get("tests") == "1"
    names = [c.get("name") for c in suite.findall("testcase")]
    assert "VERDICT_BLOCKED" not in names
