"""capture_release_screenshot — full-resolution PNG for app-store listings,
returned as METADATA ONLY so Claude doesn't auto-embed it inline.

Why this exists: regular `take_screenshot` returns a path. Claude Code
auto-embeds returned PNG paths into the conversation as image content
blocks. That breaks at the 2000px Claude multi-image limit. The dev-
loop cap (1920px on the long edge) keeps things working, but it's
useless for Play Store / App Store screenshots which need 1080×1920,
1242×2688, 2560×1440, etc. at native resolution.

This tool splits the concerns:

  - Full-resolution PNG → written to `<artifacts>/release/<label>.png`.
    Untouched. No cap. Use this directly for store listings.
  - Tiny thumbnail (256px long edge) → written to
    `<artifacts>/release/<label>.thumb.png`. Cheap to embed inline if
    you want Claude to verify "yes, the home screen is on top."
  - Tool returns a metadata dict — NO bare PNG path in `data`, so
    Claude Code doesn't auto-inline the full-res file. The thumbnail
    path lives under `data.thumbnail` and is small enough to embed
    safely.

The flow for shipping a Play Store release set:

  1. capture_release_screenshot(label="01-home")
  2. capture_release_screenshot(label="02-feed")
  3. capture_release_screenshot(label="03-detail")
  4. Open `<artifacts>/release/` in Finder, drag-and-drop into Play
     Console. No tokens spent on full-res image content.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..failures import VisionFailure
from ..repositories import (
    ArtifactRepository,
    ObservationRepository,
    SessionStateRepository,
)
from ..result import Err, Result, err, ok
from .base import BaseUseCase
from ._helpers import resolve_serial


_DEFAULT_THUMB_LONG_EDGE = 256


@dataclass(frozen=True, slots=True)
class CaptureReleaseScreenshotParams:
    label: str
    serial: str | None = None
    thumbnail_long_edge: int = _DEFAULT_THUMB_LONG_EDGE


@dataclass(frozen=True, slots=True)
class ReleaseScreenshotResult:
    """No bare PNG path at the top level — keeps the full-res file out of
    Claude's auto-inline path. `release_dir` is the parent directory the
    user opens in Finder; `thumbnail` is safe to embed."""

    label: str
    release_dir: Path                # parent dir; agent must `open` this manually
    full_resolution_filename: str    # filename only, not absolute path
    width: int
    height: int
    sha256: str
    size_bytes: int
    thumbnail: Path | None           # small PNG safe for inline embed; None if cv2 missing


class CaptureReleaseScreenshot(
    BaseUseCase[CaptureReleaseScreenshotParams, ReleaseScreenshotResult]
):
    """Capture a full-resolution screenshot for store listings.

    Returns metadata only (no full-res path in the agent-facing payload)
    so Claude Code doesn't auto-embed the un-capped image. A 256px
    thumbnail is generated alongside for inline verification.
    """

    def __init__(
        self,
        observation: ObservationRepository,
        artifacts: ArtifactRepository,
        state: SessionStateRepository,
    ) -> None:
        self._observation = observation
        self._artifacts = artifacts
        self._state = state

    async def execute(
        self, params: CaptureReleaseScreenshotParams
    ) -> Result[ReleaseScreenshotResult]:
        if not params.label.strip() or "/" in params.label or ".." in params.label:
            return err(
                VisionFailure(
                    message="label must be non-empty, no slashes or `..`",
                    next_action="fix_arguments",
                )
            )
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res

        session_res = await self._artifacts.current_session()
        if isinstance(session_res, Err):
            return session_res
        release_dir = session_res.value.root / "release"
        release_dir.mkdir(parents=True, exist_ok=True)
        out = release_dir / f"{params.label}.png"

        # Capture at full sensor resolution. No cap.
        shot_res = await self._observation.screenshot(serial_res.value, out)
        if isinstance(shot_res, Err):
            return shot_res

        # Read full dimensions + hash without touching the file.
        size_bytes = out.stat().st_size
        digest = hashlib.sha256()
        with out.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)

        width, height = _read_png_dimensions(out)

        # Generate a small thumbnail for safe inline embed. Best-effort —
        # if cv2 isn't installed, we skip and return thumbnail=None. The
        # full-res file is still on disk; agent can still proceed.
        thumb_path: Path | None = None
        try:
            thumb_path = _make_thumbnail(
                source=out,
                target=release_dir / f"{params.label}.thumb.png",
                long_edge=max(64, params.thumbnail_long_edge),
            )
        except Exception:  # noqa: BLE001 — never fail the capture on thumbnail issues
            thumb_path = None

        return ok(
            ReleaseScreenshotResult(
                label=params.label,
                release_dir=release_dir,
                full_resolution_filename=out.name,
                width=width,
                height=height,
                sha256=digest.hexdigest(),
                size_bytes=size_bytes,
                thumbnail=thumb_path,
            )
        )


# ---- helpers -------------------------------------------------------------


def _read_png_dimensions(path: Path) -> tuple[int, int]:
    """Read PNG IHDR width/height without depending on cv2.

    PNG starts with 8-byte signature + 4-byte chunk length + 4-byte type
    (`IHDR`) + 4-byte width + 4-byte height. Total offset to width:
    8 + 4 + 4 = 16. Endianness: big.
    """
    with path.open("rb") as fh:
        header = fh.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return (width, height)


def _make_thumbnail(source: Path, target: Path, long_edge: int) -> Path | None:
    """Write a small PNG copy of `source` clamped to `long_edge`. Requires
    cv2; returns None if unavailable."""
    from importlib.util import find_spec

    if find_spec("cv2") is None:
        return None
    import cv2

    img = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= long_edge:
        cv2.imwrite(str(target), img)
        return target
    scale = long_edge / longest
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(target), resized)
    return target
