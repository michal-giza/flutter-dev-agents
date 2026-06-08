"""Tests for the SetupWebDriverAgent use case (precheck behaviour)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.wda_setup import (
    SetupWebDriverAgent,
    SetupWebDriverAgentParams,
)
from tests.fakes.fake_dev_session import FakeWdaSetupCli


@pytest.mark.asyncio
async def test_wda_setup_writes_marker_on_success(tmp_path: Path):
    cli = FakeWdaSetupCli()
    uc = SetupWebDriverAgent(cli)
    res = await uc(
        SetupWebDriverAgentParams(udid="udid-A", wda_dir=tmp_path)
    )
    assert isinstance(res, Ok)
    marker = tmp_path / ".mcp-phone-controll-built"
    assert marker.exists()
    assert "udid-A" in marker.read_text()


@pytest.mark.asyncio
async def test_wda_setup_skips_if_marker_present(tmp_path: Path):
    cli = FakeWdaSetupCli()
    # Pre-create marker
    (tmp_path / ".mcp-phone-controll-built").write_text("udid-A\n")
    uc = SetupWebDriverAgent(cli)
    res = await uc(
        SetupWebDriverAgentParams(udid="udid-A", wda_dir=tmp_path)
    )
    assert isinstance(res, Ok)
    assert res.value.skipped_existing is True


@pytest.mark.asyncio
async def test_wda_setup_force_rebuilds_when_skip_false(tmp_path: Path):
    cli = FakeWdaSetupCli()
    (tmp_path / ".mcp-phone-controll-built").write_text("udid-A\n")
    uc = SetupWebDriverAgent(cli)
    res = await uc(
        SetupWebDriverAgentParams(
            udid="udid-A", wda_dir=tmp_path, skip_if_built=False
        )
    )
    assert isinstance(res, Ok)
    assert res.value.skipped_existing is False


@pytest.mark.asyncio
async def test_wda_setup_per_udid_marker(tmp_path: Path):
    """Marker tracks UDIDs separately — different device must rebuild."""
    cli = FakeWdaSetupCli()
    (tmp_path / ".mcp-phone-controll-built").write_text("udid-A\n")
    uc = SetupWebDriverAgent(cli)
    res = await uc(SetupWebDriverAgentParams(udid="udid-B", wda_dir=tmp_path))
    assert isinstance(res, Ok)
    assert res.value.skipped_existing is False
    # Now both udids are in the marker
    contents = (tmp_path / ".mcp-phone-controll-built").read_text()
    assert "udid-A" in contents and "udid-B" in contents


@pytest.mark.asyncio
async def test_wda_setup_rejects_missing_udid(tmp_path: Path):
    uc = SetupWebDriverAgent(FakeWdaSetupCli())
    res = await uc(SetupWebDriverAgentParams(udid="", wda_dir=tmp_path))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ---- team_id / DEVELOPMENT_TEAM threading -----------------------------


@pytest.mark.asyncio
async def test_wda_setup_passes_team_id_to_xcodebuild(tmp_path: Path):
    """Physical-device builds need DEVELOPMENT_TEAM. Plumb team_id from
    params through to the CLI call so xcodebuild sees it."""
    cli = FakeWdaSetupCli()
    uc = SetupWebDriverAgent(cli)
    res = await uc(
        SetupWebDriverAgentParams(
            udid="udid-physical",
            wda_dir=tmp_path,
            team_id="ABCDE12345",
        )
    )
    assert isinstance(res, Ok)
    assert cli.last_build_call is not None
    assert cli.last_build_call["team_id"] == "ABCDE12345"


@pytest.mark.asyncio
async def test_wda_setup_team_id_falls_back_to_env(
    tmp_path: Path, monkeypatch
):
    """Operators prefer setting MCP_WDA_TEAM_ID once over passing it on
    every call. Env var must fill in when param is None."""
    monkeypatch.setenv("MCP_WDA_TEAM_ID", "ZZZZZ99999")
    cli = FakeWdaSetupCli()
    uc = SetupWebDriverAgent(cli)
    res = await uc(SetupWebDriverAgentParams(udid="udid-physical", wda_dir=tmp_path))
    assert isinstance(res, Ok)
    assert cli.last_build_call["team_id"] == "ZZZZZ99999"


@pytest.mark.asyncio
async def test_wda_setup_explicit_param_overrides_env(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("MCP_WDA_TEAM_ID", "FROM_ENV_X9")
    cli = FakeWdaSetupCli()
    uc = SetupWebDriverAgent(cli)
    res = await uc(
        SetupWebDriverAgentParams(
            udid="udid-physical",
            wda_dir=tmp_path,
            team_id="EXPLICIT_AB",
        )
    )
    assert isinstance(res, Ok)
    assert cli.last_build_call["team_id"] == "EXPLICIT_AB"


@pytest.mark.asyncio
async def test_wda_setup_signing_failure_surfaces_actionable_envelope(
    tmp_path: Path, monkeypatch
):
    """The whole point of plumbing team_id: when xcodebuild fails with
    the signing error, the envelope must tell the agent exactly what
    to do — not bury it as a generic 'check_xcode_signing'."""
    monkeypatch.delenv("MCP_WDA_TEAM_ID", raising=False)
    cli = FakeWdaSetupCli(fail_with_signing_error=True)
    uc = SetupWebDriverAgent(cli)
    res = await uc(
        SetupWebDriverAgentParams(udid="udid-physical", wda_dir=tmp_path)
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "provide_team_id"
    assert "team_id" in res.failure.message.lower()
    assert "MCP_WDA_TEAM_ID" in res.failure.message
    assert res.failure.details["team_id_passed"] is False


# ---- simulator builds (the iOS-simulator signing bug) -----------------


@pytest.mark.asyncio
async def test_wda_setup_simulator_builds_without_signing(tmp_path, monkeypatch):
    """REGRESSION (field report): building WDA for a SIMULATOR used the
    device destination (platform=iOS) and demanded code signing. With
    is_simulator=True it must build for the simulator destination with NO
    team — even if MCP_WDA_TEAM_ID is set."""
    monkeypatch.setenv("MCP_WDA_TEAM_ID", "SHOULDNOTUSE")
    cli = FakeWdaSetupCli()
    uc = SetupWebDriverAgent(cli)
    res = await uc(
        SetupWebDriverAgentParams(
            udid="SIM-UDID-123", wda_dir=tmp_path, is_simulator=True
        )
    )
    assert isinstance(res, Ok)
    assert cli.last_build_call["is_simulator"] is True
    assert cli.last_build_call["team_id"] is None  # never sign a simulator


@pytest.mark.asyncio
async def test_wda_setup_auto_detects_simulator(tmp_path):
    """is_simulator omitted → auto-detect via the CLI. A udid known to
    simctl is treated as a simulator (no signing)."""
    cli = FakeWdaSetupCli()
    cli.simulator_udids = {"SIM-AUTO-9"}
    uc = SetupWebDriverAgent(cli)
    res = await uc(SetupWebDriverAgentParams(udid="SIM-AUTO-9", wda_dir=tmp_path))
    assert isinstance(res, Ok)
    assert cli.last_build_call["is_simulator"] is True
    assert cli.last_build_call["team_id"] is None


@pytest.mark.asyncio
async def test_wda_setup_auto_detects_physical_device(tmp_path, monkeypatch):
    """A udid NOT in simctl → physical device → device build + team."""
    monkeypatch.setenv("MCP_WDA_TEAM_ID", "TEAM123456")
    cli = FakeWdaSetupCli()
    cli.simulator_udids = set()  # nothing is a simulator
    uc = SetupWebDriverAgent(cli)
    res = await uc(SetupWebDriverAgentParams(udid="00008030-PHYS", wda_dir=tmp_path))
    assert isinstance(res, Ok)
    assert cli.last_build_call["is_simulator"] is False
    assert cli.last_build_call["team_id"] == "TEAM123456"
