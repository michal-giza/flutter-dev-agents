"""Dispatcher-level safety net: cap any PNG path leaking out of the
response envelope.

Why a second line of defense: we hit the 2000px limit twice now even
after capping inside individual use cases. The pattern keeps recurring
because:

  1. The fix-at-use-case-site approach has N callers and only catches
     N-1 of them — there's always one we forget.
  2. Future tools that emit screenshots will forget too. Code review
     can't reliably catch it.
  3. Claude Code's auto-embed scans returned strings for image paths.
     If a path ends in `.png` and points at an over-cap file, the
     conversation breaks. Period.

So this module walks every tool response, finds any string that looks
like a `.png` file path, and caps that file IN PLACE before the
response leaves the dispatcher. Idempotent — capping an already-
capped image is a no-op.

Goldens at `<project>/tests/fixtures/golden/**` are skipped (full-res
intentional). Release-mode files at `<artifacts>/release/**` are
skipped too — that workflow returns a parent directory, not a PNG path.

This is the seatbelt. Individual use-case caps are still belt; this
is the seatbelt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# Paths under these path-segment patterns are EXEMPT from auto-capping
# because their full-resolution form is required for the user's workflow.
# Match by `/segment/` substring so a project rooted anywhere works.
_EXEMPT_SEGMENTS = (
    "/tests/fixtures/golden/",   # SaveGoldenImage targets — diff math needs native
    "/release/",                  # capture_release_screenshot targets — store listings
)


def _is_exempt(path_str: str) -> bool:
    return any(segment in path_str for segment in _EXEMPT_SEGMENTS)


def _looks_like_png_path(value: str) -> bool:
    """Heuristic: a string is a real PNG path if it ends `.png` AND points
    at an existing file. Doesn't fire on doc-comment fragments or example
    strings in error messages."""
    if not isinstance(value, str) or not value.endswith(".png"):
        return False
    if len(value) > 1024:
        return False
    try:
        return Path(value).is_file()
    except OSError:
        return False


def _walk_strings(node: Any):
    """Yield every string in a nested dict/list/tuple structure."""
    if isinstance(node, str):
        yield node
        return
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk_strings(v)
        return
    if isinstance(node, (list, tuple)):
        for v in node:
            yield from _walk_strings(v)


def cap_pngs_in_envelope(envelope: dict) -> int:
    """Scan `envelope` for PNG file paths and cap any oversized ones.

    Returns the number of files capped. Idempotent — calling twice is
    free. Exemptions: goldens + release-mode files (per `_EXEMPT_SEGMENTS`).
    """
    from ..data.image_capping import cap_image_in_place

    capped = 0
    seen: set[str] = set()
    for value in _walk_strings(envelope):
        if value in seen:
            continue
        seen.add(value)
        if not _looks_like_png_path(value):
            continue
        if _is_exempt(value):
            continue
        if cap_image_in_place(Path(value)):
            capped += 1
    return capped
