"""Tests for ingest_har — per-action network cost from a HAR export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.ingest_har import (
    IngestHar,
    IngestHarParams,
)


def _entry(url, method="GET", status=200, size=500, time_ms=100.0):
    return {
        "request": {"method": method, "url": url},
        "response": {"status": status, "content": {"size": size}},
        "time": time_ms,
    }


def _har(*entries) -> dict:
    return {"log": {"version": "1.2", "entries": list(entries)}}


def _write_har(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "capture.har"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


async def _run(tmp_path, data, **kw):
    res = await IngestHar()(
        IngestHarParams(har_path=_write_har(tmp_path, data), **kw)
    )
    assert isinstance(res, Ok), res
    return res.value


# ---- core parsing -------------------------------------------------------


@pytest.mark.asyncio
async def test_counts_reads_and_writes_per_host(tmp_path):
    r = await _run(tmp_path, _har(
        _entry("https://api.example.com/articles", "GET"),
        _entry("https://api.example.com/articles", "GET"),
        _entry("https://api.example.com/save", "POST"),
        _entry("https://cdn.gstatic.com/font.woff2", "GET"),
    ), backend_host="api.example.com")
    assert r.total_requests == 4
    assert r.backend is not None
    assert r.backend.host == "api.example.com"
    assert r.backend.reads == 2
    assert r.backend.writes == 1


@pytest.mark.asyncio
async def test_auto_picks_non_cdn_backend(tmp_path):
    r = await _run(tmp_path, _har(
        _entry("https://fonts.gstatic.com/a.woff2"),
        _entry("https://fonts.gstatic.com/b.woff2"),
        _entry("https://fonts.gstatic.com/c.woff2"),
        _entry("https://my-backend.hf.space/api/feed"),
    ))
    # gstatic is busiest but is a CDN — backend should be the hf.space host
    assert r.backend_host == "my-backend.hf.space"


@pytest.mark.asyncio
async def test_latency_percentiles(tmp_path):
    r = await _run(tmp_path, _har(
        *[_entry("https://api.x.com/a", time_ms=t) for t in (10, 20, 30, 40, 1000)]
    ), backend_host="api.x.com")
    assert r.backend.p50_ms >= 20
    assert r.backend.p95_ms >= 1000  # the slow outlier shows in p95
    assert r.backend.slowest_ms == 1000


# ---- grading ------------------------------------------------------------


@pytest.mark.asyncio
async def test_good_grade_low_cost(tmp_path):
    r = await _run(tmp_path, _har(
        _entry("https://api.x.com/feed", time_ms=120),
    ), backend_host="api.x.com")
    assert r.grade == "good"


@pytest.mark.asyncio
async def test_poor_when_chatty(tmp_path):
    r = await _run(tmp_path, _har(
        *[_entry(f"https://api.x.com/r{i}") for i in range(60)]
    ), backend_host="api.x.com")
    assert r.grade == "poor"  # >50 reads


@pytest.mark.asyncio
async def test_needs_improvement_on_4xx(tmp_path):
    r = await _run(tmp_path, _har(
        _entry("https://api.x.com/feed", status=200),
        _entry("https://api.x.com/missing", status=404),
    ), backend_host="api.x.com")
    assert r.grade == "needs_improvement"
    assert r.backend.error_count == 1
    assert r.error_count == 1


@pytest.mark.asyncio
async def test_blocked_on_5xx(tmp_path):
    r = await _run(tmp_path, _har(
        _entry("https://api.x.com/feed", status=500),
    ), backend_host="api.x.com")
    assert r.grade == "blocked"
    assert r.backend.server_errors == 1


@pytest.mark.asyncio
async def test_slowest_list_sorted(tmp_path):
    r = await _run(tmp_path, _har(
        _entry("https://api.x.com/fast", time_ms=50),
        _entry("https://api.x.com/slow", time_ms=3000),
        _entry("https://api.x.com/mid", time_ms=800),
    ), backend_host="api.x.com")
    assert r.slowest[0].startswith("GET https://api.x.com/slow")
    assert "3000ms" in r.slowest[0]


# ---- failure modes ------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_file(tmp_path):
    res = await IngestHar()(IngestHarParams(har_path=tmp_path / "nope.har"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_not_a_har(tmp_path):
    p = tmp_path / "x.har"
    p.write_text('{"not": "a har"}', encoding="utf-8")
    res = await IngestHar()(IngestHarParams(har_path=p))
    assert isinstance(res, Err)
    assert "HAR" in res.failure.message


@pytest.mark.asyncio
async def test_directory_resolution(tmp_path):
    _write_har(tmp_path, _har(_entry("https://api.x.com/feed")))
    res = await IngestHar()(IngestHarParams(har_path=tmp_path))  # dir, not file
    assert isinstance(res, Ok)
    assert res.value.total_requests == 1
