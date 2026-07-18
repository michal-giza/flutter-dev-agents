"""Patrol 4 professional: web JSON results, CI mode, mobile knobs (v0.18.0).

Flag encodings here are taken from the REAL `patrol test --help` of
patrol_cli 4.5.1 (installed locally), not from docs:
  --web-reporter=<'["html", "json", "list"]'>   -> JSON array STRING
  --web-headless=<true | false>                 -> literal true/false
  --web-browser-args=<'["--no-sandbox", ...]'>  -> JSON array STRING
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.data.parsers.playwright_report_parser import (
    find_report,
    parse_playwright_report,
)
from mcp_phone_controll.data.repositories.patrol_repository import (
    PatrolTestRepository,
)
from mcp_phone_controll.infrastructure.patrol_cli import PatrolCli
from tests.unit.test_patrol_runner_fix import _FakeRunner


def _repo(runner):
    return PatrolTestRepository(PatrolCli(runner, binary="patrol"))


# ---- web: machine-readable results --------------------------------------


@pytest.mark.asyncio
async def test_web_requests_json_reporter_as_json_array(tmp_path):
    runner = _FakeRunner()
    await _repo(runner).run_test(tmp_path, Path("t_test.dart"), "", web=True)
    argv = runner.last_test_argv
    assert argv[argv.index("--web-reporter") + 1] == '["json"]'
    assert "--web-results-dir" in argv


# ---- CI mode (gap #5) ----------------------------------------------------


@pytest.mark.asyncio
async def test_ci_mode_web_is_unattended_and_deterministic(tmp_path):
    runner = _FakeRunner()
    await _repo(runner).run_test(tmp_path, Path("t_test.dart"), "", web=True, ci=True)
    argv = runner.last_test_argv
    assert argv[argv.index("--web-headless") + 1] == "true"
    assert "--web-retries" in argv
    assert "--web-global-timeout" in argv
    # --no-sandbox is required in most CI containers (root, no userns)
    assert "--no-sandbox" in argv[argv.index("--web-browser-args") + 1]
    assert argv[argv.index("--web-video") + 1] == "retain-on-failure"


@pytest.mark.asyncio
async def test_ci_mode_native_is_hermetic(tmp_path):
    """Patrol 4 native knobs: clean install + clean permissions per test."""
    runner = _FakeRunner()
    await _repo(runner).run_test(tmp_path, Path("t_test.dart"), "EMU01", ci=True)
    argv = runner.last_test_argv
    assert "--full-isolation" in argv
    assert "--clear-permissions" in argv
    # web-only flags must never leak onto the native path
    assert not any(a.startswith("--web-") for a in argv)


@pytest.mark.asyncio
async def test_non_ci_native_stays_lean(tmp_path):
    runner = _FakeRunner()
    await _repo(runner).run_test(tmp_path, Path("t_test.dart"), "EMU01")
    argv = runner.last_test_argv
    assert "--full-isolation" not in argv
    assert "--clear-permissions" not in argv


@pytest.mark.asyncio
async def test_tags_filter_passed_through(tmp_path):
    runner = _FakeRunner()
    await _repo(runner).run_test(
        tmp_path, Path("t_test.dart"), "EMU01", tags="smoke", exclude_tags="slow"
    )
    argv = runner.last_test_argv
    assert argv[argv.index("--tags") + 1] == "smoke"
    assert argv[argv.index("--exclude-tags") + 1] == "slow"


# ---- Playwright JSON report ---------------------------------------------


def test_playwright_report_gives_exact_counts(tmp_path):
    report = {
        "suites": [{
            "specs": [
                {"title": "logs in",
                 "tests": [{"results": [{"status": "passed", "duration": 1200}]}]},
                {"title": "checkout",
                 "tests": [{"results": [{"status": "failed", "duration": 800}]}]},
            ],
            "suites": [{
                "specs": [
                    {"title": "nested",
                     "tests": [{"results": [{"status": "skipped", "duration": 0}]}]}
                ]
            }],
        }]
    }
    (tmp_path / "results.json").write_text(json.dumps(report), encoding="utf-8")
    run = parse_playwright_report(find_report(tmp_path))
    assert (run.total, run.passed, run.failed, run.skipped) == (3, 1, 1, 1)
    assert run.duration_ms == 2000


def test_playwright_retry_uses_last_result(tmp_path):
    """Playwright records one result per retry — the LAST is authoritative."""
    report = {"suites": [{"specs": [{
        "title": "flaky",
        "tests": [{"results": [
            {"status": "failed", "duration": 10},
            {"status": "passed", "duration": 20},
        ]}],
    }]}]}
    (tmp_path / "results.json").write_text(json.dumps(report), encoding="utf-8")
    run = parse_playwright_report(find_report(tmp_path))
    assert run.passed == 1 and run.failed == 0


def test_playwright_report_falls_back_to_stats(tmp_path):
    (tmp_path / "results.json").write_text(
        json.dumps({"suites": [], "stats": {"expected": 4, "unexpected": 1, "flaky": 1}}),
        encoding="utf-8",
    )
    run = parse_playwright_report(find_report(tmp_path))
    assert run.total == 6 and run.passed == 5 and run.failed == 1


def test_no_report_returns_none(tmp_path):
    assert find_report(tmp_path) is None
