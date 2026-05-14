"""Structured logging — opt-in JSON lines for ops + Datadog/Honeycomb ingest.

Default behaviour stays human-readable (one line per event, like the
existing boot self-check). Set `MCP_LOG_FORMAT=json` to switch to
JSON-line output. Every log call goes through `emit(event, **fields)`
so we never have free-form `print` statements once this is wired in.

Fields:
  - event   short event name (snake_case)
  - level   info | warn | error
  - ts      ISO-8601 timestamp
  - pid     process id (so multi-MCP factories can be untangled)
  - msg     human-readable rendering when level=warn|error
  - **kw    arbitrary structured fields

JSON example:
  {"event":"image_cap_failed","level":"warn","ts":"2026-05-14T18:14:22.103Z",
   "pid":78788,"path":"/sessions/s1/shot.png","reason":"all backends failed"}

Text example (default):
  [phone-controll WARN] image_cap_failed path=/sessions/s1/shot.png ...

Disable entirely with MCP_QUIET=1 (used by the test suite).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

_PID = os.getpid()


def _format_mode() -> str:
    if os.environ.get("MCP_QUIET") == "1":
        return "off"
    if os.environ.get("MCP_LOG_FORMAT", "").lower() == "json":
        return "json"
    return "text"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def emit(event: str, level: str = "info", **fields: Any) -> None:
    """One log event. Routed to stderr in the configured format.

    `event` should be a snake_case identifier that names the kind of
    thing happening (not a human sentence — that's what `msg` is for).
    """
    mode = _format_mode()
    if mode == "off":
        return
    record: dict[str, Any] = {
        "event": event,
        "level": level,
        "ts": _now_iso(),
        "pid": _PID,
        **fields,
    }
    if mode == "json":
        sys.stderr.write(json.dumps(record, default=str) + "\n")
        sys.stderr.flush()
        return
    # Human-readable: [phone-controll LEVEL] event k1=v1 k2=v2 ...
    extras = " ".join(f"{k}={v}" for k, v in fields.items())
    label = f"[phone-controll {level.upper()}]"
    sys.stderr.write(f"{label} {event} {extras}\n".rstrip() + "\n")
    sys.stderr.flush()


# Convenience wrappers.
def info(event: str, **fields: Any) -> None:
    emit(event, level="info", **fields)


def warn(event: str, **fields: Any) -> None:
    emit(event, level="warn", **fields)


def error(event: str, **fields: Any) -> None:
    emit(event, level="error", **fields)
