"""narrate — turn a tool envelope into a one-line prose summary.

Small LLMs forget to summarise. The agent ladder + plan walker emit a
trail of structured envelopes; `narrate` converts each into a sentence so
the final report is readable without re-parsing JSON.

Pure function: no I/O. Same input always yields same output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..result import Result, ok
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class NarrateParams:
    envelope: dict
    tool: str | None = None      # optional tool name for richer phrasing


def _short(value: Any, limit: int = 80) -> str:
    s = str(value)
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def narrate_envelope(envelope: dict, tool: str | None = None) -> str:
    """Render `envelope` as a one-line summary suitable for human eyes."""
    label = tool or "tool"
    if envelope.get("ok"):
        data = envelope.get("data")
        truncated = " (truncated)" if envelope.get("data_truncated") else ""
        if isinstance(data, list):
            return f"{label} ✓ returned {len(data)} item(s){truncated}"
        if isinstance(data, dict):
            keys = list(data.keys())[:4]
            return f"{label} ✓ returned object with keys {keys}{truncated}"
        if data is None:
            return f"{label} ✓"
        return f"{label} ✓ {_short(data)}{truncated}"
    err = envelope.get("error") or {}
    code = err.get("code", "Failure")
    msg = _short(err.get("message", ""), 100)
    next_action = err.get("next_action")
    suffix = f" → {next_action}" if next_action else ""
    return f"{label} ✗ {code}: {msg}{suffix}"


class Narrate(BaseUseCase[NarrateParams, str]):
    async def execute(self, params: NarrateParams) -> Result[str]:
        return ok(narrate_envelope(params.envelope, params.tool))
