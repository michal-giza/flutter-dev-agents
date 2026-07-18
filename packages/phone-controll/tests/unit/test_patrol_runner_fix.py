"""Patrol runner: the P0 --reporter=json fix + web support (v0.17.0).

The bug this pins: PatrolTestRepository hard-coded
`extra_flags=["--reporter=json"]`, but `patrol test` has never had a
--reporter flag — verified against the real CLI:

    $ patrol test --reporter=json
    Could not find an option named "--reporter".   (exit 1)

so EVERY run_patrol_test / run_patrol_suite failed, masked by a generic
"run patrol doctor" hint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.patrol_repository import (
    PatrolTestRepository,
)
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.infrastructure.patrol_cli import PatrolCli


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    @property
    def ok(self):
        return self.returncode == 0


class _FakeRunner:
    """Records argv; returns scripted results keyed by the subcommand."""

    def __init__(self, test_result=None, version_out="patrol_cli v4.5.1"):
        self.calls: list[list[str]] = []
        self._test_result = test_result or _FakeResult(0, "✓ signs in (1.2s)\n")
        self._version_out = version_out

    async def run(self, argv, cwd=None, timeout_s=None):
        self.calls.append(list(argv))
        if "--version" in argv:
            return _FakeResult(0, self._version_out)
        return self._test_result

    @property
    def last_test_argv(self):
        return next(a for a in reversed(self.calls) if "test" in a)


def _repo(runner):
    return PatrolTestRepository(PatrolCli(runner, binary="patrol"))


# ---- P0: the fatal flag is gone -----------------------------------------


@pytest.mark.asyncio
async def test_never_passes_reporter_json(tmp_path):
    """The regression guard: --reporter=json must never be emitted."""
    runner = _FakeRunner()
    res = await _repo(runner).run_test(tmp_path, Path("integration_test/a_test.dart"), "EMU01")
    assert isinstance(res, Ok), res
    argv = runner.last_test_argv
    assert not any("--reporter" in a for a in argv), argv


@pytest.mark.asyncio
async def test_parses_passing_run_from_patrol_output(tmp_path):
    runner = _FakeRunner(_FakeResult(0, "✓ signs in (1.2s)\n✓ loads feed (0.4s)\n"))
    res = await _repo(runner).run_test(tmp_path, Path("t_test.dart"), "EMU01")
    assert isinstance(res, Ok)
    assert res.value.passed == 2
    assert res.value.failed == 0


@pytest.mark.asyncio
async def test_failure_surfaces_real_cli_error_not_doctor_hint(tmp_path):
    """An unknown-option error is OUR bug — say so, don't blame the toolchain."""
    runner = _FakeRunner(
        _FakeResult(1, "", 'Could not find an option named "--reporter".')
    )
    res = await _repo(runner).run_test(tmp_path, Path("t_test.dart"), "EMU01")
    assert isinstance(res, Err)
    assert "tool bug" in res.failure.message.lower()
    assert res.failure.details["exit_code"] == 1


@pytest.mark.asyncio
async def test_failed_tests_are_named_in_the_failure(tmp_path):
    runner = _FakeRunner(_FakeResult(1, "✓ a\n✗ checkout flow\n"))
    res = await _repo(runner).run_test(tmp_path, Path("t_test.dart"), "EMU01")
    assert isinstance(res, Err)
    assert "checkout flow" in res.failure.details["failed_tests"]


# ---- discovery: Patrol 4 moved to patrol_test/ ---------------------------


@pytest.mark.asyncio
async def test_list_tests_finds_patrol_test_dir(tmp_path):
    (tmp_path / "patrol_test").mkdir()
    (tmp_path / "patrol_test" / "login_test.dart").write_text("//", encoding="utf-8")
    (tmp_path / "integration_test").mkdir()
    (tmp_path / "integration_test" / "app_test.dart").write_text("//", encoding="utf-8")
    res = await _repo(_FakeRunner()).list_tests(tmp_path)
    assert isinstance(res, Ok)
    assert {f.name for f in res.value} == {"login_test", "app_test"}


# ---- web -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_run_builds_documented_argv(tmp_path):
    runner = _FakeRunner(version_out="patrol_cli v4.5.1")
    res = await _repo(runner).run_test(
        tmp_path, Path("patrol_test/login_test.dart"), "", flavor="prod", web=True
    )
    assert isinstance(res, Ok), res
    argv = runner.last_test_argv
    assert argv[:2] == ["patrol", "test"]
    assert "--device" in argv and argv[argv.index("--device") + 1] == "chrome"
    # headless takes a LITERAL true, not a bare flag
    assert argv[argv.index("--web-headless") + 1] == "true"
    # patrol_cli rejects --flavor on web — we must suppress it
    assert "--flavor" not in argv


@pytest.mark.asyncio
async def test_web_gated_on_old_cli_with_actionable_error(tmp_path):
    """The user's machine has 3.11.0 — must fail closed with an upgrade path."""
    runner = _FakeRunner(version_out="Update available! 3.11.0 → 4.5.1\npatrol_cli v3.11.0")
    res = await _repo(runner).run_test(tmp_path, Path("t_test.dart"), "", web=True)
    assert isinstance(res, Err)
    assert res.failure.next_action == "upgrade_patrol_cli"
    assert "4.0.0" in res.failure.message
    assert res.failure.details["found_version"] == "3.11.0"
    # never attempted the run
    assert not any("--web-headless" in a for a in runner.calls)


@pytest.mark.asyncio
async def test_version_parse_ignores_update_banner(tmp_path):
    """The banner contains BOTH 3.11.0 and 4.5.1 — must read the installed one."""
    runner = _FakeRunner(version_out="Update available! 3.11.0 → 4.5.1\npatrol_cli v3.11.0\n")
    assert await PatrolCli(runner, binary="patrol").version() == (3, 11, 0)


@pytest.mark.asyncio
async def test_unparsable_version_fails_web_closed(tmp_path):
    runner = _FakeRunner(version_out="garbage")
    res = await _repo(runner).run_test(tmp_path, Path("t_test.dart"), "", web=True)
    assert isinstance(res, Err)
    assert res.failure.details["found_version"] == "unknown"
