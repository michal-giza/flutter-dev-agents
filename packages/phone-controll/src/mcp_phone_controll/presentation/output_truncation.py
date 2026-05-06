"""Truncate long tool outputs so 4B-class models don't run out of context.

Applied at the dispatcher boundary AFTER serialization. Caps strings, lists,
and base64-blob values; replaces the truncated portion with a small marker so
the agent knows there's more to fetch.

Strings → '...<truncated, full size N bytes>'
Lists   → keep first MAX, append a sentinel object {_truncated: <count>}
Dicts with a 'data' field that's a long string get the same string treatment.

Tools that already write artifacts to disk (screenshot, recording) return
paths, not blobs — those are short and untouched. Tools that genuinely produce
long inline data (read_logs, dump_ui, session_summary) get capped.
"""

from __future__ import annotations

from typing import Any


DEFAULT_MAX_STRING_BYTES = 8_000          # ~2-3K tokens
DEFAULT_MAX_LIST_ITEMS = 200
DEFAULT_MAX_DEPTH = 8


def truncate_envelope(
    envelope: dict,
    max_string_bytes: int = DEFAULT_MAX_STRING_BYTES,
    max_list_items: int = DEFAULT_MAX_LIST_ITEMS,
) -> dict:
    """Returns a NEW envelope with `data` (and `error.details`) truncated.

    Adds `data_truncated: true` and `next_action: "request_artifact"` when the
    truncation actually fired, so an agent knows to fetch the full file from
    artifacts rather than re-call.
    """
    out = dict(envelope)
    truncated = False
    if "data" in out:
        out["data"], data_truncated = _walk(
            out["data"], max_string_bytes, max_list_items, depth=0
        )
        truncated = truncated or data_truncated
    if "error" in out and isinstance(out["error"], dict):
        details = out["error"].get("details")
        if details is not None:
            new_details, details_truncated = _walk(
                details, max_string_bytes, max_list_items, depth=0
            )
            new_error = dict(out["error"])
            new_error["details"] = new_details
            out["error"] = new_error
            truncated = truncated or details_truncated
    if truncated:
        out["data_truncated"] = True
        # Don't override an existing next_action; for ok=true responses,
        # add one so the agent knows to fetch full data via artifacts.
        if out.get("ok") and "next_action" not in out:
            out["next_action"] = "fetch_full_artifact_if_needed"
    return out


def _walk(
    value: Any, max_string: int, max_list: int, depth: int
) -> tuple[Any, bool]:
    if depth > DEFAULT_MAX_DEPTH:
        return ("...<max depth>", True)
    if isinstance(value, str):
        return _truncate_string(value, max_string)
    if isinstance(value, list):
        return _truncate_list(value, max_string, max_list, depth)
    if isinstance(value, dict):
        truncated_any = False
        out = {}
        for k, v in value.items():
            new_v, child_truncated = _walk(v, max_string, max_list, depth + 1)
            out[k] = new_v
            truncated_any = truncated_any or child_truncated
        return out, truncated_any
    return value, False


def _truncate_string(value: str, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return value, False
    head = encoded[:max_bytes].decode("utf-8", errors="replace")
    return (
        f"{head}\n...<truncated, full size {len(encoded)} bytes>",
        True,
    )


def _truncate_list(
    value: list, max_string: int, max_list: int, depth: int
) -> tuple[list, bool]:
    truncated_any = False
    if len(value) > max_list:
        kept = value[:max_list]
        truncated_any = True
        out = []
        for item in kept:
            new_item, child_truncated = _walk(item, max_string, max_list, depth + 1)
            out.append(new_item)
            truncated_any = truncated_any or child_truncated
        out.append(
            {"_truncated": len(value) - max_list, "_total": len(value)}
        )
        return out, truncated_any
    out = []
    for item in value:
        new_item, child_truncated = _walk(item, max_string, max_list, depth + 1)
        out.append(new_item)
        truncated_any = truncated_any or child_truncated
    return out, truncated_any
