"""Dispatcher must emit start/end structured logs for every tool call.

The Tier 1 wiring (commit `84be6ec` follow-up) turned `observability.emit`
from dead code into the dispatcher's per-call trace. These tests pin
the contract so a future refactor doesn't silently lose telemetry —
the kind of regression you only notice when you go to debug a problem
and there's nothing in the logs.

Capture by patching `observability.emit` to a list-appender.
"""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.failures import UnexpectedFailure
from mcp_phone_controll.domain.result import err, ok
from mcp_phone_controll.presentation.descriptors._shared import ToolDescriptor
from mcp_phone_controll.presentation.tool_registry import ToolDispatcher


def _capturing_dispatcher(monkeypatch, descriptors):
    """Build a dispatcher whose `observability.emit` writes into a
    list. Returns (dispatcher, captured_events)."""
    captured: list[dict] = []

    def _fake_emit(event, level="info", **fields):
        captured.append({"event": event, "level": level, **fields})

    # The dispatcher imports `emit` lazily inside dispatch(), so patch
    # the source module — every import resolves to the fake.
    from mcp_phone_controll import observability

    monkeypatch.setattr(observability, "emit", _fake_emit)
    return ToolDispatcher(descriptors), captured


@pytest.mark.asyncio
async def test_success_dispatch_emits_start_and_end(monkeypatch):
    async def _invoke(_args):
        return ok({"hello": "world"})

    d, captured = _capturing_dispatcher(
        monkeypatch,
        [
            ToolDescriptor(
                name="ping",
                description="",
                input_schema={"type": "object", "properties": {}},
                build_params=lambda _: None,
                invoke=_invoke,
            )
        ],
    )

    res = await d.dispatch("ping", {"k": 1})
    assert res["ok"] is True

    events = [e["event"] for e in captured]
    assert "tool_dispatch_start" in events
    assert "tool_dispatch_end" in events

    start = next(e for e in captured if e["event"] == "tool_dispatch_start")
    end = next(e for e in captured if e["event"] == "tool_dispatch_end")
    assert start["tool"] == "ping"
    assert start["arg_keys"] == ["k"]
    assert end["tool"] == "ping"
    assert end["ok"] is True
    assert isinstance(end["duration_ms"], int)
    assert end["duration_ms"] >= 0
    assert end["short_circuited"] is False
    assert end["level"] == "info"


@pytest.mark.asyncio
async def test_failed_dispatch_emits_warn_with_error_code(monkeypatch):
    async def _invoke(_args):
        return err(
            UnexpectedFailure(
                message="boom",
                next_action="retry_with_backoff",
            )
        )

    d, captured = _capturing_dispatcher(
        monkeypatch,
        [
            ToolDescriptor(
                name="explodes",
                description="",
                input_schema={"type": "object", "properties": {}},
                build_params=lambda _: None,
                invoke=_invoke,
            )
        ],
    )

    res = await d.dispatch("explodes", None)
    assert res["ok"] is False

    end = next(e for e in captured if e["event"] == "tool_dispatch_end")
    assert end["ok"] is False
    assert end["level"] == "warn"
    assert end["error_code"] == "UnexpectedFailure"
    assert end["next_action"] == "retry_with_backoff"


@pytest.mark.asyncio
async def test_unknown_tool_still_emits_end_event(monkeypatch):
    d, captured = _capturing_dispatcher(monkeypatch, [])

    res = await d.dispatch("not_a_tool", {})
    assert res["ok"] is False
    assert res["error"]["code"] == "UnknownTool"

    end = next(e for e in captured if e["event"] == "tool_dispatch_end")
    assert end["error_code"] == "UnknownTool"
    assert end["next_action"] == "describe_capabilities"
