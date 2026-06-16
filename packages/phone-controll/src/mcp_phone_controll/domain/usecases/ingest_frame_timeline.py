"""Ingest a captured frame timeline — grade animation/scroll smoothness.

The runtime complement to `audit_performance` (static): that flags
jank-prone *patterns*; this measures *actual* frames. You capture the
timeline (mobile: `start/stop_frame_profile` = Flutter VM Timeline; web:
Chrome DevTools MCP `performance_start/stop_trace`); we grade it into a
jank score. Pure compute, stdlib JSON only.

Accepted inputs (auto-detected):
  1. **Trace Event Format** — `{"traceEvents": [...]}` (both Flutter's
     VM Timeline export and Chrome DevTools traces use this). We extract
     Flutter "Frame" complete events (dur in µs); if there are none
     (e.g. a web trace), we fall back to top-level long tasks
     (RunTask ≥ frame budget) as the jank proxy.
  2. **Pre-extracted frames** — `{"frames_ms": [16.2, 33.1, ...]}` or
     `{"frames": [{"build_ms": .., "raster_ms": ..}, ...]}`.

Metrics: frame count, janky count (> budget), % janky, worst frame,
p50/p90/p99, and build-vs-raster split when available. Budget = 1000/fps
(default 60 → 16.7ms; pass fps=120 for ProMotion).
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
    SMOOTH = "smooth"
    ACCEPTABLE = "acceptable"
    JANKY = "janky"
    SEVERE = "severe"


@dataclass(frozen=True, slots=True)
class IngestFrameTimelineParams:
    timeline_path: Path
    fps: int = 60                  # target; budget = 1000/fps ms
    # A frame this many times over budget counts as a "severe" frame.
    severe_factor: float = 2.0


@dataclass(frozen=True, slots=True)
class IngestFrameTimelineResult:
    grade: str
    source: str                    # "frames" / "trace_frames" / "trace_tasks"
    fps_target: int
    budget_ms: float
    frame_count: int
    janky_count: int               # frames > budget
    janky_pct: float
    severe_count: int              # frames > budget * severe_factor
    worst_ms: float
    p50_ms: float
    p90_ms: float
    p99_ms: float
    avg_build_ms: float | None     # if build/raster split available
    avg_raster_ms: float | None
    advice: str


# Flutter VM Timeline frame events. Chrome traces don't emit these →
# we fall back to long tasks.
_FRAME_NAMES = frozenset({"Frame", "PipelineItem"})
_TASK_NAMES = ("RunTask", "ThreadControllerImpl::RunTask",
               "MessageLoop::RunTask", "Task")


class IngestFrameTimeline(
    BaseUseCase[IngestFrameTimelineParams, IngestFrameTimelineResult]
):
    """Grade a captured frame timeline into a jank score. Pure compute."""

    async def execute(
        self, params: IngestFrameTimelineParams
    ) -> Result[IngestFrameTimelineResult]:
        f = _resolve(params.timeline_path)
        if f is None or not f.is_file():
            return err(FilesystemFailure(
                message=(
                    f"frame timeline not found at {params.timeline_path}. "
                    "Capture via start/stop_frame_profile (mobile) or a "
                    "Chrome DevTools performance trace (web)."
                ),
                next_action="fix_arguments",
            ))
        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError) as e:
            return err(FilesystemFailure(
                message=f"malformed timeline JSON: {e}", next_action="fix_arguments",
            ))

        fps = params.fps if params.fps > 0 else 60
        budget = 1000.0 / fps

        frames_ms, builds, rasters, source = _extract(data, budget)
        if not frames_ms:
            return err(FilesystemFailure(
                message=(
                    "No frames or tasks found in the timeline. Expected a "
                    "Trace Event Format file (traceEvents) or a frames_ms list."
                ),
                next_action="fix_arguments",
            ))

        frames_ms.sort()
        n = len(frames_ms)
        janky = sum(1 for x in frames_ms if x > budget)
        severe = sum(1 for x in frames_ms if x > budget * params.severe_factor)
        janky_pct = round(100.0 * janky / n, 1)
        grade = _grade(janky_pct, severe, n)

        return ok(IngestFrameTimelineResult(
            grade=grade,
            source=source,
            fps_target=fps,
            budget_ms=round(budget, 2),
            frame_count=n,
            janky_count=janky,
            janky_pct=janky_pct,
            severe_count=severe,
            worst_ms=round(max(frames_ms), 1),
            p50_ms=_pct(frames_ms, 50),
            p90_ms=_pct(frames_ms, 90),
            p99_ms=_pct(frames_ms, 99),
            avg_build_ms=round(sum(builds) / len(builds), 1) if builds else None,
            avg_raster_ms=round(sum(rasters) / len(rasters), 1) if rasters else None,
            advice=_advice(grade, janky, n, janky_pct, max(frames_ms), budget, source),
        ))


# ============================================================
# Extraction
# ============================================================


def _resolve(path: Path) -> Path | None:
    if path.is_file():
        return path
    if path.is_dir():
        for pat in ("*.json", "*.trace"):
            for f in sorted(path.glob(pat)):
                return f
    return None


def _extract(data, budget: float):
    """Returns (frames_ms, build_ms_list, raster_ms_list, source)."""
    # Mode: pre-extracted frames_ms
    if isinstance(data, dict) and isinstance(data.get("frames_ms"), list):
        fm = [float(x) for x in data["frames_ms"] if isinstance(x, (int, float))]
        return fm, [], [], "frames"

    # Mode: pre-extracted frames with build/raster
    if isinstance(data, dict) and isinstance(data.get("frames"), list):
        fm, builds, rasters = [], [], []
        for fr in data["frames"]:
            if not isinstance(fr, dict):
                continue
            b = fr.get("build_ms")
            r = fr.get("raster_ms")
            b = float(b) if isinstance(b, (int, float)) else 0.0
            r = float(r) if isinstance(r, (int, float)) else 0.0
            if b or r:
                builds.append(b)
                rasters.append(r)
                fm.append(b + r)
            elif isinstance(fr.get("total_ms"), (int, float)):
                fm.append(float(fr["total_ms"]))
        return fm, builds, rasters, "frames"

    # Mode: Trace Event Format
    events = data.get("traceEvents") if isinstance(data, dict) else None
    if isinstance(events, list):
        # Prefer Flutter "Frame" complete events (dur in µs)
        frame_ms = [
            float(e["dur"]) / 1000.0
            for e in events
            if isinstance(e, dict)
            and e.get("ph") == "X"
            and e.get("name") in _FRAME_NAMES
            and isinstance(e.get("dur"), (int, float))
        ]
        if frame_ms:
            return frame_ms, [], [], "trace_frames"
        # Fallback: top-level tasks (web jank proxy)
        tasks_ms = [
            float(e["dur"]) / 1000.0
            for e in events
            if isinstance(e, dict)
            and e.get("ph") == "X"
            and isinstance(e.get("dur"), (int, float))
            and (
                e.get("name") in _TASK_NAMES
                or "toplevel" in str(e.get("cat", ""))
            )
        ]
        return tasks_ms, [], [], "trace_tasks"

    return [], [], [], "unknown"


def _pct(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1,
                   int(round(pct / 100.0 * len(sorted_vals) + 0.5)) - 1))
    return round(sorted_vals[k], 1)


def _grade(janky_pct: float, severe: int, n: int) -> str:
    severe_pct = 100.0 * severe / n if n else 0.0
    if janky_pct >= 30 or severe_pct >= 10:
        return "severe"
    if janky_pct >= 15:
        return "janky"
    if janky_pct >= 5:
        return "acceptable"
    return "smooth"


def _advice(grade, janky, n, janky_pct, worst, budget, source) -> str:
    label = {
        "trace_tasks": "long tasks (web; no Flutter frame events — jank proxy)",
        "trace_frames": "frames (Flutter VM Timeline)",
        "frames": "frames",
    }.get(source, source)
    tail = {
        "severe": " STOP — heavy jank; profile the worst frames.",
        "janky": " Noticeable jank — investigate build/raster on the slow frames.",
        "acceptable": " Mostly smooth; a few dropped frames.",
        "smooth": " Smooth — within frame budget.",
    }.get(grade, "")
    return (
        f"Frame grade: {grade}. {janky}/{n} {label} over "
        f"{budget:.1f}ms budget ({janky_pct:.0f}%), worst {worst:.0f}ms.{tail}"
    )
