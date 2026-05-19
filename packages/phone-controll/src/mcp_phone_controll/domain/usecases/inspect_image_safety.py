"""Image-safety probe — "is this PNG safe to read directly?"

Field incident, May 19 2026: an overnight bot used raw
`adb exec-out screencap` (bypassing `take_screenshot`'s 1600px cap)
and accumulated 2400px PNGs that crashed the conversation on the 6th
shot with the API's 2000px-per-image limit.

The fix on the MCP side (PR #4) put `compress_png` on the BASIC tier
so an escape hatch is always visible. This file adds the *checker*:
a tiny, fast tool the agent calls BEFORE `Read`-ing any image to
learn:

  - is the long edge over the API's hard 2000px ceiling? → must
    `compress_png` first (or re-shoot via `take_screenshot`)
  - was the file ever passed through the MCP's cap pipeline? (the
    pipeline preserves the original at `<path>.orig.png` so the
    sibling-presence-check is a reliable "this is one of ours" signal)
  - the exact `next_action` the agent should take next

Why a checker AND `compress_png` and not just one? Because Read costs
context tokens — calling `compress_png` on every image when most
don't need it would waste budget. The checker is cheap (a `stat` +
~64 bytes of PNG header), runs first, and points at the right
remedy.

Scope: read-only. Never modifies the file. Never refuses based on
the path's parent dir — that's `compress_png`'s job. Designed to be
safe to call on any image path the agent has on hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from .base import BaseUseCase

# Same constant as image_safety_net._HARD_CEILING_PX — anything at or
# above this is rejected by the upstream API in multi-image requests.
# The cap pipeline targets 1600 by default, so a healthy MCP-produced
# screenshot is well under this threshold. We surface "exceeds safe
# threshold" at 1900 to leave a margin for the off-by-one across PNG
# dimension probes (cv2 vs PIL vs sips can disagree by 1px on some
# sources).
_API_HARD_DIMENSION_LIMIT = 2000
_SAFE_THRESHOLD = 1900


@dataclass(frozen=True, slots=True)
class InspectImageSafetyParams:
    path: Path


@dataclass(frozen=True, slots=True)
class InspectImageSafetyResult:
    path: str
    exists: bool
    width: int
    height: int
    long_edge_px: int
    bytes: int
    exceeds_api_dim_limit: bool   # at or over 2000 — API will reject
    exceeds_safe_threshold: bool  # over 1900 — close enough to refuse
    mcp_produced: bool            # sibling `.orig.png` present
    safe_to_read: bool            # the headline boolean for the agent
    next_action: str              # one of the values below
    advice: str                   # human-readable one-liner for the envelope


# Documented set so callers (and the test that pins them) can rely on
# stable values. Order roughly matches preference:
_NEXT_READ = "read_safely"
_NEXT_COMPRESS = "compress_png"
_NEXT_REGEN = "regenerate_via_take_screenshot"
_NEXT_NOT_FOUND = "fix_arguments"


class InspectImageSafety(
    BaseUseCase[InspectImageSafetyParams, InspectImageSafetyResult]
):
    """Probe an image path; tell the agent whether it's safe to read.

    No side effects. Reading the PNG header (24 bytes) is enough for
    dimensions — we don't decode pixels. The sibling-`.orig.png`
    check is a stat call. Total cost: well under 1 ms per call.
    """

    async def execute(
        self, params: InspectImageSafetyParams
    ) -> Result[InspectImageSafetyResult]:
        from ...data.image_capping import _read_png_dimensions

        path = Path(params.path).expanduser()
        # Don't `resolve()` to a non-existent path — preserve the agent's
        # input verbatim in the error envelope so they can tell exactly
        # what was wrong.
        if not path.is_file():
            return err(
                FilesystemFailure(
                    message=f"image not found: {path}",
                    next_action=_NEXT_NOT_FOUND,
                    details={"path": str(path)},
                )
            )

        try:
            size = path.stat().st_size
        except OSError as exc:
            return err(
                FilesystemFailure(
                    message=f"could not stat {path}: {exc}",
                    next_action="check_path",
                    details={"path": str(path)},
                )
            )

        dims = _read_png_dimensions(path)
        # Reject zero dimensions too — some corrupt PNGs have a valid
        # magic + all-zeros IHDR fields which the probe returns as
        # `(0, 0)` instead of None. Either way, the file is unsafe to
        # treat as an image.
        if dims is None or dims[0] == 0 or dims[1] == 0:
            # File exists but isn't a parseable PNG. Could be JPEG,
            # truncated download, etc. Surface it explicitly so the
            # agent doesn't quietly assume "image OK, must be safe".
            return err(
                FilesystemFailure(
                    message=(
                        f"{path} is not a readable PNG (header parse failed). "
                        "compress_png only handles PNGs; convert first."
                    ),
                    next_action="convert_to_png",
                    details={"path": str(path), "bytes": size},
                )
            )
        width, height = dims
        long_edge = max(width, height)

        # Provenance: any PNG that went through the MCP's cap pipeline
        # has a sibling `<path>.orig.png` (the preserved full-res copy).
        # That's a reliable "we touched this" marker. It doesn't *prove*
        # the current file is small — operators can manually mess with
        # paths — but combined with the dimension probe it gives the
        # agent enough signal.
        orig_sibling = path.with_suffix(".orig.png") if path.suffix == ".png" else None
        mcp_produced = bool(orig_sibling and orig_sibling.is_file())

        exceeds_hard = long_edge >= _API_HARD_DIMENSION_LIMIT
        exceeds_safe = long_edge > _SAFE_THRESHOLD

        # Decide the next action.
        if exceeds_hard:
            # Past the API's 2000 ceiling. The agent MUST act.
            # `compress_png` will resize down to 1600 by default, but if
            # the user's running an old subprocess without an image
            # backend (cv2/PIL missing), compress_png will fail —
            # `regenerate_via_take_screenshot` is the safer instruction
            # because that path has the safety-net rewriter behind it.
            next_action = _NEXT_REGEN if not mcp_produced else _NEXT_COMPRESS
            advice = (
                f"long edge is {long_edge}px (>= {_API_HARD_DIMENSION_LIMIT}); "
                "API will reject this image. "
                + (
                    "Re-shoot via take_screenshot."
                    if next_action == _NEXT_REGEN
                    else f"Call compress_png(path={path!s}, max_dim=1600)."
                )
            )
            safe = False
        elif exceeds_safe:
            # Between 1900 and 2000 — likely fine but risky under
            # accumulation. Recommend compress_png as cheap insurance.
            next_action = _NEXT_COMPRESS
            advice = (
                f"long edge is {long_edge}px (close to {_API_HARD_DIMENSION_LIMIT} "
                f"limit). compress_png recommended before Read."
            )
            safe = False
        else:
            next_action = _NEXT_READ
            advice = f"safe — long edge {long_edge}px, {size} bytes."
            safe = True

        return ok(
            InspectImageSafetyResult(
                path=str(path),
                exists=True,
                width=width,
                height=height,
                long_edge_px=long_edge,
                bytes=size,
                exceeds_api_dim_limit=exceeds_hard,
                exceeds_safe_threshold=exceeds_safe,
                mcp_produced=mcp_produced,
                safe_to_read=safe,
                next_action=next_action,
                advice=advice,
            )
        )
