"""Tests for v0.5.0 phase-16 Lighthouse report ingestion.

Lighthouse JSON parsing: category scores, Core Web Vitals,
opportunities, CanvasKit-aware grading. We don't run Lighthouse;
we parse what it produces.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.ingest_lighthouse_report import (
    IngestLighthouseReport,
    IngestLighthouseReportParams,
)


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _lh_report(
    *,
    perf=0.85,
    a11y=0.95,
    seo=0.92,
    lcp_ms=2100.0,
    cls=0.05,
    tbt_ms=150.0,
    url="https://example.com/",
    opportunities=None,
) -> dict:
    """Build a minimal-but-realistic Lighthouse JSON structure."""
    audits = {
        "largest-contentful-paint": {
            "numericValue": lcp_ms,
            "displayValue": f"{lcp_ms / 1000:.1f} s",
            "score": 0.9 if lcp_ms < 2500 else 0.4,
        },
        "cumulative-layout-shift": {
            "numericValue": cls,
            "displayValue": str(cls),
            "score": 0.95 if cls < 0.1 else 0.3,
        },
        "total-blocking-time": {
            "numericValue": tbt_ms,
            "displayValue": f"{tbt_ms:.0f} ms",
            "score": 0.9 if tbt_ms < 200 else 0.4,
        },
        "first-contentful-paint": {
            "numericValue": 900.0, "displayValue": "0.9 s", "score": 0.95,
        },
    }
    if opportunities:
        for i, (title, savings) in enumerate(opportunities):
            audits[f"opp-{i}"] = {
                "title": title,
                "score": 0.5,
                "details": {"overallSavingsMs": savings},
            }
    return {
        "finalUrl": url,
        "categories": {
            "performance": {"score": perf},
            "accessibility": {"score": a11y},
            "best-practices": {"score": 0.93},
            "seo": {"score": seo},
        },
        "audits": audits,
    }


async def _run(**kwargs) -> Ok | Err:
    return await IngestLighthouseReport()(
        IngestLighthouseReportParams(**kwargs)
    )


# ---- error handling ----------------------------------------------------


@pytest.mark.asyncio
async def test_missing_report_returns_failure(tmp_path: Path):
    res = await _run(report_path=tmp_path / "nope.json")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_malformed_json_returns_failure(tmp_path: Path):
    bad = _write(tmp_path / "lh.json", "{not json")
    res = await _run(report_path=bad)
    assert isinstance(res, Err)


@pytest.mark.asyncio
async def test_non_lighthouse_json_returns_failure(tmp_path: Path):
    """A valid JSON that isn't a Lighthouse report (no categories)."""
    bad = _write(tmp_path / "lh.json", json.dumps({"foo": "bar"}))
    res = await _run(report_path=bad)
    assert isinstance(res, Err)
    assert "categories" in res.failure.message.lower()


@pytest.mark.asyncio
async def test_directory_resolves_report(tmp_path: Path):
    _write(tmp_path / "lighthouse.json", json.dumps(_lh_report()))
    res = await _run(report_path=tmp_path)
    assert isinstance(res, Ok)
    assert res.value.fetched_url == "https://example.com/"


# ---- happy path --------------------------------------------------------


@pytest.mark.asyncio
async def test_good_report_grades_good(tmp_path: Path):
    _write(tmp_path / "lh.json", json.dumps(_lh_report(
        perf=0.85, a11y=0.95, lcp_ms=2100.0, cls=0.05,
    )))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    v = res.value
    assert v.grade == "good"
    assert v.lcp_s == 2.1
    assert v.cls == 0.05
    assert v.tbt_ms == 150.0
    # 4 categories parsed
    assert len(v.categories) == 4
    cats = {c.category: c.score for c in v.categories}
    assert cats["performance"] == 85.0
    assert cats["accessibility"] == 95.0


@pytest.mark.asyncio
async def test_web_vitals_parsed(tmp_path: Path):
    _write(tmp_path / "lh.json", json.dumps(_lh_report()))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    metrics = {wv.metric for wv in res.value.web_vitals}
    assert "LCP" in metrics
    assert "CLS" in metrics
    assert "TBT" in metrics
    assert "FCP" in metrics


# ---- grading thresholds ------------------------------------------------


@pytest.mark.asyncio
async def test_poor_lcp_blocks(tmp_path: Path):
    """LCP >= 4.0s is in the poor band → blocked."""
    _write(tmp_path / "lh.json", json.dumps(_lh_report(lcp_ms=4500.0)))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    assert res.value.grade == "blocked"
    assert "STOP" in res.value.advice


@pytest.mark.asyncio
async def test_poor_cls_blocks(tmp_path: Path):
    """CLS >= 0.25 is in the poor band → blocked."""
    _write(tmp_path / "lh.json", json.dumps(_lh_report(cls=0.3)))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    assert res.value.grade == "blocked"


@pytest.mark.asyncio
async def test_low_accessibility_blocks(tmp_path: Path):
    """a11y < 50 is a release gate → blocked."""
    _write(tmp_path / "lh.json", json.dumps(_lh_report(a11y=0.40)))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    assert res.value.grade == "blocked"


@pytest.mark.asyncio
async def test_middle_lcp_needs_improvement(tmp_path: Path):
    """LCP between 2.5 and 4.0 → needs_improvement (not blocked)."""
    _write(tmp_path / "lh.json", json.dumps(_lh_report(
        lcp_ms=3200.0, cls=0.05, a11y=0.95, perf=0.75,
    )))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    assert res.value.grade == "needs_improvement"


@pytest.mark.asyncio
async def test_canvaskit_perf_threshold_is_lenient(tmp_path: Path):
    """A perf score of 72 with good CWV should be 'good' under the
    default CanvasKit-aware threshold of 70 — NOT penalised for
    being under Lighthouse's own 90 boundary."""
    _write(tmp_path / "lh.json", json.dumps(_lh_report(
        perf=0.72, a11y=0.95, lcp_ms=2200.0, cls=0.05,
    )))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    assert res.value.grade == "good"


@pytest.mark.asyncio
async def test_perf_threshold_override(tmp_path: Path):
    """Raising the threshold (HTML/wasm renderer) makes a 72 perf
    score 'needs_improvement'."""
    _write(tmp_path / "lh.json", json.dumps(_lh_report(
        perf=0.72, a11y=0.95, lcp_ms=2200.0, cls=0.05,
    )))
    res = await _run(
        report_path=tmp_path / "lh.json",
        perf_good_threshold=90.0,
    )
    assert isinstance(res, Ok)
    assert res.value.grade == "needs_improvement"


# ---- opportunities -----------------------------------------------------


@pytest.mark.asyncio
async def test_opportunities_parsed_and_sorted(tmp_path: Path):
    _write(tmp_path / "lh.json", json.dumps(_lh_report(
        opportunities=[
            ("Eliminate render-blocking resources", 450),
            ("Properly size images", 1200),
            ("Reduce unused JavaScript", 300),
        ],
    )))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    opps = res.value.top_opportunities
    assert len(opps) == 3
    # Sorted by savings desc — biggest first
    assert "Properly size images" in opps[0]
    assert "1200ms" in opps[0]


@pytest.mark.asyncio
async def test_opportunities_capped_at_5(tmp_path: Path):
    _write(tmp_path / "lh.json", json.dumps(_lh_report(
        opportunities=[(f"Opp {i}", (i + 1) * 100) for i in range(10)],
    )))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    assert len(res.value.top_opportunities) == 5


# ---- aggregates --------------------------------------------------------


@pytest.mark.asyncio
async def test_overall_score_is_category_mean(tmp_path: Path):
    _write(tmp_path / "lh.json", json.dumps(_lh_report(
        perf=0.80, a11y=1.00, seo=0.90,  # + best-practices 0.93
    )))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    # mean of [80, 100, 93, 90] = 90.75
    assert res.value.overall_score == pytest.approx(90.75, abs=0.5)


@pytest.mark.asyncio
async def test_pwa_category_optional(tmp_path: Path):
    """A report without a pwa category still parses the other 4."""
    report = _lh_report()
    assert "pwa" not in report["categories"]
    _write(tmp_path / "lh.json", json.dumps(report))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    cats = {c.category for c in res.value.categories}
    assert "pwa" not in cats
    assert "performance" in cats


@pytest.mark.asyncio
async def test_advice_mentions_grade_and_cwv(tmp_path: Path):
    _write(tmp_path / "lh.json", json.dumps(_lh_report()))
    res = await _run(report_path=tmp_path / "lh.json")
    assert isinstance(res, Ok)
    assert res.value.grade in res.value.advice
    assert "LCP" in res.value.advice
