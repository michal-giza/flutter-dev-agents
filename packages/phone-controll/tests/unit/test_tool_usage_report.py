"""Unit tests for ToolUsageReport — dead-tool surfacing + error rates."""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.entities import SessionTrace, TraceEntry
from mcp_phone_controll.domain.result import ok
from mcp_phone_controll.domain.usecases.discovery import (
    ToolUsageReportParams,
    ToolUsageReportUseCase,
)


class _StaticTraceRepo:
    def __init__(self, entries):
        self._entries = entries

    async def record(self, entry):
        return ok(None)

    async def summary(self, session_id=None):
        from datetime import datetime

        return ok(
            SessionTrace(
                session_id=session_id or "s1",
                started_at=datetime(2024, 1, 1),
                entries=tuple(self._entries),
            )
        )


def _entry(seq, name, ok_=True, code=None):
    return TraceEntry(
        sequence=seq,
        tool_name=name,
        args={},
        ok=ok_,
        error_code=code,
        summary="ok" if ok_ else (code or "error"),
    )


@pytest.mark.asyncio
async def test_report_aggregates_counts_and_errors():
    entries = [
        _entry(1, "select_device"),
        _entry(2, "tap_text"),
        _entry(3, "tap_text", ok_=False, code="UiElementNotFoundFailure"),
        _entry(4, "take_screenshot"),
        _entry(5, "tap_text", ok_=False, code="UiElementNotFoundFailure"),
    ]
    uc = ToolUsageReportUseCase(
        _StaticTraceRepo(entries),
        all_tool_names_provider=lambda: (
            "select_device",
            "tap_text",
            "take_screenshot",
            "release_device",
            "list_devices",
        ),
    )
    res = await uc.execute(ToolUsageReportParams())
    assert res.is_ok
    rep = res.value
    assert rep.total_calls == 5
    by_name = {row.name: row for row in rep.by_tool}
    assert by_name["tap_text"].calls == 3
    assert by_name["tap_text"].errors == 2
    assert abs(by_name["tap_text"].error_rate - 2 / 3) < 1e-6
    # Dead tools come from the all-tools-set difference.
    assert "release_device" in rep.dead_tools
    assert "list_devices" in rep.dead_tools
    # Top errors include tap_text.
    assert any(r.name == "tap_text" for r in rep.top_errors)


@pytest.mark.asyncio
async def test_report_handles_empty_session():
    uc = ToolUsageReportUseCase(
        _StaticTraceRepo([]),
        all_tool_names_provider=lambda: ("select_device", "tap_text"),
    )
    res = await uc.execute(ToolUsageReportParams())
    assert res.is_ok
    rep = res.value
    assert rep.total_calls == 0
    assert rep.by_tool == ()
    assert set(rep.dead_tools) == {"select_device", "tap_text"}
