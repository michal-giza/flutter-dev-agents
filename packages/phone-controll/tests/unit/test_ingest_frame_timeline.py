"""Tests for ingest_frame_timeline — jank score from a captured timeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.ingest_frame_timeline import (
    IngestFrameTimeline,
    IngestFrameTimelineParams,
)


def _write(tmp_path: Path, data: dict, name="timeline.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


async def _run(tmp_path, data, **kw):
    res = await IngestFrameTimeline()(
        IngestFrameTimelineParams(timeline_path=_write(tmp_path, data), **kw)
    )
    assert isinstance(res, Ok), res
    return res.value


# ---- frames_ms list -----------------------------------------------------


@pytest.mark.asyncio
async def test_smooth_frames(tmp_path):
    r = await _run(tmp_path, {"frames_ms": [12, 13, 14, 15, 16] * 20})
    assert r.grade == "smooth"
    assert r.source == "frames"
    assert r.janky_count == 0
    assert r.budget_ms == 16.67


@pytest.mark.asyncio
async def test_janky_frames(tmp_path):
    # 20% of frames over budget but under 2x (janky, not severe)
    frames = [12.0] * 80 + [25.0] * 20
    r = await _run(tmp_path, {"frames_ms": frames})
    assert r.janky_count == 20
    assert r.janky_pct == 20.0
    assert r.severe_count == 0
    assert r.grade == "janky"
    assert r.worst_ms == 25.0


@pytest.mark.asyncio
async def test_severe_frames(tmp_path):
    frames = [12.0] * 50 + [50.0] * 50  # 50% janky, all severe
    r = await _run(tmp_path, {"frames_ms": frames})
    assert r.grade == "severe"
    assert r.severe_count == 50


@pytest.mark.asyncio
async def test_120fps_budget(tmp_path):
    # 10ms frames are smooth at 60fps but janky at 120fps (budget 8.33)
    r60 = await _run(tmp_path, {"frames_ms": [10.0] * 50}, fps=60)
    assert r60.janky_count == 0
    r120 = await _run(tmp_path, {"frames_ms": [10.0] * 50}, fps=120)
    assert r120.budget_ms == 8.33
    assert r120.janky_count == 50


# ---- frames with build/raster split ------------------------------------


@pytest.mark.asyncio
async def test_build_raster_split(tmp_path):
    frames = [{"build_ms": 5.0, "raster_ms": 4.0} for _ in range(30)]
    r = await _run(tmp_path, {"frames": frames})
    assert r.avg_build_ms == 5.0
    assert r.avg_raster_ms == 4.0
    assert r.janky_count == 0  # 9ms total < 16.67


# ---- Trace Event Format -------------------------------------------------


@pytest.mark.asyncio
async def test_trace_flutter_frame_events(tmp_path):
    # Flutter "Frame" complete events, dur in microseconds
    events = [
        {"ph": "X", "name": "Frame", "dur": 12000},   # 12ms
        {"ph": "X", "name": "Frame", "dur": 40000},   # 40ms — janky
        {"ph": "X", "name": "Frame", "dur": 10000},
        {"ph": "X", "name": "Other", "dur": 99000},   # ignored
    ]
    r = await _run(tmp_path, {"traceEvents": events})
    assert r.source == "trace_frames"
    assert r.frame_count == 3
    assert r.janky_count == 1


@pytest.mark.asyncio
async def test_trace_web_longtasks_fallback(tmp_path):
    # No Flutter Frame events → fall back to top-level tasks
    events = [
        {"ph": "X", "name": "RunTask", "dur": 8000},     # 8ms
        {"ph": "X", "name": "RunTask", "dur": 120000},   # 120ms long task
        {"ph": "X", "cat": "toplevel", "dur": 5000},
    ]
    r = await _run(tmp_path, {"traceEvents": events})
    assert r.source == "trace_tasks"
    assert r.frame_count == 3
    assert r.janky_count == 1  # the 120ms task


# ---- failure modes ------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_file(tmp_path):
    res = await IngestFrameTimeline()(
        IngestFrameTimelineParams(timeline_path=tmp_path / "nope.json")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_empty_timeline(tmp_path):
    res = await IngestFrameTimeline()(
        IngestFrameTimelineParams(timeline_path=_write(tmp_path, {"traceEvents": []}))
    )
    assert isinstance(res, Err)
    assert "No frames" in res.failure.message
