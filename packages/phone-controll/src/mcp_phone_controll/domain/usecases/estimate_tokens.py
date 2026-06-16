"""estimate_tokens — token counter + budget predictor/validator.

A context-budget guard, primarily for **small / local models**: our
tools can emit large payloads (a 74k-char widget tree, MB-scale HAR /
Lighthouse / trace files), and a small context window overflows
silently. This lets an agent **preflight** a payload or file and decide
whether to proceed, scope it down, or compact first.

Scope (honest about what a server-side MCP can do):
  • **Count** — estimate tokens of a string or a file.
  • **Predict** — size a file *before* you ingest it (e.g. "is this HAR
    safe to ingest_har?").
  • **Validate** — against a `budget_tokens` you declare → fits / tight /
    overflow, with a recommendation.

It can NOT see the model's live remaining context or trigger a flush —
compaction is the host's job (Claude Code auto-compacts; a local agent
clears its own history). We provide the signal; the host acts on it.

Estimation: uses `tiktoken` (cl100k_base) when installed for an exact
count; otherwise a calibrated chars-per-token heuristic with a low–high
band. Pure compute, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..failures import FilesystemFailure, InvalidArgumentFailure
from ..result import Result, err, ok
from .base import BaseUseCase

# Don't read more than this into memory for a single estimate; above it
# we estimate from the byte size (≈1 byte/char for ASCII/JSON) instead.
_MAX_READ_BYTES = 25 * 1024 * 1024  # 25 MB


@dataclass(frozen=True, slots=True)
class EstimateTokensParams:
    text: str | None = None
    path: Path | None = None
    # Declare your remaining context budget to get a fits/flush verdict.
    budget_tokens: int | None = None
    # Avg chars per token for the heuristic. ~4 for prose; code/JSON is
    # denser (~3.3). Default 4.0. Ignored when tiktoken is used.
    chars_per_token: float = 4.0


@dataclass(frozen=True, slots=True)
class EstimateTokensResult:
    method: str                  # "tiktoken" | "heuristic"
    chars: int
    words: int
    estimated_tokens: int
    low_tokens: int              # heuristic band (== estimate for tiktoken)
    high_tokens: int
    size_class: str              # small / medium / large / huge
    source: str                  # "text" | "file:<name>" | "file-size:<name>"
    budget_tokens: int | None
    fits: bool | None
    headroom_tokens: int | None
    recommendation: str | None   # proceed / proceed_with_caution / scope_or_paginate / flush_context
    advice: str


# token size classes (rough context-pressure bands)
_SMALL, _MEDIUM, _LARGE = 2_000, 10_000, 50_000


class EstimateTokens(BaseUseCase[EstimateTokensParams, EstimateTokensResult]):
    """Estimate the token cost of text or a file, optionally validating
    against a declared context budget. Pure compute."""

    async def execute(
        self, params: EstimateTokensParams
    ) -> Result[EstimateTokensResult]:
        if params.text is None and params.path is None:
            return err(InvalidArgumentFailure(
                message="provide either `text` or `path`.",
                next_action="fix_arguments",
            ))

        cpt = params.chars_per_token if params.chars_per_token > 0 else 4.0

        # --- gather the text / size ---
        if params.text is not None:
            text = params.text
            chars = len(text)
            words = len(text.split())
            source = "text"
            big_file_bytes: int | None = None
        else:
            p = params.path
            if p is None or not p.is_file():
                return err(FilesystemFailure(
                    message=f"file not found: {params.path}",
                    next_action="fix_arguments",
                ))
            try:
                size = p.stat().st_size
            except OSError as e:
                return err(FilesystemFailure(
                    message=f"cannot stat {p}: {e}", next_action="fix_arguments",
                ))
            if size > _MAX_READ_BYTES:
                # Too big to load — estimate from byte size (≈ chars).
                text = ""
                chars = size
                words = size // 5  # rough
                source = f"file-size:{p.name}"
                big_file_bytes = size
            else:
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    return err(FilesystemFailure(
                        message=f"cannot read {p}: {e}", next_action="fix_arguments",
                    ))
                chars = len(text)
                words = len(text.split())
                source = f"file:{p.name}"
                big_file_bytes = None

        # --- estimate ---
        method, est, low, high = _estimate(text, chars, cpt, big_file_bytes)
        size_class = _size_class(est)

        # --- validate against budget ---
        fits: bool | None = None
        headroom: int | None = None
        rec: str | None = None
        if params.budget_tokens is not None and params.budget_tokens > 0:
            b = params.budget_tokens
            headroom = b - est
            fits = est <= b
            if not fits:
                rec = "flush_context"
            elif headroom < 0.2 * b:
                rec = "proceed_with_caution"
            else:
                rec = "proceed"

        return ok(EstimateTokensResult(
            method=method,
            chars=chars,
            words=words,
            estimated_tokens=est,
            low_tokens=low,
            high_tokens=high,
            size_class=size_class,
            source=source,
            budget_tokens=params.budget_tokens,
            fits=fits,
            headroom_tokens=headroom,
            recommendation=rec,
            advice=_advice(method, est, size_class, params.budget_tokens, fits, headroom, rec),
        ))


# ============================================================
# Estimation
# ============================================================


def _estimate(
    text: str, chars: int, cpt: float, big_file_bytes: int | None,
) -> tuple[str, int, int, int]:
    """Returns (method, estimate, low, high).

    The heuristic is purely char-based so the low–high band always
    brackets the central estimate. (An earlier version blended in a
    words×1.33 term, but words badly underestimate code/JSON — few
    whitespace-delimited tokens, many real ones — which pushed the
    center below the char-based low bound. tiktoken is the accurate path
    when installed.)
    """
    # Exact via tiktoken when available and we actually have the text.
    if text and big_file_bytes is None:
        try:
            import tiktoken  # type: ignore[import-not-found]

            enc = tiktoken.get_encoding("cl100k_base")
            n = len(enc.encode(text))
            return "tiktoken", n, n, n
        except Exception:
            pass  # fall through to heuristic

    central = round(chars / cpt) if cpt else 0
    low = round(chars / (cpt + 0.5))            # denser → fewer tokens
    high = round(chars / max(cpt - 0.7, 1.5))   # sparser → more tokens
    return "heuristic", max(central, 0), max(low, 0), max(high, central)


def _size_class(tokens: int) -> str:
    if tokens < _SMALL:
        return "small"
    if tokens < _MEDIUM:
        return "medium"
    if tokens < _LARGE:
        return "large"
    return "huge"


def _advice(method, est, size_class, budget, fits, headroom, rec) -> str:
    base = f"~{est:,} tokens ({method}, {size_class})"
    if budget is None:
        tail = {
            "small": " — safe to inline.",
            "medium": " — fine for most context windows.",
            "large": " — heavy; scope/paginate for small models.",
            "huge": " — will overflow small windows; scope, paginate, or summarize before ingesting.",
        }[size_class]
        return base + tail
    verdict = "fits" if fits else "OVERFLOWS"
    tail = {
        "flush_context": " — won't fit; compact/flush context or scope the payload first.",
        "proceed_with_caution": " — fits but tight (<20% headroom); consider scoping.",
        "proceed": " — comfortable headroom.",
    }.get(rec or "", "")
    return f"{base} vs {budget:,} budget → {verdict} (headroom {headroom:,}).{tail}"
