"""SessionTraceRepository backed by SQLite.

Persists every dispatcher call across MCP-process restarts. Useful when:

  - the user restarts Claude Code mid-session and wants to reconstruct
    "what did the agent already do" (replays don't replay side effects,
    but the audit shows the path)
  - a CI pipeline wants to post-mortem failed runs
  - tool_usage_report aggregates over more than the in-memory ring

The schema is intentionally trivial — `args` and `summary` are JSON-encoded
strings. Read-back time scales linearly with row count, but typical
sessions are under 1000 rows.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ...domain.entities import SessionTrace, TraceEntry
from ...domain.repositories import SessionTraceRepository
from ...domain.result import Result, ok

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    args_json TEXT NOT NULL,
    ok INTEGER NOT NULL,
    error_code TEXT,
    summary TEXT NOT NULL,
    artifact_paths_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session ON trace_entries(session_id, sequence);
"""


class SqliteSessionTraceRepository(SessionTraceRepository):
    def __init__(self, db_path: Path, session_id: str) -> None:
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_id = session_id
        self._lock = asyncio.Lock()
        self._sequence = 0
        self._started_at = datetime.now()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            row = conn.execute(
                "SELECT MAX(sequence) FROM trace_entries WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if row and row[0] is not None:
                self._sequence = int(row[0])

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    async def record(self, entry: TraceEntry) -> Result[None]:
        async with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO trace_entries
                        (session_id, sequence, tool_name, args_json, ok,
                         error_code, summary, artifact_paths_json, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self._session_id,
                        entry.sequence,
                        entry.tool_name,
                        json.dumps(entry.args, default=str),
                        1 if entry.ok else 0,
                        entry.error_code,
                        entry.summary,
                        json.dumps(list(entry.artifact_paths)),
                        datetime.now().isoformat(),
                    ),
                )
        return ok(None)

    async def summary(self, session_id: str | None = None) -> Result[SessionTrace]:
        sid = session_id or self._session_id
        async with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT sequence, tool_name, args_json, ok, error_code,
                           summary, artifact_paths_json
                    FROM trace_entries
                    WHERE session_id=?
                    ORDER BY sequence ASC
                    """,
                    (sid,),
                ).fetchall()
        entries = tuple(
            TraceEntry(
                sequence=int(seq),
                tool_name=str(tn),
                args=json.loads(aj),
                ok=bool(ok_),
                error_code=ec,
                summary=str(s),
                artifact_paths=tuple(json.loads(ap)),
            )
            for seq, tn, aj, ok_, ec, s, ap in rows
        )
        return ok(
            SessionTrace(
                session_id=sid,
                started_at=self._started_at,
                entries=entries,
            )
        )

    async def reset(self) -> Result[None]:
        async with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM trace_entries WHERE session_id=?",
                    (self._session_id,),
                )
            self._sequence = 0
            self._started_at = datetime.now()
        return ok(None)
