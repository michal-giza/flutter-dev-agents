"""Tier-G discovery primitives: recommended_sequence, replay buffer, auto-narrate."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mcp_phone_controll.domain.entities import SessionTrace, TraceEntry
from mcp_phone_controll.domain.result import ok
from mcp_phone_controll.domain.tool_levels import recommended_sequence_for_level
from mcp_phone_controll.domain.usecases.discovery import (
    DescribeCapabilities,
    DescribeCapabilitiesParams,
    DescribeTool,
    DescribeToolParams,
)


# ---- G1: recommended_sequence -------------------------------------------


def test_recommended_sequence_basic_starts_with_describe():
    seq = recommended_sequence_for_level("basic")
    assert seq[0] == "describe_capabilities"
    assert "release_device" in seq


def test_recommended_sequence_intermediate_includes_dev_session():
    seq = recommended_sequence_for_level("intermediate")
    assert "start_debug_session" in seq
    assert "tap_and_verify" in seq


def test_recommended_sequence_expert_is_empty():
    # Expert tier (Claude) deliberately gets no prescribed path.
    assert recommended_sequence_for_level("expert") == ()


# ---- G2: replay buffer in describe_tool ---------------------------------


class _Repo:
    def __init__(self, entries):
        self._entries = entries

    async def record(self, _e):
        return ok(None)

    async def summary(self, _sid=None):
        return ok(
            SessionTrace(
                session_id="s",
                started_at=datetime(2026, 1, 1),
                entries=tuple(self._entries),
            )
        )


def _entry(seq, name, ok_=True, args=None):
    return TraceEntry(
        sequence=seq,
        tool_name=name,
        args=args or {},
        ok=ok_,
        error_code=None,
        summary="ok" if ok_ else "fail",
    )


_DESCRIPTOR = {
    "name": "select_device",
    "description": "Select a device by serial.",
    "input_schema": {
        "type": "object",
        "properties": {"serial": {"type": "string"}},
        "required": ["serial"],
    },
}


@pytest.mark.asyncio
async def test_describe_tool_returns_replay_buffer_with_successful_calls():
    entries = [
        _entry(1, "select_device", args={"serial": "EMU01"}),
        _entry(2, "list_devices"),
        _entry(3, "select_device", ok_=False, args={"serial": "BAD"}),
        _entry(4, "select_device", args={"serial": "R3CYA05CHXB"}),
        _entry(5, "select_device", args={"serial": "EMU02"}),
    ]
    uc = DescribeTool(lambda n: _DESCRIPTOR, traces=_Repo(entries), replay_size=3)
    res = await uc.execute(DescribeToolParams(name="select_device"))
    assert res.is_ok
    replay = res.value.replay
    assert len(replay) == 3
    # Most-recent-first; the failed call is excluded.
    assert replay[0]["args"] == {"serial": "EMU02"}
    assert replay[1]["args"] == {"serial": "R3CYA05CHXB"}
    assert replay[2]["args"] == {"serial": "EMU01"}


@pytest.mark.asyncio
async def test_describe_tool_returns_empty_replay_when_no_traces_repo():
    uc = DescribeTool(lambda n: _DESCRIPTOR, traces=None)
    res = await uc.execute(DescribeToolParams(name="select_device"))
    assert res.is_ok
    assert res.value.replay == ()


@pytest.mark.asyncio
async def test_describe_tool_replay_size_zero_disables():
    entries = [_entry(1, "select_device", args={"serial": "EMU01"})]
    uc = DescribeTool(lambda n: _DESCRIPTOR, traces=_Repo(entries), replay_size=0)
    res = await uc.execute(DescribeToolParams(name="select_device"))
    assert res.is_ok
    assert res.value.replay == ()


# ---- G3: auto-narrate via dispatcher (integration) ----------------------


@pytest.mark.asyncio
async def test_auto_narrate_appends_summary_every_nth_call(tmp_path: Path):
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher
    from mcp_phone_controll.presentation.middleware import AutoNarrateMiddleware

    d = _build_fake_dispatcher(tmp_path)
    # Reach into the middleware chain rather than patching private dispatcher
    # state — the refactor moved auto-narrate into its own middleware.
    narrate_mw = next(mw for mw in d.middlewares if isinstance(mw, AutoNarrateMiddleware))
    narrate_mw._every = 2
    narrate_mw._counter = 0

    r1 = await d.dispatch("list_devices", {})
    assert "narrate" not in r1
    r2 = await d.dispatch("list_devices", {})
    assert "narrate" in r2
    r3 = await d.dispatch("list_devices", {})
    assert "narrate" not in r3
    r4 = await d.dispatch("list_devices", {})
    assert "narrate" in r4


@pytest.mark.asyncio
async def test_auto_narrate_off_by_default(tmp_path: Path):
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher
    d = _build_fake_dispatcher(tmp_path)
    r = await d.dispatch("list_devices", {})
    assert "narrate" not in r
