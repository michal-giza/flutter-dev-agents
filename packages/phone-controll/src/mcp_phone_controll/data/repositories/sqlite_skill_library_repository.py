"""Voyager-style skill library — SQLite-persistent reusable tool sequences.

Wang et al., 2023 ("Voyager", arXiv:2305.16291) showed lifelong-learning
agents accumulate a skill library that compounds over time. The agent
takes a successful sequence of low-level actions, names it, and recalls
it later as a single high-level "skill."

Our applied form: capture a successful slice of the session trace
(e.g. the seven calls that constitute "boot a debug session") under a
human-readable name. Subsequent agents call `recall_skill_library` to
list available skills and `replay_skill(name)` to re-execute the
sequence.

The library is per-process by default; opt into cross-session
persistence with `MCP_SKILL_LIBRARY_DB`.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ...domain.result import Result, ok

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    sequence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    use_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0
);
"""


class SqliteSkillLibraryRepository:
    """A simple, persistent skill library keyed by skill name.

    Skills are sequences of (tool_name, args_template) pairs. `args_template`
    is a JSON dict; values starting with `$` are placeholder variables the
    caller fills at replay time. This keeps skills reusable across slightly
    different contexts (different `package_id`, different `serial`) without
    requiring real templating.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    async def promote(
        self,
        name: str,
        description: str,
        sequence: list[dict],
    ) -> Result[None]:
        """Store a named sequence; replaces existing skill of the same name."""
        async with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO skills
                        (name, description, sequence_json, created_at,
                         last_used_at, use_count, success_count)
                    VALUES (?, ?, ?, ?, NULL, 0, 0)
                    """,
                    (
                        name,
                        description,
                        json.dumps(sequence),
                        datetime.now().isoformat(),
                    ),
                )
        return ok(None)

    async def list_skills(self) -> Result[list[dict]]:
        async with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT name, description, sequence_json, created_at,
                           last_used_at, use_count, success_count
                    FROM skills ORDER BY use_count DESC, name ASC
                    """
                ).fetchall()
        return ok(
            [
                {
                    "name": r[0],
                    "description": r[1],
                    "sequence": json.loads(r[2]),
                    "created_at": r[3],
                    "last_used_at": r[4],
                    "use_count": r[5],
                    "success_count": r[6],
                    "success_rate": (r[6] / r[5]) if r[5] else None,
                }
                for r in rows
            ]
        )

    async def fetch(self, name: str) -> Result[dict | None]:
        async with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT name, description, sequence_json FROM skills WHERE name=?",
                    (name,),
                ).fetchone()
        if row is None:
            return ok(None)
        return ok(
            {
                "name": row[0],
                "description": row[1],
                "sequence": json.loads(row[2]),
            }
        )

    async def record_use(self, name: str, success: bool) -> Result[None]:
        async with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE skills
                    SET use_count = use_count + 1,
                        success_count = success_count + ?,
                        last_used_at = ?
                    WHERE name = ?
                    """,
                    (1 if success else 0, datetime.now().isoformat(), name),
                )
        return ok(None)

    async def delete(self, name: str) -> Result[None]:
        async with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM skills WHERE name=?", (name,))
        return ok(None)
