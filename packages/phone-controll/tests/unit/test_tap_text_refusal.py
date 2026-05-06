"""Dispatcher refuses tap_text on app UI once a Patrol session is active."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.test_tool_dispatcher import _build_fake_dispatcher


@pytest.mark.asyncio
async def test_tap_text_allowed_before_patrol_activates(tmp_path: Path):
    d = _build_fake_dispatcher(tmp_path)
    await d.dispatch("select_device", {"serial": "EMU01"})
    res = await d.dispatch("tap_text", {"text": "Settings"})
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_tap_text_refused_after_prepare_for_test(tmp_path: Path):
    d = _build_fake_dispatcher(tmp_path)
    await d.dispatch("select_device", {"serial": "EMU01"})
    await d.dispatch(
        "prepare_for_test",
        {"package_id": "com.example", "project_path": str(tmp_path)},
    )
    res = await d.dispatch("tap_text", {"text": "Sign in"})
    assert res["ok"] is False
    assert res["error"]["code"] == "TapTextRefused"
    assert res["error"]["next_action"] == "use_patrol"


@pytest.mark.asyncio
async def test_tap_text_with_system_flag_still_works(tmp_path: Path):
    d = _build_fake_dispatcher(tmp_path)
    await d.dispatch("select_device", {"serial": "EMU01"})
    await d.dispatch(
        "prepare_for_test",
        {"package_id": "com.example", "project_path": str(tmp_path)},
    )
    res = await d.dispatch("tap_text", {"text": "Allow", "system": True})
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_release_device_clears_patrol_lock(tmp_path: Path):
    d = _build_fake_dispatcher(tmp_path)
    await d.dispatch("select_device", {"serial": "EMU01"})
    await d.dispatch(
        "prepare_for_test",
        {"package_id": "com.example", "project_path": str(tmp_path)},
    )
    await d.dispatch("release_device", {})
    res = await d.dispatch("tap_text", {"text": "anything"})
    # release_device clears the Patrol guard. The tap may still fail later for
    # an unrelated reason (no device selected, etc.), but it must NOT be
    # refused with TapTextRefused.
    if not res["ok"]:
        assert res["error"]["code"] != "TapTextRefused"
