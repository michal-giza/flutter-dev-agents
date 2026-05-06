"""Voyager-style skill library — promote / list / replay round-trip."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.sqlite_skill_library_repository import (
    SqliteSkillLibraryRepository,
)
from mcp_phone_controll.domain.entities import SessionTrace, TraceEntry
from mcp_phone_controll.domain.result import Err, ok
from mcp_phone_controll.domain.usecases.skill_library import (
    ListSkills,
    PromoteSequence,
    PromoteSequenceParams,
    ReplaySkill,
    ReplaySkillParams,
    _apply_overrides,
)


class _TraceRepo:
    def __init__(self, entries):
        self._entries = entries

    async def record(self, _e):
        return ok(None)

    async def summary(self, _sid=None):
        return ok(
            SessionTrace(
                session_id="s",
                started_at=datetime(2026, 1, 1),
                entries=tuple(self._entries),
            )
        )


def _entry(seq, name, ok_=True, args=None):
    return TraceEntry(
        sequence=seq,
        tool_name=name,
        args=args or {},
        ok=ok_,
        error_code=None,
        summary="ok",
    )


@pytest.mark.asyncio
async def test_promote_then_list_then_replay(tmp_path: Path):
    library = SqliteSkillLibraryRepository(tmp_path / "skills.db")
    entries = [
        _entry(1, "select_device", args={"serial": "EMU01"}),
        _entry(2, "new_session", args={"label": "boot"}),
        _entry(3, "start_debug_session", args={"project_path": "$proj"}),
        _entry(4, "describe_capabilities"),  # discovery — must be filtered out
    ]
    promote = PromoteSequence(_TraceRepo(entries), library)
    res = await promote.execute(
        PromoteSequenceParams(
            name="boot_debug_session",
            description="Lock device, open session, start flutter run --machine",
        )
    )
    assert res.is_ok
    assert res.value.steps == 3  # describe_capabilities filtered out

    listed = await ListSkills(library).execute(None)
    assert listed.is_ok
    names = [s["name"] for s in listed.value]
    assert "boot_debug_session" in names

    # Replay through a fake dispatcher; succeeds for every step.
    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(name, args):
        calls.append((name, dict(args)))
        return {"ok": True, "data": None}

    replay_res = await ReplaySkill(library, fake_dispatch).execute(
        ReplaySkillParams(
            name="boot_debug_session",
            overrides={"proj": "/Users/me/app"},
        )
    )
    assert replay_res.is_ok
    rep = replay_res.value
    assert rep.success is True
    assert rep.steps_total == 3
    assert rep.steps_ok == 3
    # Override substitution applied.
    assert calls[2][1]["project_path"] == "/Users/me/app"


@pytest.mark.asyncio
async def test_promote_rejects_invalid_name(tmp_path: Path):
    library = SqliteSkillLibraryRepository(tmp_path / "s.db")
    promote = PromoteSequence(_TraceRepo([_entry(1, "x")]), library)
    res = await promote.execute(
        PromoteSequenceParams(name="has spaces", description="x")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_promote_rejects_empty_window(tmp_path: Path):
    library = SqliteSkillLibraryRepository(tmp_path / "s.db")
    promote = PromoteSequence(_TraceRepo([]), library)
    res = await promote.execute(
        PromoteSequenceParams(name="never_called", description="x")
    )
    assert isinstance(res, Err)


@pytest.mark.asyncio
async def test_replay_unknown_skill(tmp_path: Path):
    library = SqliteSkillLibraryRepository(tmp_path / "s.db")

    async def dispatch(_n, _a):
        return {"ok": True}

    res = await ReplaySkill(library, dispatch).execute(
        ReplaySkillParams(name="missing_skill")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "list_skills"


@pytest.mark.asyncio
async def test_replay_records_failure(tmp_path: Path):
    library = SqliteSkillLibraryRepository(tmp_path / "s.db")
    await library.promote(
        "tap_then_verify",
        "two-step skill",
        [
            {"tool": "tap_text", "args": {"text": "Sign in"}},
            {"tool": "wait_for_element", "args": {"text": "Welcome"}},
        ],
    )

    async def dispatch(name, _a):
        return (
            {"ok": True}
            if name == "tap_text"
            else {"ok": False, "error": {"code": "UiElementNotFoundFailure"}}
        )

    res = await ReplaySkill(library, dispatch).execute(
        ReplaySkillParams(name="tap_then_verify")
    )
    assert res.is_ok
    rep = res.value
    assert rep.success is False
    assert rep.failed_at == 1
    assert rep.steps_ok == 1

    # The library should now show 1 use and 0 successes.
    listed = await library.list_skills()
    assert listed.is_ok
    skill = next(s for s in listed.value if s["name"] == "tap_then_verify")
    assert skill["use_count"] == 1
    assert skill["success_count"] == 0


def test_apply_overrides_substitutes_dollar_placeholders():
    out = _apply_overrides(
        {"a": "$proj", "b": "literal", "c": 5},
        {"proj": "/Users/me/x"},
    )
    assert out == {"a": "/Users/me/x", "b": "literal", "c": 5}
