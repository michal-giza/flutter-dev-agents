"""Frame jank detection — the #1 user-perceived quality signal.

Flutter renders at 60 fps (16.67 ms/frame) or 120 fps (8.33 ms) on
high-refresh-rate devices. When a frame's build + raster work
exceeds that budget, the user sees jank — a hitch in animation, a
stutter while scrolling, a delay before a tap visibly registers.

Static analysis can't catch this. Unit tests don't catch it.
Visual diffs don't catch it. The only way to know is to drive the
app and measure frame timing while it's running.

This module gives an agent a bracket-pattern API for that:

  start_frame_profile()                ← enable VM Timeline collection
  # agent drives the suspect interaction:
  tap_text("Open big list")
  swipe(...)  # scroll
  tap_text("Close")
  stop_frame_profile()                 ← disable + analyze + return

The returned report includes:

  • Total frames captured.
  • Janked frames (duration > target_fps budget + tolerance).
  • P50 / P90 / P99 / max frame times.
  • Worst-3 individual frames with their build/raster split.
  • Plain-English advice line for PR comments.

Why bracket pattern and not duration-based:

`profile_frames(duration_s=10)` would force the agent to predict
how long the UI work takes. The bracket pattern matches what the
agent actually knows: "I'm about to run this specific
interaction." Same shape as the memory-leak workflow.

Implementation:

- `start` calls `setVMTimelineFlags(['Dart', 'Embedder', 'GC'])`
  on the VM service. This enables the embedder-level frame events
  (the ones tagged 'Frame' / 'vsync callback' / 'Animator::BeginFrame').
- `stop` calls `getVMTimeline` for the captured window, parses the
  trace events, identifies frame boundaries, and computes the
  per-frame timing stats. Then `setVMTimelineFlags([])` to stop
  collection (don't leave it on — it has measurable overhead).

The Chrome-trace-format JSON the VM service returns is the same
format DevTools' Performance tab consumes. We don't try to
replicate the full DevTools analysis — just the jank-detection
slice that an agent actually needs to decide "ship or fix."
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from statistics import median
from typing import Any

from ..failures import DebugSessionFailure
from ..repositories import DebugSessionRepository
from ..result import Err, Result, err, ok
from .base import BaseUseCase

# Timeline streams to enable. 'Embedder' is the one with frame
# events; 'Dart' adds language-level events (for analyzing build
# phase); 'GC' lets us correlate jank with garbage-collection
# pauses. 'Compiler' and 'Isolate' are noisy; we skip them.
_TIMELINE_STREAMS = ("Embedder", "Dart", "GC")

# Default tolerance — anything within this many percent of the
# budget is "fine." 10% means a 17.6ms frame at 60fps is not janked.
# Matches the convention DevTools uses.
_DEFAULT_TOLERANCE_PCT = 0.10


# ---------------- start_frame_profile -----------------------------------


@dataclass(frozen=True, slots=True)
class StartFrameProfileParams:
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class StartFrameProfileResult:
    isolate_id: str
    started_at_micros: int          # `getVMTimelineMicros` baseline
    streams_enabled: tuple[str, ...]


class StartFrameProfile(
    BaseUseCase[StartFrameProfileParams, StartFrameProfileResult]
):
    """Open the bracket — enable Timeline collection.

    The Timeline buffer is bounded; if collection runs > ~30s of
    busy frames it wraps and you lose the oldest events. For
    typical use (drive an interaction, stop within 5-15s) this is
    fine.
    """

    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(
        self, params: StartFrameProfileParams
    ) -> Result[StartFrameProfileResult]:
        session_res = await _resolve_session(self._repo, params.session_id)
        if isinstance(session_res, Err):
            return session_res
        target = session_res.value
        return await _with_vm(target.vm_service_uri, _start)


# ---------------- stop_frame_profile ------------------------------------


@dataclass(frozen=True, slots=True)
class StopFrameProfileParams:
    session_id: str | None = None
    # Target frame rate the agent wants the app to hit. Tools call
    # this "target_fps" but the budget per frame is what we compare
    # against — 60 → 16.67ms, 120 → 8.33ms.
    target_fps: int = 60
    # Frames within tolerance_pct of the budget are NOT counted as
    # jank. 10% by default matches DevTools convention.
    tolerance_pct: float = _DEFAULT_TOLERANCE_PCT


@dataclass(frozen=True, slots=True)
class FrameTiming:
    start_micros: int
    duration_micros: int
    build_micros: int               # 0 if not available
    raster_micros: int              # 0 if not available
    is_janked: bool


@dataclass(frozen=True, slots=True)
class StopFrameProfileResult:
    target_fps: int
    budget_micros: int              # = 1_000_000 / target_fps
    total_frames: int
    janked_frames: int
    jank_pct: float                 # 0.0-1.0
    p50_micros: int
    p90_micros: int
    p99_micros: int
    max_micros: int
    worst_frames: tuple[FrameTiming, ...]   # top 3
    advice: str                     # paste-ready PR-comment line


class StopFrameProfile(
    BaseUseCase[StopFrameProfileParams, StopFrameProfileResult]
):
    """Close the bracket — disable, analyze, return.

    Heavy-handed by design: ALWAYS disables Timeline streams on
    exit, even if analysis fails. Leaving Timeline running has
    real overhead (~5-10% CPU per stream) so we never leak the
    enabled state across sessions.

    Returns a jank summary the agent can paste directly into a
    PR comment. The `advice` line is the one-sentence verdict;
    `worst_frames` lets you point at the specific offenders.
    """

    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(
        self, params: StopFrameProfileParams
    ) -> Result[StopFrameProfileResult]:
        session_res = await _resolve_session(self._repo, params.session_id)
        if isinstance(session_res, Err):
            return session_res
        target = session_res.value
        return await _with_vm(
            target.vm_service_uri,
            _stop,
            target_fps=params.target_fps,
            tolerance_pct=params.tolerance_pct,
        )


# ---- shared helpers ----------------------------------------------------


async def _resolve_session(repo, session_id):
    """Same convention as memory_inspect — explicit ID > most recent."""
    sessions_res = await repo.list_sessions()
    if isinstance(sessions_res, Err):
        return sessions_res
    sessions = sessions_res.value
    target = None
    if session_id:
        for s in sessions:
            if s.id == session_id:
                target = s
                break
    elif sessions:
        target = sessions[-1]
    if target is None or not target.vm_service_uri:
        return err(
            DebugSessionFailure(
                message="no active debug session with a vm_service_uri",
                next_action="start_debug_session",
            )
        )
    return ok(target)


async def _with_vm(uri: str, op, **kwargs) -> Result[Any]:
    from ...infrastructure.vm_service_client import VmServiceClient

    try:
        client = VmServiceClient(uri)
        await client.connect()
    except ImportError as e:
        return err(
            DebugSessionFailure(
                message=str(e),
                next_action="install_debug_extras",
                details={"hint": "uv pip install -e \".[debug]\""},
            )
        )
    except Exception as e:
        return err(
            DebugSessionFailure(
                message=f"failed to connect to VM service: {e}",
                next_action="check_debug_session",
            )
        )
    try:
        return await op(client, **kwargs)
    finally:
        await client.close()


async def _pick_isolate(client) -> Result[str]:
    vm = await client.get_vm()
    isolates = (vm.get("result") or {}).get("isolates") or []
    runnable = next((i for i in isolates if i.get("runnable")), None)
    if not runnable:
        return err(
            DebugSessionFailure(
                message="no runnable isolate",
                next_action="check_debug_session",
            )
        )
    return ok(str(runnable["id"]))


# ---- start -------------------------------------------------------------


async def _start(client) -> Result[StartFrameProfileResult]:
    """Enable Timeline streams; capture baseline µs for diagnostics."""
    iso_res = await _pick_isolate(client)
    if isinstance(iso_res, Err):
        return iso_res
    iso_id = iso_res.value

    # Set the recording streams. Empty list = disabled; we set the
    # streams we want enabled.
    response = await client.call(
        "setVMTimelineFlags",
        {"recordedStreams": list(_TIMELINE_STREAMS)},
    )
    if "error" in response:
        return err(
            DebugSessionFailure(
                message=str(response["error"]),
                details={"response": response},
            )
        )

    # Capture baseline timestamp for diagnostics (the stop op
    # doesn't need this — it gets a full event window anyway —
    # but it's useful when an agent wants to bound the analysis
    # window manually).
    micros_response = await client.call("getVMTimelineMicros", {})
    baseline = int(
        (micros_response.get("result") or {}).get("timestamp", 0)
    )

    return ok(
        StartFrameProfileResult(
            isolate_id=iso_id,
            started_at_micros=baseline,
            streams_enabled=_TIMELINE_STREAMS,
        )
    )


# ---- stop --------------------------------------------------------------


async def _stop(
    client,
    target_fps: int,
    tolerance_pct: float,
) -> Result[StopFrameProfileResult]:
    """Fetch Timeline events, identify frames, compute stats, disable."""
    # Always disable on exit — even if subsequent calls fail. Use a
    # try/finally inside the function so the disable runs.
    try:
        timeline_response = await client.call("getVMTimeline", {})
        if "error" in timeline_response:
            return err(
                DebugSessionFailure(
                    message=str(timeline_response["error"]),
                    details={"response": timeline_response},
                )
            )
        trace_events = (timeline_response.get("result") or {}).get(
            "traceEvents", []
        )
        return ok(_analyze_frame_events(trace_events, target_fps, tolerance_pct))
    finally:
        # Always disable, best-effort. If the disable call itself
        # fails (e.g. the app crashed between start and stop), the
        # analysis is still useful — don't bury it in a finally
        # exception.
        with contextlib.suppress(Exception):
            await client.call("setVMTimelineFlags", {"recordedStreams": []})


def _analyze_frame_events(
    trace_events: list[dict],
    target_fps: int,
    tolerance_pct: float,
) -> StopFrameProfileResult:
    """Pure function — Timeline events → jank summary.

    Frame identification: Flutter's embedder emits 'Frame' duration
    events (Chrome trace 'ph': 'X' = complete event with explicit
    `dur` field). Each is one rendered frame's total wall time
    from vsync to commit.

    Build/raster split: the per-frame trace also includes 'Build'
    and 'Raster' sub-events (also ph='X'). We sum their durations
    inside the parent Frame window when present.
    """
    budget_micros = 1_000_000 // max(target_fps, 1)
    jank_threshold = int(budget_micros * (1 + tolerance_pct))

    frames: list[FrameTiming] = []
    # 'X' events have explicit `dur` so they're trivial to read; we
    # ignore 'B'/'E' (begin/end pairs) because Flutter emits 'X' for
    # frame events.
    for ev in trace_events:
        if ev.get("ph") != "X":
            continue
        name = ev.get("name", "")
        if name not in ("Frame", "Frame Phase", "vsync callback"):
            continue
        if "dur" not in ev:
            continue
        start = int(ev.get("ts", 0))
        dur = int(ev["dur"])

        # Optionally collect build/raster sub-events that fall
        # inside this frame's window. O(N^2) over all events is
        # fine for the typical 100-1000-event trace size; if the
        # window grows beyond that we can index-by-time later.
        build = 0
        raster = 0
        end = start + dur
        for sub in trace_events:
            if sub.get("ph") != "X" or "dur" not in sub:
                continue
            sub_ts = int(sub.get("ts", 0))
            if sub_ts < start or sub_ts >= end:
                continue
            sub_name = sub.get("name", "")
            if sub_name in ("Build", "Animator::BeginFrame"):
                build += int(sub["dur"])
            elif sub_name in ("Raster", "GPURasterizer::Draw"):
                raster += int(sub["dur"])

        frames.append(
            FrameTiming(
                start_micros=start,
                duration_micros=dur,
                build_micros=build,
                raster_micros=raster,
                is_janked=dur > jank_threshold,
            )
        )

    if not frames:
        return StopFrameProfileResult(
            target_fps=target_fps,
            budget_micros=budget_micros,
            total_frames=0,
            janked_frames=0,
            jank_pct=0.0,
            p50_micros=0,
            p90_micros=0,
            p99_micros=0,
            max_micros=0,
            worst_frames=(),
            advice=(
                "No frames captured. Either the bracket window was too "
                "short, or the app was idle between start/stop. Drive "
                "a visible interaction next time."
            ),
        )

    durations = sorted(f.duration_micros for f in frames)
    janked = [f for f in frames if f.is_janked]
    total = len(frames)
    worst = sorted(frames, key=lambda f: f.duration_micros, reverse=True)[:3]
    jank_pct = len(janked) / total if total > 0 else 0.0

    p50 = int(median(durations))
    p90 = int(durations[int(len(durations) * 0.9) - 1]) if len(durations) >= 10 else int(durations[-1])
    p99 = int(durations[int(len(durations) * 0.99) - 1]) if len(durations) >= 100 else int(durations[-1])
    max_d = int(durations[-1])

    advice = _advice(total, janked, jank_pct, p99, budget_micros)

    return StopFrameProfileResult(
        target_fps=target_fps,
        budget_micros=budget_micros,
        total_frames=total,
        janked_frames=len(janked),
        jank_pct=jank_pct,
        p50_micros=p50,
        p90_micros=p90,
        p99_micros=p99,
        max_micros=max_d,
        worst_frames=tuple(worst),
        advice=advice,
    )


def _advice(
    total: int, janked: list, jank_pct: float, p99: int, budget: int
) -> str:
    """One-sentence verdict for PR comments.

    Thresholds match common Flutter performance guidance:
    < 1% jank = smooth; 1-5% = noticeable; > 5% = bad. P99 over
    budget signals the worst case the user actually feels.
    """
    if total < 10:
        return (
            f"Only {total} frames captured — too few for confidence. "
            "Drive a longer interaction before stop_frame_profile."
        )
    if jank_pct < 0.01:
        return (
            f"✓ Smooth. {total} frames, {len(janked)} janked "
            f"({jank_pct * 100:.1f}%), p99 {p99 / 1000:.1f}ms "
            f"vs {budget / 1000:.1f}ms budget."
        )
    if jank_pct < 0.05:
        return (
            f"⚠ Noticeable jank. {len(janked)}/{total} frames "
            f"({jank_pct * 100:.1f}%) over budget. p99 {p99 / 1000:.1f}ms. "
            "Look at the worst-frames list for the culprits."
        )
    return (
        f"❌ Significant jank. {len(janked)}/{total} frames "
        f"({jank_pct * 100:.1f}%) over the {budget / 1000:.0f}ms budget. "
        f"p99 {p99 / 1000:.1f}ms. This is user-visible — investigate "
        "before shipping."
    )
