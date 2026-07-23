"""junit_path on run_patrol_test/suite — end-to-end through the real _run.

Proves the runner writes a JUnit report at the requested path for BOTH a
passing native run (per-case) and a failing run whose output can't be
itemised (the empty-parse safety net keeps CI red).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.patrol_repository import (
    PatrolTestRepository,
)
from mcp_phone_controll.infrastructure.patrol_cli import PatrolCli
from tests.unit.test_patrol_runner_fix import _FakeResult, _FakeRunner


def _repo(runner):
    return PatrolTestRepository(PatrolCli(runner, binary="patrol"))


@pytest.mark.asyncio
async def test_junit_written_for_passing_native_run(tmp_path):
    out = tmp_path / "reports" / "patrol.xml"
    runner = _FakeRunner()  # default stdout: "✓ signs in (1.2s)"
    res = await _repo(runner).run_test(
        tmp_path, Path("integration_test/a_test.dart"), "EMU01", junit_path=out
    )
    assert res.is_ok
    assert out.exists()
    root = ET.parse(out).getroot()
    assert root.get("tests") == "1"
    assert root.get("failures") == "0"
    assert root.find("testcase").get("name") == "signs in"


@pytest.mark.asyncio
async def test_junit_stays_red_when_failing_run_has_no_itemisable_output(tmp_path):
    """A non-zero exit with output the scraper can't parse must still emit
    a RED report — an empty (green) suite would hide a real CI failure."""
    out = tmp_path / "patrol.xml"
    runner = _FakeRunner(
        test_result=_FakeResult(1, "Gradle build failed; no test lines here")
    )
    res = await _repo(runner).run_test(
        tmp_path, Path("integration_test/a_test.dart"), "EMU01", junit_path=out
    )
    assert not res.is_ok
    assert out.exists()
    root = ET.parse(out).getroot()
    assert root.get("tests") == "1"
    assert root.get("failures") == "1"
    # the failure path also surfaces the report location to the agent
    assert res.failure.details.get("junit_report") == str(out)


@pytest.mark.asyncio
async def test_junit_stays_red_on_partial_scrape(tmp_path):
    """The realistic mobile failure mode: the scraper itemises the passing
    test but misses the failing one, while patrol still exits non-zero. The
    JUnit must be RED, not a green suite with one passing case."""
    out = tmp_path / "patrol.xml"
    runner = _FakeRunner(
        test_result=_FakeResult(
            1, "✓ test_a (1.2s)\nsomething exploded\nSome tests failed."
        )
    )
    res = await _repo(runner).run_test(
        tmp_path, Path("integration_test/a_test.dart"), "EMU01", junit_path=out
    )
    assert not res.is_ok
    root = ET.parse(out).getroot()
    # one scraped pass + one synthetic failure -> still red
    assert int(root.get("failures")) >= 1
    assert root.get("failures") != "0"


@pytest.mark.asyncio
async def test_no_junit_when_path_omitted(tmp_path):
    runner = _FakeRunner()
    await _repo(runner).run_test(
        tmp_path, Path("integration_test/a_test.dart"), "EMU01"
    )
    # No stray reports dir created.
    assert not (tmp_path / "reports").exists()
