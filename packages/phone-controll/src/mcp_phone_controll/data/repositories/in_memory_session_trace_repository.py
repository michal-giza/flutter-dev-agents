"""SessionTraceRepository — in-memory ring of TraceEntry per process.

Lightweight on purpose: every dispatcher call appends one entry; agents call
session_summary to read the trace back. Persistence is a future addition.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from ...domain.entities import SessionTrace, TraceEntry
from ...domain.repositories import SessionTraceRepository
from ...domain.result import Result, ok


class InMemorySessionTraceRepository(SessionTraceRepository):
    def __init__(self, max_entries: int = 500) -> None:
        self._entries: list[TraceEntry] = []
        self._started_at = datetime.now()
        self._max = max_entries
        self._lock = asyncio.Lock()
        self._sequence = 0

    async def record(self, entry: TraceEntry) -> Result[None]:
        async with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max :]
        return ok(None)

    async def summary(self, session_id: str | None = None) -> Result[SessionTrace]:
        async with self._lock:
            entries = tuple(self._entries)
        return ok(
            SessionTrace(
                session_id=session_id or "current",
                started_at=self._started_at,
                entries=entries,
            )
        )

    async def reset(self) -> Result[None]:
        async with self._lock:
            self._entries.clear()
            self._started_at = datetime.now()
            self._sequence = 0
        return ok(None)

    def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence
