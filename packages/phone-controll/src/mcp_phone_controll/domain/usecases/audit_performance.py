"""Performance audit — Flutter jank / animation / scroll smells.

The gap no first-party MCP fills: Google's `dart mcp-server` does
analyze/fix/format/inspector but **no performance, frame, or animation
judgment**; Maestro and the browser MCPs don't do Flutter static
analysis. This encodes senior "why is it janky" taste as regex rules
over `lib/`. Pure compute — no device, no VM, model-agnostic.

Scope: the three things that actually drop frames in Flutter apps —
**animations**, **scroll/virtualization**, and **rebuild cost** — caught
at the precision a regex can credibly hit without an AST.

Rules (10 across 3 severities):

  **HIGH — drops frames** (4)
    • non_lazy_list            — ListView(children:)/GridView(children:)
                                 default ctor builds every child up front
                                 (use .builder for long/dynamic lists)
    • setstate_in_animation    — setState() inside an animation listener
                                 rebuilds the whole subtree every frame
                                 (use AnimatedBuilder)
    • controller_not_disposed  — AnimationController created but the file
                                 has no dispose() (ticker leak + jank)
    • opacity_animated         — Opacity(opacity: <animation>) repaints
                                 the subtree each frame (use FadeTransition
                                 / AnimatedOpacity)

  **MEDIUM — likely jank** (4)
    • shrinkwrap_list          — shrinkWrap:true on a scrollable lays out
                                 all children (defeats virtualization)
    • nested_scroll_column     — SingleChildScrollView + Column rendering
                                 a dynamic list (...spread / .map) — not
                                 lazy
    • image_no_cache_size      — Image.network/asset without cacheWidth/
                                 cacheHeight decodes at full resolution
    • heavy_work_in_build      — .sort()/.where().toList() inside build()
                                 re-runs every rebuild

  **LOW — polish** (2)
    • missing_repaint_boundary — file animates (AnimationController/
                                 AnimatedBuilder/CustomPaint) but has no
                                 RepaintBoundary to isolate repaints
    • implicit_anim_zero       — implicit animation with Duration.zero
                                 (animates nothing — likely a bug)

What this is NOT: not a profiler (use ingest_frame_timeline for runtime
jank), not the linter (we skip `const`/style nits `flutter analyze`
owns), not an AST. False negatives expected on indirection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from ._helpers import is_path_excluded
from .base import BaseUseCase


class Severity(str, Enum):
    HIGH = "high"       # drops frames
    MEDIUM = "medium"   # likely jank
    LOW = "low"         # polish


@dataclass(frozen=True, slots=True)
class PerfFinding:
    rule: str
    description: str
    severity: Severity
    file: str
    line: int
    snippet: str
    fix_hint: str
    category: str        # animation / scroll / rebuild


@dataclass(frozen=True, slots=True)
class AuditPerformanceParams:
    project_path: Path
    paths: tuple[str, ...] = ()
    min_severity: str = "low"
    max_findings: int = 200


@dataclass(frozen=True, slots=True)
class AuditPerformanceResult:
    grade: str                               # smooth / acceptable / janky / severe
    score: float                             # weighted findings per KLOC
    files_scanned: int
    lines_scanned: int
    findings: tuple[PerfFinding, ...]
    findings_by_severity: dict[str, int]
    findings_by_category: dict[str, int]
    top_actions: tuple[str, ...]
    advice: str


_SEVERITY_WEIGHT = {Severity.HIGH: 6, Severity.MEDIUM: 2, Severity.LOW: 1}


class AuditPerformance(
    BaseUseCase[AuditPerformanceParams, AuditPerformanceResult]
):
    """Scan a Flutter project for jank-causing animation / scroll /
    rebuild patterns. Pure compute, regex over `lib/`."""

    async def execute(
        self, params: AuditPerformanceParams
    ) -> Result[AuditPerformanceResult]:
        if not params.project_path.is_dir():
            return err(FilesystemFailure(
                message=f"project_path not found: {params.project_path}",
                next_action="fix_arguments",
            ))
        try:
            min_sev = Severity(params.min_severity)
        except ValueError:
            return err(FilesystemFailure(
                message=(
                    f"unknown min_severity {params.min_severity!r}. "
                    "Valid: high, medium, low"
                ),
                next_action="fix_arguments",
            ))

        files = _collect_dart_files(params.project_path, params.paths)
        all_findings: list[PerfFinding] = []
        lines_total = 0
        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = content.splitlines()
            lines_total += len(lines)
            rel = str(f.relative_to(params.project_path))
            all_findings.extend(_scan_dart(rel, lines, content))

        order = [Severity.HIGH, Severity.MEDIUM, Severity.LOW]
        kept = set(order[: order.index(min_sev) + 1])
        all_findings = [f for f in all_findings if f.severity in kept]

        sev_idx = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
        all_findings.sort(key=lambda x: (sev_idx[x.severity], x.file, x.line))
        kept_findings = tuple(all_findings[: params.max_findings])

        by_sev: dict[str, int] = {}
        by_cat: dict[str, int] = {}
        for fnd in kept_findings:
            by_sev[fnd.severity.value] = by_sev.get(fnd.severity.value, 0) + 1
            by_cat[fnd.category] = by_cat.get(fnd.category, 0) + 1

        weighted = sum(_SEVERITY_WEIGHT[f.severity] for f in kept_findings)
        kloc = max(lines_total, 1) / 1000.0
        score = weighted / kloc
        grade = _grade_for(score, by_sev, len(files))

        return ok(AuditPerformanceResult(
            grade=grade,
            score=round(score, 2),
            files_scanned=len(files),
            lines_scanned=lines_total,
            findings=kept_findings,
            findings_by_severity=by_sev,
            findings_by_category=by_cat,
            top_actions=_build_top_actions(kept_findings),
            advice=_build_advice(grade, score, len(kept_findings), len(files)),
        ))


# ============================================================
# File discovery
# ============================================================


def _collect_dart_files(project: Path, paths: tuple[str, ...]) -> list[Path]:
    roots = (
        [project / p for p in paths if (project / p).exists()]
        if paths else [project]
    )
    out: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".dart":
            out.append(root)
            continue
        for f in root.rglob("*.dart"):
            if not f.is_file() or is_path_excluded(f, project):
                continue
            name = f.name
            if (
                name.endswith((".g.dart", ".freezed.dart", ".gr.dart",
                               ".mocks.dart", ".config.dart"))
                or ".gen." in name
            ):
                continue
            if "/test/" in str(f) or name.endswith("_test.dart"):
                continue
            out.append(f)
    return sorted(set(out), key=str)


# ============================================================
# Patterns
# ============================================================

# Default (non-lazy) ListView/GridView constructors — NOT .builder /
# .separated / .custom. `ListView(` immediately (no dot) = default ctor.
_RE_NON_LAZY_LIST = re.compile(r"\b(ListView|GridView)\s*\(")
_RE_LAZY_LIST = re.compile(r"\b(ListView|GridView)\s*\.\s*(builder|separated|custom)")
_RE_SETSTATE_IN_LISTENER = re.compile(
    r"addListener\s*\(\s*\(\s*\)\s*(?:=>|\{)[^;{}]*setState", re.DOTALL
)
_RE_ANIM_CONTROLLER = re.compile(r"\bAnimationController\s*\(")
_RE_DISPOSE = re.compile(r"\bvoid\s+dispose\s*\(")
_RE_OPACITY_ANIMATED = re.compile(
    r"\bOpacity\s*\(\s*opacity:\s*[^,)\n]*(?:_?anim\w*|_?controller\w*|\.value)"
)
_RE_SHRINKWRAP = re.compile(r"shrinkWrap\s*:\s*true")
_RE_SINGLE_SCROLL = re.compile(r"\bSingleChildScrollView\s*\(")
_RE_COLUMN = re.compile(r"\bColumn\s*\(")
_RE_DYNAMIC_LIST = re.compile(r"\.\.\.|\.map\s*\(")  # spread or .map in children
_RE_IMAGE_CALL = re.compile(r"\bImage\s*\.\s*(network|asset|file)\s*\(")
_RE_CACHE_SIZE = re.compile(r"cache(?:Width|Height)\s*:")
_RE_BUILD_METHOD = re.compile(r"Widget\s+build\s*\(\s*BuildContext")
_RE_HEAVY_OP = re.compile(r"\.(?:sort|where|map|reduce|fold)\s*\(")
_RE_ANIMATES = re.compile(
    r"\bAnimationController\s*\(|\bAnimatedBuilder\s*\(|\bCustomPaint\s*\("
)
_RE_REPAINT_BOUNDARY = re.compile(r"\bRepaintBoundary\s*\(")
_RE_DURATION_ZERO = re.compile(r"Duration\s*\.\s*zero|Duration\s*\(\s*\)")
_RE_IMPLICIT_ANIM = re.compile(
    r"\bAnimated(?:Container|Opacity|Padding|Align|Positioned|"
    r"DefaultTextStyle|Scale|Rotation|Slide)\s*\("
)


# ============================================================
# Per-file scanner
# ============================================================


def _scan_dart(rel: str, lines: list[str], content: str) -> list[PerfFinding]:
    findings: list[PerfFinding] = []

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # HIGH — non-lazy list (default ctor, not .builder)
        if _RE_NON_LAZY_LIST.search(line) and not _RE_LAZY_LIST.search(line):
            findings.append(_mk(
                "non_lazy_list",
                "Default ListView/GridView constructor builds every child "
                "eagerly — janks on long or dynamic lists.",
                Severity.HIGH, "scroll", rel, i, stripped[:140],
                "Use ListView.builder / GridView.builder (lazy, virtualized).",
            ))

        # HIGH — animated Opacity widget
        if _RE_OPACITY_ANIMATED.search(line):
            findings.append(_mk(
                "opacity_animated",
                "Opacity widget driven by an animation repaints its whole "
                "subtree every frame.",
                Severity.HIGH, "animation", rel, i, stripped[:140],
                "Use FadeTransition / AnimatedOpacity (compositor-level).",
            ))

        # MEDIUM — shrinkWrap
        if _RE_SHRINKWRAP.search(line):
            findings.append(_mk(
                "shrinkwrap_list",
                "shrinkWrap:true lays out all children at once — defeats "
                "list virtualization.",
                Severity.MEDIUM, "scroll", rel, i, stripped[:140],
                "Give the list bounded height + remove shrinkWrap, or use a "
                "CustomScrollView with slivers.",
            ))

        # MEDIUM — Image without cache size (check the call window)
        m = _RE_IMAGE_CALL.search(line)
        if m:
            window = content[content.find(line): content.find(line) + 300]
            if not _RE_CACHE_SIZE.search(window):
                findings.append(_mk(
                    "image_no_cache_size",
                    "Image.* without cacheWidth/cacheHeight decodes at full "
                    "resolution — memory + raster cost.",
                    Severity.MEDIUM, "rebuild", rel, i, stripped[:140],
                    "Pass cacheWidth/cacheHeight (target px) to downscale on decode.",
                ))

    # ---- File-level ----
    # HIGH — setState inside an animation listener
    if _RE_SETSTATE_IN_LISTENER.search(content):
        m = _RE_SETSTATE_IN_LISTENER.search(content)
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "setstate_in_animation",
            "setState() inside an animation listener rebuilds the whole "
            "subtree every frame.",
            Severity.HIGH, "animation", rel, line_no, "addListener(() { setState(...) })",
            "Drive the animated widget with AnimatedBuilder instead of setState.",
        ))

    # HIGH — AnimationController created but no dispose() in file
    if _RE_ANIM_CONTROLLER.search(content) and not _RE_DISPOSE.search(content):
        m = _RE_ANIM_CONTROLLER.search(content)
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "controller_not_disposed",
            "AnimationController created but the file has no dispose() — "
            "ticker keeps firing (leak + jank).",
            Severity.HIGH, "animation", rel, line_no, "AnimationController(...)",
            "Dispose it in State.dispose(); add a TickerProviderStateMixin.",
        ))

    # MEDIUM — SingleChildScrollView + Column rendering a dynamic list
    if (
        _RE_SINGLE_SCROLL.search(content)
        and _RE_COLUMN.search(content)
        and _RE_DYNAMIC_LIST.search(content)
    ):
        m = _RE_SINGLE_SCROLL.search(content)
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "nested_scroll_column",
            "SingleChildScrollView + Column rendering a dynamic list "
            "(spread/.map) builds every row — not lazy.",
            Severity.MEDIUM, "scroll", rel, line_no,
            "SingleChildScrollView(child: Column(children: [...list]))",
            "Use ListView.builder, or CustomScrollView + SliverList.",
        ))

    # MEDIUM — heavy work in build()
    bm = _RE_BUILD_METHOD.search(content)
    if bm:
        # look at the ~1500 chars after build( for a heavy collection op
        window = content[bm.start(): bm.start() + 1500]
        hm = _RE_HEAVY_OP.search(window)
        if hm:
            line_no = content.count("\n", 0, bm.start() + hm.start()) + 1
            findings.append(_mk(
                "heavy_work_in_build",
                "Collection op (sort/where/map/reduce) inside build() "
                "re-runs on every rebuild.",
                Severity.MEDIUM, "rebuild", rel, line_no, "build() { ... .sort()/.where() ... }",
                "Hoist the computation out of build() (memoize / compute in the model).",
            ))

    # LOW — animates but no RepaintBoundary
    if _RE_ANIMATES.search(content) and not _RE_REPAINT_BOUNDARY.search(content):
        m = _RE_ANIMATES.search(content)
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "missing_repaint_boundary",
            "File animates but has no RepaintBoundary — repaints can spill "
            "into sibling/parent layers.",
            Severity.LOW, "animation", rel, line_no, "AnimationController/AnimatedBuilder/CustomPaint",
            "Wrap the animated subtree in a RepaintBoundary to isolate repaints.",
        ))

    # LOW — implicit animation with Duration.zero
    if _RE_IMPLICIT_ANIM.search(content) and _RE_DURATION_ZERO.search(content):
        # only if both appear reasonably close (same widget likely)
        am = _RE_IMPLICIT_ANIM.search(content)
        line_no = content.count("\n", 0, am.start()) + 1
        findings.append(_mk(
            "implicit_anim_zero",
            "Implicit animation with Duration.zero animates nothing — "
            "likely an unintended no-op.",
            Severity.LOW, "animation", rel, line_no, "Animated*(duration: Duration.zero)",
            "Give it a real duration, or use the non-animated widget.",
        ))

    return findings


# ============================================================
# Helpers
# ============================================================


def _mk(
    rule: str, desc: str, severity: Severity, category: str,
    file: str, line: int, snippet: str, fix_hint: str,
) -> PerfFinding:
    return PerfFinding(
        rule=rule, description=desc, severity=severity, category=category,
        file=file, line=line, snippet=snippet[:140], fix_hint=fix_hint,
    )


def _grade_for(score: float, by_sev: dict[str, int], files: int) -> str:
    if files == 0:
        return "smooth"
    if by_sev.get("high", 0) >= 5 or score >= 12:
        return "severe"
    if by_sev.get("high", 0) > 0 or score >= 4:
        return "janky"
    if score >= 1:
        return "acceptable"
    return "smooth"


def _build_top_actions(findings: tuple[PerfFinding, ...]) -> tuple[str, ...]:
    if not findings:
        return ("No performance findings at the configured threshold.",)
    counts: dict[str, tuple[int, PerfFinding]] = {}
    for f in findings:
        prev = counts.get(f.rule)
        if prev is None or _SEVERITY_WEIGHT[f.severity] > _SEVERITY_WEIGHT[prev[1].severity]:
            counts[f.rule] = ((prev[0] if prev else 0) + 1, f)
        else:
            counts[f.rule] = (prev[0] + 1, prev[1])
    ranked = sorted(
        counts.items(),
        key=lambda kv: (-_SEVERITY_WEIGHT[kv[1][1].severity], -kv[1][0]),
    )
    return tuple(
        f"[{s.severity.value}] {rule} ×{n} — {s.fix_hint}"
        for rule, (n, s) in ranked[:5]
    )


def _build_advice(grade: str, score: float, n: int, files: int) -> str:
    tail = {
        "severe": " STOP — multiple frame-dropping patterns; profile + fix the highs.",
        "janky": " Fix the HIGH findings (lists + animations) before shipping.",
        "acceptable": " Minor polish; mediums/lows when convenient.",
        "smooth": " No notable jank patterns found.",
    }.get(grade, "")
    return (
        f"Performance grade: {grade} ({score:.1f} weighted/KLOC). "
        f"{n} findings across {files} files.{tail}"
    )
