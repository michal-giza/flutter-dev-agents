"""Dispatcher-level safety net: cap any PNG path leaking out of the
response envelope, and HARD-REFUSE to return paths the cap couldn't fix.

Why a hard guard, not just best-effort: the user has now hit the
2000px limit three times despite per-use-case caps. Each time the
fix was real but a future regression — a forgotten use case, a stale
MCP subprocess running old code, a missing cv2 — slipped one through.

This module is the last line. It runs AFTER every tool dispatch:

  1. Walk the response envelope. For every string that points at an
     existing `.png` file, attempt to cap.
  2. After capping, verify dimensions. If the file is STILL over cap
     (e.g. cv2/PIL/sips all unavailable), REWRITE the envelope to
     remove the offending path string and add an error marker.

The agent gets a clear, structured error instead of a path that would
poison the conversation. The file stays on disk for forensic use; only
the agent-visible reference is sanitised.

Goldens at `<project>/tests/fixtures/golden/**` are skipped (full-res
intentional). Release-mode files at `<artifacts>/release/**` are
skipped too — that workflow returns metadata, not a PNG path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..observability import warn

# Paths under these path-segment patterns are EXEMPT from auto-capping
# because their full-resolution form is required for the user's workflow.
# Match by `/segment/` substring so a project rooted anywhere works.
_EXEMPT_SEGMENTS = (
    "/tests/fixtures/golden/",   # SaveGoldenImage targets — diff math needs native
    "/release/",                  # capture_release_screenshot targets — store listings
)

# Replacement marker the seatbelt writes when it had to remove an
# un-cappable path from the response. The agent sees this and can
# diagnose / install missing extras.
_REMOVED_MARKER = "<removed: image-cap failed; see stderr for diagnosis>"


def _is_exempt(path_str: str) -> bool:
    return any(segment in path_str for segment in _EXEMPT_SEGMENTS)


def _looks_like_png_path(value: str) -> bool:
    """A string is a real PNG path if it ends `.png` AND points at an
    existing file. Filters out doc-comment fragments and example strings
    in error messages."""
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


def _replace_in_place(node: Any, replacements: dict[str, str]) -> Any:
    """Walk + rewrite. Replaces any string in `node` whose exact value is
    a key in `replacements`. Returns the rewritten structure."""
    if isinstance(node, str):
        return replacements.get(node, node)
    if isinstance(node, dict):
        return {k: _replace_in_place(v, replacements) for k, v in node.items()}
    if isinstance(node, list):
        return [_replace_in_place(v, replacements) for v in node]
    if isinstance(node, tuple):
        return tuple(_replace_in_place(v, replacements) for v in node)
    return node


# Hard ceiling — independent of `MCP_MAX_IMAGE_DIM`. Even if a user (or a
# stale subprocess running old defaults) sets the env cap to 2200 or
# higher, the safety net refuses anything > 1900 to protect against the
# upstream API's 2000px-per-image rejection in multi-image requests.
# Setting this just below 2000 leaves a small safety margin for any
# off-by-one in dimension probing across backends.
_HARD_CEILING_PX = 1900


def cap_pngs_in_envelope(envelope: dict) -> dict:
    """Scan `envelope` for PNG file paths, cap any oversized ones, and
    HARD-REFUSE to return paths the cap couldn't fix.

    Two layers of defense, both must pass:

      1. `cap_image_in_place(path)` — soft cap, defaults to
         `MCP_MAX_IMAGE_DIM` env (1600 today).
      2. `is_within_cap(path, max_dim=_HARD_CEILING_PX)` — hard 1900 ceiling
         that ignores env overrides. Catches the case where someone bumped
         the soft cap past 2000 or a stale subprocess is using the old
         1920 default that the upstream API can still reject under heavy
         multi-image accumulation.

    Returns the envelope (possibly rewritten if any path was refused).
    Adds `image_cap` metadata describing what was capped vs refused, so
    the agent and ops can debug.
    """
    from ..data.image_capping import cap_image_in_place, is_within_cap

    capped: list[str] = []
    refused: list[dict[str, str]] = []
    seen: set[str] = set()
    replacements: dict[str, str] = {}

    for value in _walk_strings(envelope):
        if value in seen:
            continue
        seen.add(value)
        if not _looks_like_png_path(value):
            continue
        if _is_exempt(value):
            continue
        path = Path(value)
        # First attempt: soft cap (env-driven default 1600).
        if cap_image_in_place(path):
            capped.append(value)
        # Second attempt: if still > hard ceiling, try ONCE more with the
        # hard cap explicitly. This catches the case where env was set
        # higher than the hard ceiling.
        if not is_within_cap(path, max_dim=_HARD_CEILING_PX) and cap_image_in_place(
            path, max_dim=_HARD_CEILING_PX
        ):
            capped.append(value)
        # Final verification against the hard ceiling. If we still can't
        # bring it under, refuse the path.
        if not is_within_cap(path, max_dim=_HARD_CEILING_PX):
            # The cap couldn't fix it. Refuse the path.
            refused.append(
                {
                    "path": value,
                    "reason": (
                        "image exceeds the dimension cap and could not be "
                        "resized — no image backend available (install cv2, "
                        "PIL, or run on macOS for sips)"
                    ),
                }
            )
            replacements[value] = _REMOVED_MARKER
            warn(
                "image_safety_net_refused",
                path=value,
                reason="cap_failed_all_backends",
            )

    if not capped and not refused:
        return envelope

    # Rewrite if anything was refused. Also surface diagnostics so the
    # agent can correct its environment instead of silently failing.
    if replacements:
        envelope = _replace_in_place(envelope, replacements)
    diag: dict[str, Any] = {}
    if capped:
        diag["capped"] = capped
    if refused:
        diag["refused"] = refused
        # If we had to refuse anything, flip ok to false so the agent
        # treats this as a hard failure and surfaces the diagnosis.
        envelope.setdefault("error", {})
        envelope["ok"] = False
        envelope["error"].setdefault("code", "ImageCapFailure")
        envelope["error"].setdefault(
            "message",
            f"{len(refused)} image(s) exceeded the dimension cap and "
            "could not be resized (no working image backend). See "
            "details.image_cap.refused.",
        )
        envelope["error"].setdefault("next_action", "install_image_backend")
        envelope["error"].setdefault("details", {})
        envelope["error"]["details"]["image_cap"] = diag
    else:
        # Capped successfully — attach as a non-blocking note.
        envelope["image_cap"] = diag
    return envelope
