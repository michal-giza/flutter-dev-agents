"""Tests for write_vscode_launch_config — idempotent + flavor-aware."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.usecases.ide import (
    WriteVscodeLaunchConfig,
    WriteVscodeLaunchConfigParams,
    render_vscode_launch_config,
)


def test_render_includes_three_modes():
    cfg = render_vscode_launch_config(flavor=None, target="lib/main.dart", debug_mode="debug")
    modes = {c["flutterMode"] for c in cfg["configurations"]}
    assert modes == {"debug", "profile", "release"}
    assert all(c["program"] == "lib/main.dart" for c in cfg["configurations"])


def test_render_propagates_flavor_args():
    cfg = render_vscode_launch_config(flavor="prod", target="lib/main.dart", debug_mode="debug")
    for c in cfg["configurations"]:
        assert c["args"] == ["--flavor", "prod"]


@pytest.mark.asyncio
async def test_writes_file_when_missing(tmp_path: Path):
    uc = WriteVscodeLaunchConfig()
    res = await uc.execute(
        WriteVscodeLaunchConfigParams(project_path=tmp_path, flavor="dev")
    )
    assert res.is_ok and res.value.created
    out = tmp_path / ".vscode" / "launch.json"
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["version"] == "0.2.0"


@pytest.mark.asyncio
async def test_does_not_overwrite_by_default(tmp_path: Path):
    out = tmp_path / ".vscode" / "launch.json"
    out.parent.mkdir()
    out.write_text('{"hand":"tuned"}')
    uc = WriteVscodeLaunchConfig()
    res = await uc.execute(WriteVscodeLaunchConfigParams(project_path=tmp_path))
    assert res.is_ok and res.value.created is False
    assert out.read_text() == '{"hand":"tuned"}'


@pytest.mark.asyncio
async def test_overwrite_replaces_existing(tmp_path: Path):
    out = tmp_path / ".vscode" / "launch.json"
    out.parent.mkdir()
    out.write_text('{"hand":"tuned"}')
    uc = WriteVscodeLaunchConfig()
    res = await uc.execute(
        WriteVscodeLaunchConfigParams(project_path=tmp_path, overwrite=True)
    )
    assert res.is_ok and res.value.created
    assert "configurations" in out.read_text()


@pytest.mark.asyncio
async def test_missing_project_directory_errors(tmp_path: Path):
    uc = WriteVscodeLaunchConfig()
    res = await uc.execute(
        WriteVscodeLaunchConfigParams(project_path=tmp_path / "nope")
    )
    assert not res.is_ok
    assert res.failure.next_action == "fix_arguments"
