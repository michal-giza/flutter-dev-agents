"""Ingest a HAR (HTTP Archive) export — per-action network cost.

The "reads-per-action" telemetry the field reports asked for. A browser
MCP (Chrome DevTools MCP / Playwright / Claude-in-Chrome) captures the
Network panel as a HAR; this parses it into a graded report: per-host
request counts, reads vs writes, latency percentiles, payload bytes,
errors, and the slowest calls — with one **backend host** highlighted
(e.g. firestore.googleapis.com, or a REST API like `*.hf.space`).

Same posture as `ingest_lighthouse_report` / `ingest_maestro_report`:
you capture, we grade. Pure compute, stdlib JSON only — no network.

Validated by the bike_news_room run: completing onboarding fired
`/api/live-ticker` + `/api/feeds` + `/api/trending`; this turns that
Network-panel observation into a repeatable, attributable cost report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from .base import BaseUseCase

_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Hosts that are almost always static/CDN/telemetry — not the app's
# data backend. Used to auto-pick the backend host when not given.
_STATIC_HOST_HINTS = (
    "gstatic.com", "googleapis.com/fonts", "fonts.googleapis.com",
    "fonts.gstatic.com", "google-analytics.com", "googletagmanager.com",
    "cdn.jsdelivr.net", "unpkg.com", "cloudflare.com",
)


class Grade(str, Enum):
    GOOD = "good"
    NEEDS_IMPROVEMENT = "needs_improvement"
    POOR = "poor"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class HostStat:
    host: str
    requests: int
    reads: int                # GET/HEAD/OPTIONS
    writes: int               # POST/PUT/PATCH/DELETE
    error_count: int          # status >= 400
    server_errors: int        # status >= 500
    total_bytes: int          # response payload (content size)
    total_time_ms: float
    p50_ms: float
    p95_ms: float
    slowest_ms: float


@dataclass(frozen=True, slots=True)
class IngestHarParams:
    har_path: Path
    # Highlight this backend host (substring match). None → auto-pick the
    # busiest non-static/CDN host.
    backend_host: str | None = None
    # A backend call slower than this is "slow" (for the slowest list).
    slow_ms: float = 1000.0


@dataclass(frozen=True, slots=True)
class IngestHarResult:
    grade: str
    total_requests: int
    total_bytes: int
    total_time_ms: float
    error_count: int
    hosts: tuple[HostStat, ...]            # all hosts, busiest first
    backend_host: str | None
    backend: HostStat | None              # the highlighted host's stat
    slowest: tuple[str, ...]              # "METHOD url — Nms (status)"
    advice: str


class IngestHar(BaseUseCase[IngestHarParams, IngestHarResult]):
    """Parse a HAR export into a per-host / per-action network-cost
    report with a backend-host focus. Pure compute."""

    async def execute(self, params: IngestHarParams) -> Result[IngestHarResult]:
        har_file = _resolve_har(params.har_path)
        if har_file is None or not har_file.is_file():
            return err(FilesystemFailure(
                message=(
                    f"HAR not found at {params.har_path}. Export one from the "
                    "browser Network panel (or a browser MCP) as .har."
                ),
                next_action="fix_arguments",
            ))
        try:
            data = json.loads(har_file.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError) as e:
            return err(FilesystemFailure(
                message=f"malformed HAR JSON: {e}", next_action="fix_arguments",
            ))

        entries = (((data or {}).get("log") or {}).get("entries"))
        if not isinstance(entries, list):
            return err(FilesystemFailure(
                message="Not a HAR file (no log.entries). Export as HAR 1.2.",
                next_action="fix_arguments",
            ))

        agg = _aggregate(entries)
        hosts = tuple(sorted(
            (_finish_host(h, rows) for h, rows in agg.items()),
            key=lambda s: -s.requests,
        ))
        total_requests = sum(h.requests for h in hosts)
        total_bytes = sum(h.total_bytes for h in hosts)
        total_time = sum(h.total_time_ms for h in hosts)
        error_count = sum(h.error_count for h in hosts)

        backend_host = _pick_backend(hosts, params.backend_host)
        backend = next((h for h in hosts if h.host == backend_host), None)

        slowest = _slowest(entries)
        grade = _grade(backend, error_count)

        return ok(IngestHarResult(
            grade=grade,
            total_requests=total_requests,
            total_bytes=total_bytes,
            total_time_ms=round(total_time, 1),
            error_count=error_count,
            hosts=hosts,
            backend_host=backend_host,
            backend=backend,
            slowest=slowest,
            advice=_advice(grade, backend, total_requests, error_count),
        ))


# ============================================================
# Parsing
# ============================================================


def _resolve_har(path: Path) -> Path | None:
    if path.is_file():
        return path
    if path.is_dir():
        for f in sorted(path.glob("*.har")):
            return f
    return None


def _host_of(url: str) -> str:
    # Cheap host extraction without urllib overhead/edge cases.
    s = url.split("://", 1)[-1]
    return s.split("/", 1)[0].split("?", 1)[0] or "(unknown)"


def _aggregate(entries: list) -> dict[str, list[tuple[str, int, int, float]]]:
    """host -> list of (method, status, content_bytes, time_ms)."""
    out: dict[str, list[tuple[str, int, int, float]]] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        req = e.get("request") or {}
        resp = e.get("response") or {}
        url = str(req.get("url", ""))
        if not url:
            continue
        method = str(req.get("method", "GET")).upper()
        status = int(resp.get("status", 0) or 0)
        content = resp.get("content") or {}
        size = content.get("size")
        if not isinstance(size, (int, float)) or size < 0:
            bs = resp.get("bodySize", 0)
            size = bs if isinstance(bs, (int, float)) and bs > 0 else 0
        time_ms = e.get("time")
        time_ms = float(time_ms) if isinstance(time_ms, (int, float)) and time_ms >= 0 else 0.0
        out.setdefault(_host_of(url), []).append(
            (method, status, int(size), time_ms)
        )
    return out


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    # nearest-rank
    k = max(0, min(len(s) - 1, int(round(pct / 100.0 * len(s) + 0.5)) - 1))
    return round(s[k], 1)


def _finish_host(host: str, rows: list[tuple[str, int, int, float]]) -> HostStat:
    times = [t for _, _, _, t in rows]
    reads = sum(1 for m, _, _, _ in rows if m in _READ_METHODS)
    return HostStat(
        host=host,
        requests=len(rows),
        reads=reads,
        writes=len(rows) - reads,
        error_count=sum(1 for _, st, _, _ in rows if st >= 400),
        server_errors=sum(1 for _, st, _, _ in rows if st >= 500),
        total_bytes=sum(b for _, _, b, _ in rows),
        total_time_ms=round(sum(times), 1),
        p50_ms=_percentile(times, 50),
        p95_ms=_percentile(times, 95),
        slowest_ms=round(max(times), 1) if times else 0.0,
    )


def _pick_backend(hosts: tuple[HostStat, ...], explicit: str | None) -> str | None:
    if explicit:
        for h in hosts:
            if explicit in h.host:
                return h.host
        return explicit  # not seen, but report it so the caller knows
    # Auto: busiest host that isn't an obvious static/CDN/local origin.
    for h in hosts:  # already sorted busiest-first
        low = h.host.lower()
        if any(hint in low for hint in _STATIC_HOST_HINTS):
            continue
        if low.startswith(("localhost", "127.0.0.1", "0.0.0.0")):
            continue
        return h.host
    return hosts[0].host if hosts else None


def _slowest(entries: list, limit: int = 5) -> tuple[str, ...]:
    rows: list[tuple[float, str]] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        req = e.get("request") or {}
        resp = e.get("response") or {}
        t = e.get("time")
        if not isinstance(t, (int, float)):
            continue
        url = str(req.get("url", ""))[:120]
        method = str(req.get("method", "GET")).upper()
        status = int(resp.get("status", 0) or 0)
        rows.append((float(t), f"{method} {url} — {t:.0f}ms ({status})"))
    rows.sort(key=lambda x: -x[0])
    return tuple(r for _, r in rows[:limit])


# ============================================================
# Grading
# ============================================================


def _grade(backend: HostStat | None, total_errors: int) -> str:
    if backend is None:
        return "good"
    # blocked — the backend returned a server (5xx) error in this capture.
    if backend.server_errors > 0:
        return "blocked"
    # poor — very chatty or slow backend.
    if backend.reads > 50 or backend.p95_ms >= 2000:
        return "poor"
    # needs_improvement — moderately chatty/slow, or any 4xx.
    if backend.reads > 15 or backend.p95_ms >= 800 or backend.error_count > 0:
        return "needs_improvement"
    return "good"


def _advice(grade: str, backend: HostStat | None, total: int, errors: int) -> str:
    if backend is None:
        return f"HAR parsed: {total} requests, no backend host identified."
    tail = {
        "blocked": " STOP — backend errors in this capture.",
        "poor": " Backend is chatty/slow — batch reads or add caching.",
        "needs_improvement": " Trim backend reads / tighten latency where you can.",
        "good": " Backend cost looks reasonable for this action.",
    }.get(grade, "")
    return (
        f"HAR grade: {grade}. Backend {backend.host}: {backend.reads} reads / "
        f"{backend.writes} writes, p95 {backend.p95_ms:.0f}ms, "
        f"{backend.total_bytes} bytes. {total} total requests, "
        f"{errors} errors.{tail}"
    )
