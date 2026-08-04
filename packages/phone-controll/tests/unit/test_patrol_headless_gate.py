"""`--web-headless` shape is gated on the INSTALLED patrol_cli version.

patrol_cli 4.6.0 changed it from a value option
(`--web-headless=<true|false>`) to a negatable boolean (`--[no-]web-headless`).
Observed live against 4.6.1:

    [WARN] Passing a value to --web-headless is deprecated.
           Use --web-headless or --no-web-headless instead.

The value form still parses on 4.6.x, but the BARE flag is a hard parse
error on 4.5.x — so we must emit per-version, and fall back to the legacy
form whenever we can't read a version.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.patrol_repository import (
    PatrolTestRepository,
)
from mcp_phone_controll.infrastructure.patrol_cli import PatrolCli
from tests.unit.test_patrol_runner_fix import _FakeRunner


def _repo(runner):
    return PatrolTestRepository(PatrolCli(runner, binary="patrol"))


async def _web_argv(version_out: str) -> list[str]:
    runner = _FakeRunner(version_out=version_out)
    await _repo(runner).run_test(Path("/proj"), Path("t_test.dart"), "", web=True)
    return runner.last_test_argv


@pytest.mark.asyncio
async def test_461_emits_bare_boolean_flag():
    argv = await _web_argv("patrol_cli v4.6.1")
    assert "--web-headless" in argv
    # the deprecated value must NOT follow the flag
    assert argv[argv.index("--web-headless") + 1] != "true"


@pytest.mark.asyncio
async def test_460_is_the_boundary():
    argv = await _web_argv("patrol_cli v4.6.0")
    assert argv[argv.index("--web-headless") + 1] != "true"


@pytest.mark.asyncio
async def test_451_keeps_the_legacy_value_form():
    """Must not regress users still on 4.5.x — the bare flag is a hard
    parse error there."""
    argv = await _web_argv("patrol_cli v4.5.1")
    assert argv[argv.index("--web-headless") + 1] == "true"


@pytest.mark.asyncio
async def test_unparsable_version_never_reaches_argv_on_the_web_path():
    """An unreadable version fails the web gate CLOSED before we build any
    argv — so the headless form is moot there. Pinned so the gate and the
    flag-shape logic can't drift apart."""
    runner = _FakeRunner(version_out="something unparseable")
    res = await _repo(runner).run_test(
        Path("/proj"), Path("t_test.dart"), "", web=True
    )
    assert not res.is_ok
    assert res.failure.next_action == "upgrade_patrol_cli"


@pytest.mark.asyncio
async def test_unparsable_version_falls_back_to_legacy_form():
    """Directly: unknown version → the form that parses on BOTH lines (only
    a deprecation warning on 4.6.x), never the bare flag that hard-fails on
    4.5.x. Guards any future caller that isn't behind the web gate."""
    cli = PatrolCli(_FakeRunner(version_out="nope"), binary="patrol")
    assert await cli._headless_argv(True) == ["--web-headless", "true"]


@pytest.mark.asyncio
async def test_headless_false_uses_the_negated_flag_on_46():
    runner = _FakeRunner(version_out="patrol_cli v4.6.1")
    cli = PatrolCli(runner, binary="patrol")
    argv = await cli._headless_argv(False)
    assert argv == ["--no-web-headless"]


@pytest.mark.asyncio
async def test_headless_false_uses_the_value_form_on_45():
    runner = _FakeRunner(version_out="patrol_cli v4.5.1")
    cli = PatrolCli(runner, binary="patrol")
    argv = await cli._headless_argv(False)
    assert argv == ["--web-headless", "false"]
