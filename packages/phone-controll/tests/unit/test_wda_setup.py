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
