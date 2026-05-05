"""Parse `flutter run --machine` daemon-protocol output.

The daemon emits JSON arrays on stdout, one per line, framed as `[<obj>]`.
Each object is either:
  - An event:   `{"event": "app.start", "params": {...}}`
  - A response: `{"id": <int>, "result": <any>}` or `{"id": <int>, "error": "..."}`

This parser is pure — it consumes a single line and returns a typed shape.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ...domain.entities import DebugLogEntry


def parse_machine_line(raw: str) -> list[dict[str, Any]]:
    """Parse one line of `flutter run --machine` stdout.

    Returns the list of JSON objects on the line (typically 0 or 1). Lines
    that aren't valid JSON arrays (status text, banners) parse to []."""
    line = raw.strip()
    if not line.startswith("["):
        return []
    try:
        decoded = json.loads(line)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]


def event_to_log(event: dict[str, Any]) -> DebugLogEntry | None:
    """Convert a daemon event dict into a DebugLogEntry, if it's log-shaped.

    Returns None for non-log events (app.start, app.started, app.progress, etc).
    """
    name = event.get("event")
    params = event.get("params") or {}
    now = datetime.now()

    if name == "app.log":
        return DebugLogEntry(
            timestamp=now,
            level="error" if params.get("error") else "info",
            source="app",
            message=str(params.get("log") or params.get("message") or ""),
            isolate_id=params.get("isolateId"),
        )
    if name == "daemon.logMessage":
        level = str(params.get("level", "info")).lower()
        return DebugLogEntry(
            timestamp=now,
            level=level,
            source="daemon",
            message=str(params.get("message", "")),
        )
    if name == "app.progress":
        message = params.get("message") or params.get("id") or ""
        if not message:
            return None
        return DebugLogEntry(
            timestamp=now, level="progress", source="daemon", message=str(message)
        )
    if name == "app.stop":
        return DebugLogEntry(
            timestamp=now, level="info", source="app", message="app stopped"
        )
    return None


def app_id_from_started(event: dict[str, Any]) -> str | None:
    """Extract the appId from an app.started event."""
    if event.get("event") != "app.started":
        return None
    params = event.get("params") or {}
    app_id = params.get("appId")
    return str(app_id) if app_id else None


def vm_service_uri_from_started(event: dict[str, Any]) -> str | None:
    """Extract VM service URI (debugger / vm-service) from app.debugPort or app.started."""
    if event.get("event") not in ("app.started", "app.debugPort"):
        return None
    params = event.get("params") or {}
    return params.get("wsUri") or params.get("uri")
