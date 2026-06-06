"""Web-platform support for the test runners (v0.5.2).

FIELD REPORT (2026-06-06): `run_unit_tests` ran `flutter test` on the
default VM platform, so a Flutter **web** app whose code imports
`dart:html` (transitively, via almost the whole package) errored with:

    Error: Dart library 'dart:html' is not available on this platform.

The repo's own `make runtests` uses `flutter test --platform chrome`,
where the same suite is 22/22 green. These tests pin the fix:

  - FlutterCli.test_unit / test_widget add `--platform <X>` when asked.
  - The repository / use case run on the VM in "auto" mode, then
    transparently retry on `--platform chrome` when the run hits the
    web-only-library marker.
  - "vm" / "chrome" force the platform with no retry.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.data.parsers.flutter_test_reporter_parser import (
    looks_like_web_platform_error,
)
from mcp_phone_controll.data.repositories.flutter_test_repository import (
    FlutterTestRepository,
)
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.widget_testing import (
    RunWidgetTest,
    RunWidgetTestParams,
)
from mcp_phone_controll.infrastructure.flutter_cli import FlutterCli
from mcp_phone_controll.infrastructure.process_runner import ProcessResult

_WEB_ERROR = (
    "Error: Dart library 'dart:html' is not available on this platform.\n"
    "  import 'dart:html';\n"
)


def _passing_reporter(passed: int = 3) -> str:
    lines = [json.dumps({"type": "suite", "suite": {"id": 0, "path": "test/x.dart"}})]
    for i in range(passed):
        lines.append(json.dumps(
            {"type": "testStart", "test": {"id": i, "name": f"t{i}", "suiteID": 0}}
        ))
        lines.append(json.dumps({"type": "testDone", "testID": i, "result": "success"}))
    lines.append(json.dumps({"type": "done", "success": True}))
    return "\n".join(lines)


class _ScriptedRunner:
    """Records each argv and returns scripted ProcessResults in order
    (last one repeats if the script runs out)."""

    def __init__(self, results: list[ProcessResult]) -> None:
        self._results = results
        self.argvs: list[list[str]] = []

    async def run(self, argv, cwd=None, timeout_s=None):
        self.argvs.append(list(argv))
        idx = min(len(self.argvs) - 1, len(self._results) - 1)
        return self._results[idx]


# ---- the marker detector ------------------------------------------------


def test_marker_detects_web_platform_error():
    assert looks_like_web_platform_error(_WEB_ERROR, "")
    assert looks_like_web_platform_error("", _WEB_ERROR)


def test_marker_ignores_ordinary_output():
    assert not looks_like_web_platform_error(_passing_reporter(), "")
    assert not looks_like_web_platform_error(None, None)


# ---- FlutterCli argv ----------------------------------------------------


@pytest.mark.asyncio
async def test_cli_test_unit_adds_platform_flag(tmp_path: Path):
    runner = _ScriptedRunner([ProcessResult(returncode=0, stdout="", stderr="")])
    cli = FlutterCli(runner, flutter_path="flutter")

    await cli.test_unit(tmp_path, platform="chrome")
    assert "--platform" in runner.argvs[0]
    assert runner.argvs[0][runner.argvs[0].index("--platform") + 1] == "chrome"


@pytest.mark.asyncio
async def test_cli_test_unit_omits_flag_when_none(tmp_path: Path):
    runner = _ScriptedRunner([ProcessResult(returncode=0, stdout="", stderr="")])
    cli = FlutterCli(runner, flutter_path="flutter")

    await cli.test_unit(tmp_path, platform=None)
    assert "--platform" not in runner.argvs[0]


@pytest.mark.asyncio
async def test_cli_test_widget_adds_platform_flag(tmp_path: Path):
    runner = _ScriptedRunner([ProcessResult(returncode=0, stdout="", stderr="")])
    cli = FlutterCli(runner, flutter_path="flutter")

    await cli.test_widget(tmp_path, platform="chrome")
    assert "--platform" in runner.argvs[0]
    assert runner.argvs[0][runner.argvs[0].index("--platform") + 1] == "chrome"


# ---- FlutterTestRepository: auto / vm / chrome --------------------------


@pytest.mark.asyncio
async def test_repo_auto_retries_on_chrome_after_web_error(tmp_path: Path):
    """The headline fix: a web app fails on the VM, then auto-retries on
    Chrome and succeeds — without the caller specifying a platform."""
    runner = _ScriptedRunner([
        ProcessResult(returncode=1, stdout="", stderr=_WEB_ERROR),       # VM fails
        ProcessResult(returncode=0, stdout=_passing_reporter(3), stderr=""),  # chrome ok
    ])
    repo = FlutterTestRepository(FlutterCli(runner, flutter_path="flutter"))

    res = await repo.run_unit_tests(tmp_path, platform="auto")

    assert isinstance(res, Ok)
    assert res.value.passed == 3
    assert len(runner.argvs) == 2  # VM, then retry
    assert "--platform" not in runner.argvs[0]            # first = VM
    assert "chrome" in runner.argvs[1]                    # retry = chrome


@pytest.mark.asyncio
async def test_repo_auto_does_not_retry_when_vm_ok(tmp_path: Path):
    runner = _ScriptedRunner([
        ProcessResult(returncode=0, stdout=_passing_reporter(2), stderr=""),
    ])
    repo = FlutterTestRepository(FlutterCli(runner, flutter_path="flutter"))

    res = await repo.run_unit_tests(tmp_path, platform="auto")

    assert isinstance(res, Ok)
    assert len(runner.argvs) == 1  # no retry
    assert "--platform" not in runner.argvs[0]


@pytest.mark.asyncio
async def test_repo_chrome_forces_platform_no_vm_attempt(tmp_path: Path):
    runner = _ScriptedRunner([
        ProcessResult(returncode=0, stdout=_passing_reporter(2), stderr=""),
    ])
    repo = FlutterTestRepository(FlutterCli(runner, flutter_path="flutter"))

    res = await repo.run_unit_tests(tmp_path, platform="chrome")

    assert isinstance(res, Ok)
    assert len(runner.argvs) == 1
    assert "chrome" in runner.argvs[0]  # straight to chrome, no VM probe


@pytest.mark.asyncio
async def test_repo_vm_does_not_retry_even_on_web_error(tmp_path: Path):
    """Explicit vm = no auto-retry; the error surfaces with a fix hint."""
    runner = _ScriptedRunner([
        ProcessResult(returncode=1, stdout="", stderr=_WEB_ERROR),
    ])
    repo = FlutterTestRepository(FlutterCli(runner, flutter_path="flutter"))

    res = await repo.run_unit_tests(tmp_path, platform="vm")

    assert isinstance(res, Err)
    assert len(runner.argvs) == 1  # no retry
    assert "platform='chrome'" in res.failure.details.get("hint", "")


# ---- RunWidgetTest auto-retry ------------------------------------------


@pytest.mark.asyncio
async def test_widget_test_auto_retries_on_chrome(tmp_path: Path):
    runner = _ScriptedRunner([
        ProcessResult(returncode=1, stdout="", stderr=_WEB_ERROR),
        ProcessResult(returncode=0, stdout=_passing_reporter(4), stderr=""),
    ])
    cli = FlutterCli(runner, flutter_path="flutter")

    res = await RunWidgetTest(cli)(RunWidgetTestParams(project_path=tmp_path))

    assert isinstance(res, Ok)
    assert res.value.passed == 4
    assert len(runner.argvs) == 2
    assert "chrome" in runner.argvs[1]
