"""SQLite-persistent session trace — survives process restarts."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.sqlite_session_trace_repository import (
    SqliteSessionTraceRepository,
)
from mcp_phone_controll.domain.entities import TraceEntry


@pytest.mark.asyncio
async def test_records_and_reads_back_entries(tmp_path: Path):
    db = tmp_path / "trace.db"
    repo = SqliteSessionTraceRepository(db_path=db, session_id="s1")
    seq = repo.next_sequence()
    await repo.record(
        TraceEntry(
            sequence=seq,
            tool_name="select_device",
            args={"serial": "EMU01"},
            ok=True,
            error_code=None,
            summary="ok",
        )
    )
    res = await repo.summary()
    assert res.is_ok
    entries = res.value.entries
    assert len(entries) == 1
    assert entries[0].tool_name == "select_device"
    assert entries[0].args == {"serial": "EMU01"}


@pytest.mark.asyncio
async def test_persists_across_repo_instances(tmp_path: Path):
    db = tmp_path / "trace.db"
    repo1 = SqliteSessionTraceRepository(db_path=db, session_id="s1")
    await repo1.record(
        TraceEntry(
            sequence=repo1.next_sequence(),
            tool_name="list_devices",
            args={},
            ok=True,
            error_code=None,
            summary="ok",
        )
    )

    # Simulate a process restart by creating a fresh repo at the same db.
    repo2 = SqliteSessionTraceRepository(db_path=db, session_id="s1")
    res = await repo2.summary()
    assert res.is_ok
    assert len(res.value.entries) == 1
    # Sequence resumes from where the previous one left off.
    assert repo2.next_sequence() == 2


@pytest.mark.asyncio
async def test_separates_sessions(tmp_path: Path):
    db = tmp_path / "trace.db"
    repo_a = SqliteSessionTraceRepository(db_path=db, session_id="A")
    repo_b = SqliteSessionTraceRepository(db_path=db, session_id="B")
    await repo_a.record(
        TraceEntry(
            sequence=repo_a.next_sequence(),
            tool_name="x",
            args={},
            ok=True,
            error_code=None,
            summary="ok",
        )
    )
    res_b = await repo_b.summary()
    assert res_b.is_ok
    assert res_b.value.entries == ()
