"""Durable record of debug sessions across MCP-server restarts.

The problem (field-reported "gap #6"): the debug-session registry lived
only in the MCP process's memory, so restarting the tool server orphaned
still-alive sessions — the Flutter app and its VM Service kept running,
but `list_debug_sessions` came back empty and there was no way to
re-attach.

This store persists just the *metadata* needed to re-attach — crucially
the VM Service ws URI — to a small JSON file. On the next start the
repository reloads it and, for each record whose VM Service is still
reachable, revives an attached session (VM-Service-only: service
extensions / widget-tree / vm_evaluate work; hot reload does not, since
the `flutter --machine` daemon connection didn't survive). Dead records
are pruned.

Not persisted: the live daemon client / websocket — those can't outlive
the process. Only the reconnection coordinates.

Concurrency: read-modify-write on every mutation (atomic temp+rename),
keyed by session id, so two MCP processes sharing the file don't clobber
each other's records.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _default_path() -> Path:
    override = os.environ.get("MCP_DEBUG_SESSIONS_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".mcp_phone_controll" / "debug_sessions.json"


class DebugSessionStore:
    """JSON-file registry of debug-session records (id → metadata dict).

    Records are plain dicts with at least `id` and `vm_service_uri`;
    the repository owns the schema. Every method is best-effort and never
    raises on a missing/corrupt file — a broken registry must never block
    starting a fresh session.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_path()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> list[dict[str, Any]]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [r for r in data if isinstance(r, dict) and r.get("id")]

    def upsert(self, record: dict[str, Any]) -> None:
        """Add or replace the record with this `id`. Read-modify-write so a
        concurrent process's records survive."""
        rid = record.get("id")
        if not rid:
            return
        records = [r for r in self.load() if r.get("id") != rid]
        records.append(record)
        self._write(records)

    def remove(self, session_id: str) -> None:
        records = [r for r in self.load() if r.get("id") != session_id]
        self._write(records)

    def _write(self, records: list[dict[str, Any]]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic: write a temp file in the same dir, then rename.
            fd, tmp = tempfile.mkstemp(
                dir=str(self._path.parent), prefix=".debug_sessions.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(records, f, indent=2)
                os.replace(tmp, self._path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        except OSError:
            # Persistence is best-effort; never fail a session op over it.
            pass
