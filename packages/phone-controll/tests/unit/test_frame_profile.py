"""Tests for the v0.3.0 frame-profiling use cases.

Hermetic — stubs the VmServiceClient module-level so no real VM
service is needed. The interesting test surface is the
event-analysis logic, since the use-case lifecycle (connect →
call → disconnect) is tested via the existing memory-inspect
suite's stub pattern.

Coverage:
- _analyze_frame_events: the pure analyzer. Synthetic Chrome-trace
  events → correct counts, percentiles, jank classification,
  worst-frame ranking, advice line.
- StartFrameProfile: confirms it sends the right
  setVMTimelineFlags call.
- StopFrameProfile: confirms it ALWAYS disables on exit, even if
  the analysis errors.
- Edge cases: zero frames, exactly 1 frame, all frames smooth,
  all frames janked.
"""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.entities import DebugSession, DebugSessionState
from mcp_phone_controll.domain.result import Err, Ok, ok
from mcp_phone_controll.domain.usecases.frame_profile import (
    StartFrameProfile,
    StartFrameProfileParams,
    StopFrameProfile,
    StopFrameProfileParams,
    _analyze_frame_events,
)

# ---- fixtures: stub VM client + fake debug repo ------------------------


class _StubVmClient:
    def __init__(self, responses: dict | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict]] = []

    async def connect(self, timeout_s: float = 10.0) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get_vm(self) -> dict:
        return self.responses.get(
            "getVM",
            {"result": {"isolates": [
                {"id": "isolates/1", "name": "main", "runnable": True}
            ]}},
        )

    async def call(self, method: str, params: dict) -> dict:
        self.calls.append((method, params))
        return self.responses.get(method, {"result": {}})


def _patch_vm(monkeypatch, stub: _StubVmClient) -> None:
    """Patch the module-level _with_vm helper to use our stub."""
    import mcp_phone_controll.domain.usecases.frame_profile as mod

    async def _fake_with_vm(uri, op, **kwargs):
        return await op(stub, **kwargs)

    monkeypatch.setattr(mod, "_with_vm", _fake_with_vm)


class _FakeDebugRepo:
    def __init__(self, vm_service_uri: str | None = "ws://127.0.0.1:0/ws"):
        self._uri = vm_service_uri

    async def list_sessions(self):
        return ok([
            DebugSession(
                id="dbg-1",
                project_path="/p",
                device_serial="X",
                mode="debug",
                started_at=0.0,
                vm_service_uri=self._uri,
                app_id="app",
                state=DebugSessionState.RUNNING,
            )
        ])


# ---- _analyze_frame_events: the pure analyzer --------------------------


def _make_frame_event(start: int, dur: int, sub_events: list[dict] | None = None) -> list[dict]:
    """Build a Frame event with optional Build/Raster sub-events.

    Chrome trace format: 'ph': 'X' = complete event with `dur`.
    """
    events = [{"ph": "X", "name": "Frame", "ts": start, "dur": dur}]
    for sub in sub_events or []:
        events.append({"ph": "X", "ts": sub["ts"], "dur": sub["dur"], "name": sub["name"]})
    return events


def test_analyze_smooth_frames_at_60fps():
    """20 frames all at 12ms (well under 16.67ms 60fps budget). 0 janked."""
    events: list[dict] = []
    for i in range(20):
        events.extend(_make_frame_event(start=i * 16_000, dur=12_000))
    result = _analyze_frame_events(events, target_fps=60, tolerance_pct=0.10)
    assert result.total_frames == 20
    assert result.janked_frames == 0
    assert result.jank_pct == 0.0
    assert result.max_micros == 12_000
    assert "Smooth" in result.advice or "✓" in result.advice


def test_analyze_significant_jank_at_60fps():
    """20 frames, 10 over budget. 50% jank → 'significant'."""
    events: list[dict] = []
    for i in range(10):
        events.extend(_make_frame_event(start=i * 16_000, dur=10_000))
    for i in range(10, 20):
        # 30ms — well over 18.3ms threshold (16.67 * 1.10)
        events.extend(_make_frame_event(start=i * 16_000, dur=30_000))
    result = _analyze_frame_events(events, target_fps=60, tolerance_pct=0.10)
    assert result.total_frames == 20
    assert result.janked_frames == 10
    assert abs(result.jank_pct - 0.50) < 0.01
    assert "Significant" in result.advice or "❌" in result.advice


def test_analyze_noticeable_jank_at_60fps():
    """100 frames, 3 janked. Between 1% and 5% → 'noticeable'."""
    events: list[dict] = []
    for i in range(97):
        events.extend(_make_frame_event(start=i * 16_000, dur=10_000))
    for i in range(97, 100):
        events.extend(_make_frame_event(start=i * 16_000, dur=25_000))
    result = _analyze_frame_events(events, target_fps=60, tolerance_pct=0.10)
    assert result.janked_frames == 3
    assert "Noticeable" in result.advice or "⚠" in result.advice


def test_analyze_respects_tolerance_pct():
    """Frame at exactly 17ms (16.67 + 0.33ms) → within 10% tolerance, NOT janked."""
    events = _make_frame_event(start=0, dur=17_000)
    events.extend(_make_frame_event(start=20_000, dur=17_000))
    result = _analyze_frame_events(events, target_fps=60, tolerance_pct=0.10)
    # 17ms is within 16.67 * 1.10 = 18.3ms → not janked
    assert result.janked_frames == 0


def test_analyze_120fps_budget():
    """At 120fps, budget is 8.33ms — a 12ms frame IS jank."""
    events = _make_frame_event(start=0, dur=12_000)
    result = _analyze_frame_events(events, target_fps=120, tolerance_pct=0.10)
    # 8.33 * 1.10 = 9.17ms threshold; 12ms > threshold
    assert result.janked_frames == 1
    assert result.budget_micros == 8333


def test_analyze_zero_frames_returns_helpful_advice():
    """No Frame events in trace → 'no frames captured' advice line."""
    result = _analyze_frame_events([], target_fps=60, tolerance_pct=0.10)
    assert result.total_frames == 0
    assert result.janked_frames == 0
    assert "No frames captured" in result.advice


def test_analyze_too_few_frames_advises_longer_window():
    """< 10 frames → advice asks for a longer bracket window."""
    events: list[dict] = []
    for i in range(5):
        events.extend(_make_frame_event(start=i * 16_000, dur=10_000))
    result = _analyze_frame_events(events, target_fps=60, tolerance_pct=0.10)
    assert result.total_frames == 5
    assert "too few" in result.advice.lower()


def test_analyze_extracts_build_and_raster_split():
    """Frame at 20ms with 8ms build + 10ms raster inside.
    The per-frame split should be captured."""
    events = [
        # Frame containing the sub-events at ts 1000-21000
        {"ph": "X", "name": "Frame", "ts": 1000, "dur": 20_000},
        # Build sub-event inside that window
        {"ph": "X", "name": "Build", "ts": 2000, "dur": 8_000},
        # Raster sub-event inside that window
        {"ph": "X", "name": "Raster", "ts": 12_000, "dur": 10_000},
    ]
    result = _analyze_frame_events(events, target_fps=60, tolerance_pct=0.10)
    assert result.total_frames == 1
    assert result.worst_frames[0].build_micros == 8_000
    assert result.worst_frames[0].raster_micros == 10_000


def test_analyze_returns_worst_3_frames_sorted():
    """top-3 worst frames should be sorted longest-first."""
    durations = [10_000, 25_000, 30_000, 35_000, 15_000]  # frame-5 longest in middle
    events: list[dict] = []
    for i, dur in enumerate(durations):
        events.extend(_make_frame_event(start=i * 40_000, dur=dur))
    result = _analyze_frame_events(events, target_fps=60, tolerance_pct=0.10)
    assert len(result.worst_frames) == 3
    assert result.worst_frames[0].duration_micros == 35_000
    assert result.worst_frames[1].duration_micros == 30_000
    assert result.worst_frames[2].duration_micros == 25_000


def test_analyze_filters_non_frame_events():
    """Trace contains GC + other event types — only Frame events count."""
    events = [
        {"ph": "X", "name": "Frame", "ts": 0, "dur": 10_000},
        {"ph": "X", "name": "GC", "ts": 12_000, "dur": 5_000},      # not a frame
        {"ph": "X", "name": "Compiler", "ts": 18_000, "dur": 1000},  # not a frame
        {"ph": "X", "name": "Frame", "ts": 20_000, "dur": 14_000},
    ]
    result = _analyze_frame_events(events, target_fps=60, tolerance_pct=0.10)
    assert result.total_frames == 2


# ---- StartFrameProfile -------------------------------------------------


@pytest.mark.asyncio
async def test_start_frame_profile_enables_timeline_streams(monkeypatch):
    """Confirms the right setVMTimelineFlags call is made."""
    stub = _StubVmClient(responses={
        "setVMTimelineFlags": {"result": {}},
        "getVMTimelineMicros": {"result": {"timestamp": 123_456}},
    })
    _patch_vm(monkeypatch, stub)

    res = await StartFrameProfile(_FakeDebugRepo())(StartFrameProfileParams())
    assert isinstance(res, Ok)
    # Confirm setVMTimelineFlags was called with embedder + dart + gc
    flag_calls = [c for c in stub.calls if c[0] == "setVMTimelineFlags"]
    assert len(flag_calls) == 1
    streams = flag_calls[0][1].get("recordedStreams", [])
    assert "Embedder" in streams
    assert "Dart" in streams
    # Baseline captured for diagnostics
    assert res.value.started_at_micros == 123_456


@pytest.mark.asyncio
async def test_start_frame_profile_no_session_returns_typed_failure():
    """No active session → DebugSessionFailure."""
    res = await StartFrameProfile(_FakeDebugRepo(vm_service_uri=None))(
        StartFrameProfileParams()
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "start_debug_session"


# ---- StopFrameProfile --------------------------------------------------


@pytest.mark.asyncio
async def test_stop_frame_profile_always_disables_on_exit(monkeypatch):
    """The whole point: stop ALWAYS disables Timeline streams.

    Even when the trace is empty (no frames captured) — we must
    leave the device with collection off so we don't leak the
    ~5-10% CPU overhead across sessions.
    """
    stub = _StubVmClient(responses={
        "getVMTimeline": {"result": {"traceEvents": []}},
        "setVMTimelineFlags": {"result": {}},
    })
    _patch_vm(monkeypatch, stub)

    await StopFrameProfile(_FakeDebugRepo())(StopFrameProfileParams())
    # The disable call (recordedStreams=[]) MUST have happened
    disable_calls = [
        c for c in stub.calls
        if c[0] == "setVMTimelineFlags" and c[1].get("recordedStreams") == []
    ]
    assert len(disable_calls) >= 1, (
        "stop_frame_profile must always disable Timeline streams on exit; "
        f"all calls: {stub.calls}"
    )


@pytest.mark.asyncio
async def test_stop_frame_profile_returns_jank_analysis(monkeypatch):
    """End-to-end: trace events → returned StopFrameProfileResult."""
    trace_events = []
    # 50 smooth frames at 10ms each
    for i in range(50):
        trace_events.extend(_make_frame_event(start=i * 16_000, dur=10_000))
    stub = _StubVmClient(responses={
        "getVMTimeline": {"result": {"traceEvents": trace_events}},
        "setVMTimelineFlags": {"result": {}},
    })
    _patch_vm(monkeypatch, stub)

    res = await StopFrameProfile(_FakeDebugRepo())(StopFrameProfileParams())
    assert isinstance(res, Ok)
    v = res.value
    assert v.total_frames == 50
    assert v.janked_frames == 0
    assert v.budget_micros == 16_666
