"""ProgressLogMiddleware — emits a structured `tool_dispatch` event per call."""

from __future__ import annotations

import json

import pytest

from mcp_phone_controll.presentation.middleware import ProgressLogMiddleware


@pytest.mark.asyncio
async def test_emits_info_event_under_threshold(monkeypatch, capsys):
    monkeypatch.setenv("MCP_LOG_FORMAT", "json")
    monkeypatch.setenv("MCP_PROGRESS_LOG", "on")
    monkeypatch.delenv("MCP_QUIET", raising=False)
    mw = ProgressLogMiddleware(slow_threshold_ms=10_000)
    args = {"x": 1}
    await mw.pre_dispatch("list_devices", args)
    await mw.post_dispatch("list_devices", args, {"ok": True})
    line = capsys.readouterr().err.strip().split("\n")[-1]
    payload = json.loads(line)
    assert payload["event"] == "tool_dispatch"
    assert payload["tool"] == "list_devices"
    assert payload["ok"] is True
    assert payload["level"] == "info"
    assert "duration_ms" in payload


@pytest.mark.asyncio
async def test_disabled_via_env(monkeypatch, capsys):
    monkeypatch.setenv("MCP_PROGRESS_LOG", "off")
    monkeypatch.setenv("MCP_LOG_FORMAT", "json")
    monkeypatch.delenv("MCP_QUIET", raising=False)
    mw = ProgressLogMiddleware()
    await mw.pre_dispatch("any", {})
    await mw.post_dispatch("any", {}, {"ok": True})
    captured = capsys.readouterr().err.strip()
    assert "tool_dispatch" not in captured
