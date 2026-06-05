"""Ingest Lighthouse reports for Flutter web apps.

Lighthouse (Google's web-quality auditor) emits a JSON report
(`lighthouse <url> --output=json --output-path=report.json`).
This use case parses it, surfaces the 4 category scores +
Core Web Vitals + the top opportunities, and grades the result
so it can feed into `audit_release_readiness` as a web_vitals
domain (phase 16.5).

Same composition posture as `ingest_maestro_report`: we don't
run Lighthouse (the user / CI does), we parse its output. The
agent then knows what to fix first.

Flutter web specifics encoded:
  • The CanvasKit renderer ships a ~1.5MB wasm payload, so a
    "perfect" Lighthouse perf score is rare. Our grade
    thresholds are tuned to that reality — a perf score of 70
    is GOOD for a CanvasKit app, not a failure.
  • We surface LCP (Largest Contentful Paint) prominently
    because the white-screen-of-load is the #1 Flutter-web UX
    complaint (paired with audit_web_app's no_loading_indicator
    rule).

What this is NOT:
  • Not a Lighthouse runner — invoke lighthouse CLI / PageSpeed
    for that.
  • Not a synthetic-monitoring service — you bring one report;
    we parse it. For trends, run repeatedly + diff.

Pure compute. Stdlib JSON only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from .base import BaseUseCase


class Grade(str, Enum):
    GOOD = "good"
    NEEDS_IMPROVEMENT = "needs_improvement"
    POOR = "poor"


@dataclass(frozen=True, slots=True)
class CategoryScore:
    category: str            # performance / accessibility / best-practices / seo / pwa
    score: float             # 0-100
    grade: str               # good / needs_improvement / poor


@dataclass(frozen=True, slots=True)
class WebVital:
    metric: str              # LCP / FID / CLS / TBT / FCP / SI / TTI
    display_value: str       # "2.3 s", "0.05"
    numeric_value: float     # raw value (ms for time metrics)
    score: float             # 0-100 (Lighthouse audit score * 100)
    grade: str               # good / needs_improvement / poor


@dataclass(frozen=True, slots=True)
class IngestLighthouseReportParams:
    report_path: Path
    # For CanvasKit Flutter web, a perf score of 70 is healthy.
    # Override the perf-good threshold if you ship the HTML / wasm
    # renderer (which scores higher).
    perf_good_threshold: float = 70.0


@dataclass(frozen=True, slots=True)
class IngestLighthouseReportResult:
    grade: str                              # good / needs_improvement / poor / blocked
    overall_score: float                    # mean of category scores
    fetched_url: str | None
    categories: tuple[CategoryScore, ...]
    web_vitals: tuple[WebVital, ...]
    lcp_s: float | None                     # Largest Contentful Paint, seconds
    cls: float | None                       # Cumulative Layout Shift
    tbt_ms: float | None                    # Total Blocking Time, ms
    top_opportunities: tuple[str, ...]      # paste-ready "title — savings"
    advice: str


# Core Web Vitals thresholds (Google's official boundaries)
_LCP_GOOD_S = 2.5
_LCP_POOR_S = 4.0
_CLS_GOOD = 0.1
_CLS_POOR = 0.25
_TBT_GOOD_MS = 200.0
_TBT_POOR_MS = 600.0


class IngestLighthouseReport(
    BaseUseCase[IngestLighthouseReportParams, IngestLighthouseReportResult]
):
    """Parse a Lighthouse JSON report, surface scores + Core Web
    Vitals + top opportunities.

    Pure compute. Stdlib JSON only.
    """

    async def execute(
        self, params: IngestLighthouseReportParams
    ) -> Result[IngestLighthouseReportResult]:
        report_file = _resolve_report_file(params.report_path)
        if report_file is None or not report_file.is_file():
            return err(FilesystemFailure(
                message=(
                    f"Lighthouse report not found at {params.report_path}. "
                    "Generate one with `lighthouse <url> --output=json "
                    "--output-path=report.json`."
                ),
                next_action="fix_arguments",
            ))

        try:
            data = json.loads(
                report_file.read_text(encoding="utf-8", errors="replace")
            )
        except (json.JSONDecodeError, OSError) as e:
            return err(FilesystemFailure(
                message=f"malformed Lighthouse JSON: {e}",
                next_action="fix_arguments",
            ))

        if not isinstance(data, dict) or "categories" not in data:
            return err(FilesystemFailure(
                message=(
                    "Not a Lighthouse report (no 'categories' key). "
                    "Pass the JSON output of `lighthouse --output=json`."
                ),
                next_action="fix_arguments",
            ))

        fetched_url = data.get("finalUrl") or data.get("requestedUrl")
        categories = _parse_categories(data.get("categories", {}))
        audits = data.get("audits", {})
        web_vitals = _parse_web_vitals(audits)
        top_opportunities = _parse_opportunities(audits)

        # Pull the headline Core Web Vitals as typed numbers
        lcp_s = _numeric_seconds(audits.get("largest-contentful-paint"))
        cls = _numeric_raw(audits.get("cumulative-layout-shift"))
        tbt_ms = _numeric_ms(audits.get("total-blocking-time"))

        # Overall = mean of category scores
        overall = (
            sum(c.score for c in categories) / len(categories)
            if categories else 0.0
        )

        grade = _overall_grade(
            categories, lcp_s, cls, params.perf_good_threshold,
        )

        return ok(IngestLighthouseReportResult(
            grade=grade,
            overall_score=round(overall, 1),
            fetched_url=fetched_url,
            categories=categories,
            web_vitals=web_vitals,
            lcp_s=lcp_s,
            cls=cls,
            tbt_ms=tbt_ms,
            top_opportunities=top_opportunities,
            advice=_build_advice(
                grade, overall, categories, lcp_s, cls,
                params.perf_good_threshold,
            ),
        ))


# ============================================================
# File resolution
# ============================================================


def _resolve_report_file(path: Path) -> Path | None:
    if path.is_file():
        return path
    if path.is_dir():
        for candidate in (
            "lighthouse.json", "report.json", "lhr.json",
            "lighthouse-report.json",
        ):
            f = path / candidate
            if f.is_file():
                return f
        for f in sorted(path.glob("*.json")):
            return f
    return None


# ============================================================
# Parsers
# ============================================================


def _parse_categories(cats: dict) -> tuple[CategoryScore, ...]:
    out: list[CategoryScore] = []
    # Lighthouse keys: performance, accessibility, best-practices, seo, pwa
    for key in (
        "performance", "accessibility", "best-practices", "seo", "pwa",
    ):
        cat = cats.get(key)
        if not isinstance(cat, dict):
            continue
        raw = cat.get("score")
        if raw is None:
            continue  # category not run (e.g. pwa skipped)
        score = float(raw) * 100.0
        out.append(CategoryScore(
            category=key,
            score=round(score, 1),
            grade=_score_grade(score).value,
        ))
    return tuple(out)


# Lighthouse audit ids → friendly Web Vital names
_VITAL_AUDITS = {
    "largest-contentful-paint": "LCP",
    "cumulative-layout-shift": "CLS",
    "total-blocking-time": "TBT",
    "first-contentful-paint": "FCP",
    "speed-index": "SI",
    "interactive": "TTI",
    "max-potential-fid": "FID",
}


def _parse_web_vitals(audits: dict) -> tuple[WebVital, ...]:
    out: list[WebVital] = []
    for audit_id, name in _VITAL_AUDITS.items():
        a = audits.get(audit_id)
        if not isinstance(a, dict):
            continue
        numeric = a.get("numericValue")
        score = a.get("score")
        if numeric is None:
            continue
        score_pct = float(score) * 100.0 if score is not None else 0.0
        out.append(WebVital(
            metric=name,
            display_value=str(a.get("displayValue", "")),
            numeric_value=float(numeric),
            score=round(score_pct, 1),
            grade=_score_grade(score_pct).value,
        ))
    return tuple(out)


def _parse_opportunities(audits: dict) -> tuple[str, ...]:
    """Lighthouse 'opportunities' are audits with a numeric
    `overallSavingsMs` in their details. Pick the top 5 by
    savings."""
    opps: list[tuple[float, str]] = []
    for a in audits.values():
        if not isinstance(a, dict):
            continue
        details = a.get("details")
        if not isinstance(details, dict):
            continue
        savings = details.get("overallSavingsMs")
        # Only include if it's a real opportunity (score < 1 and
        # has savings).
        score = a.get("score")
        if savings and isinstance(savings, (int, float)) and savings > 0:
            if score is not None and score >= 1.0:
                continue  # already passing
            title = a.get("title", "(untitled)")
            opps.append((float(savings), f"{title} — ~{int(savings)}ms"))
    opps.sort(key=lambda x: -x[0])
    return tuple(o[1] for o in opps[:5])


def _numeric_seconds(audit: dict | None) -> float | None:
    if not isinstance(audit, dict):
        return None
    v = audit.get("numericValue")
    return round(float(v) / 1000.0, 2) if v is not None else None


def _numeric_ms(audit: dict | None) -> float | None:
    if not isinstance(audit, dict):
        return None
    v = audit.get("numericValue")
    return round(float(v), 1) if v is not None else None


def _numeric_raw(audit: dict | None) -> float | None:
    if not isinstance(audit, dict):
        return None
    v = audit.get("numericValue")
    return round(float(v), 3) if v is not None else None


# ============================================================
# Grading
# ============================================================


def _score_grade(score: float) -> Grade:
    # Lighthouse's own colour boundaries: >=90 good, 50-89 needs
    # improvement, <50 poor.
    if score >= 90:
        return Grade.GOOD
    if score >= 50:
        return Grade.NEEDS_IMPROVEMENT
    return Grade.POOR


def _overall_grade(
    categories: tuple[CategoryScore, ...],
    lcp_s: float | None,
    cls: float | None,
    perf_good_threshold: float,
) -> str:
    # "blocked" — a Core Web Vital is in the POOR band, OR
    # accessibility is poor (a11y is a release gate for us).
    if lcp_s is not None and lcp_s >= _LCP_POOR_S:
        return "blocked"
    if cls is not None and cls >= _CLS_POOR:
        return "blocked"
    a11y = next(
        (c for c in categories if c.category == "accessibility"), None
    )
    if a11y is not None and a11y.score < 50:
        return "blocked"

    perf = next(
        (c for c in categories if c.category == "performance"), None
    )
    # Perf gate uses the CanvasKit-aware threshold
    if perf is not None and perf.score < perf_good_threshold - 20:
        return "poor"

    # needs_improvement if any Core Web Vital is in the middle band
    if lcp_s is not None and lcp_s >= _LCP_GOOD_S:
        return "needs_improvement"
    if cls is not None and cls >= _CLS_GOOD:
        return "needs_improvement"
    if perf is not None and perf.score < perf_good_threshold:
        return "needs_improvement"

    return "good"


def _build_advice(
    grade: str,
    overall: float,
    categories: tuple[CategoryScore, ...],
    lcp_s: float | None,
    cls: float | None,
    perf_good_threshold: float,
) -> str:
    cat_str = " · ".join(
        f"{c.category}={c.score:.0f}" for c in categories
    )
    vitals = []
    if lcp_s is not None:
        vitals.append(f"LCP {lcp_s:.1f}s")
    if cls is not None:
        vitals.append(f"CLS {cls:.2f}")
    vitals_str = ", ".join(vitals) if vitals else "no CWV data"

    tail = ""
    if grade == "blocked":
        tail = " STOP — a Core Web Vital is in the poor band (or a11y < 50)."
    elif grade == "needs_improvement":
        tail = (
            " Tighten the slow metric. Note: CanvasKit Flutter web rarely "
            f"scores >{perf_good_threshold:.0f} on perf — that's expected."
        )

    return (
        f"Lighthouse grade: {grade} (overall {overall:.0f}/100). "
        f"[{cat_str}]. {vitals_str}.{tail}"
    )
