"""Voyager-style skill library — promote, list, replay reusable sequences.

Three use cases:

  - `PromoteSequence` — tag a slice of the current session trace as a
    named, reusable skill. Description is human-readable.
  - `ListSkills` — return every skill in the library, sorted by use count.
  - `ReplaySkill` — execute a stored sequence through the dispatcher,
    returning a per-step trace. Records success/failure on the library.

Wang et al., 2023 (arXiv:2305.16291) — lifelong-learning agents
accumulate skills; reusing them dominates re-discovering them every
session. Our applied form is one tier coarser (named macros, not
parametric programs), which fits the small-LLM regime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..failures import InvalidArgumentFailure
from ..repositories import SessionTraceRepository, SkillLibraryRepository
from ..result import Err, Result, err, ok
from .base import BaseUseCase, NoParams


@dataclass(frozen=True, slots=True)
class PromoteSequenceParams:
    name: str
    description: str
    from_sequence: int | None = None    # earliest trace `sequence` to include
    to_sequence: int | None = None      # latest trace `sequence` to include
    only_ok: bool = True                # promote only successful steps


@dataclass(frozen=True, slots=True)
class PromotedSkill:
    name: str
    description: str
    steps: int


class PromoteSequence(BaseUseCase[PromoteSequenceParams, PromotedSkill]):
    """Promote a slice of the current session trace into a named skill."""

    def __init__(
        self,
        traces: SessionTraceRepository,
        library: SkillLibraryRepository,
    ) -> None:
        self._traces = traces
        self._library = library

    async def execute(
        self, params: PromoteSequenceParams
    ) -> Result[PromotedSkill]:
        if not params.name.strip() or " " in params.name:
            return err(
                InvalidArgumentFailure(
                    message="skill name must be non-empty and contain no spaces",
                    next_action="fix_arguments",
                    details={
                        "corrected_example": {
                            "name": "boot_debug_session",
                            "description": "Open IDE, lock device, start flutter run --machine",
                        }
                    },
                )
            )
        summary_res = await self._traces.summary(None)
        if isinstance(summary_res, Err):
            return summary_res
        entries = summary_res.value.entries
        # Filter by sequence window + ok flag.
        sliced = []
        for entry in entries:
            if params.from_sequence is not None and entry.sequence < params.from_sequence:
                continue
            if params.to_sequence is not None and entry.sequence > params.to_sequence:
                continue
            if params.only_ok and not entry.ok:
                continue
            sliced.append(entry)
        # Skip entries that recall the library itself or list/discovery
        # tools — we don't want skills full of `describe_capabilities`.
        skip_tools = {
            "describe_capabilities",
            "describe_tool",
            "session_summary",
            "tool_usage_report",
            "narrate",
            "summarize_session",
            "promote_sequence",
            "list_skills",
            "replay_skill",
        }
        sequence: list[dict] = [
            {"tool": e.tool_name, "args": dict(e.args)}
            for e in sliced
            if e.tool_name not in skip_tools
        ]
        if not sequence:
            return err(
                InvalidArgumentFailure(
                    message="no eligible entries to promote",
                    next_action="fix_arguments",
                    details={
                        "hint": "broaden from/to_sequence or set only_ok=false",
                        "trace_size": len(entries),
                    },
                )
            )
        save_res = await self._library.promote(
            params.name, params.description, sequence
        )
        if isinstance(save_res, Err):
            return save_res
        return ok(
            PromotedSkill(
                name=params.name,
                description=params.description,
                steps=len(sequence),
            )
        )


class ListSkills(BaseUseCase[NoParams, list[dict]]):
    def __init__(self, library: SkillLibraryRepository) -> None:
        self._library = library

    async def execute(self, _params: NoParams) -> Result[list[dict]]:
        return await self._library.list_skills()


@dataclass(frozen=True, slots=True)
class ReplaySkillParams:
    name: str
    overrides: dict | None = None       # placeholder substitutions ($-prefixed)


@dataclass(frozen=True, slots=True)
class ReplayResult:
    skill: str
    steps_total: int
    steps_ok: int
    success: bool
    failed_at: int | None
    last_envelope_summary: str | None


class ReplaySkill(BaseUseCase[ReplaySkillParams, ReplayResult]):
    """Re-execute a stored skill through the dispatcher.

    `overrides` lets the caller substitute placeholder values (any arg
    starting with `$`) at replay time. Skill stops on first ok=false,
    records the result on the library so the agent can prefer high-
    success-rate skills next time (Voyager's "skill library curation").
    """

    def __init__(self, library: SkillLibraryRepository, dispatcher_call) -> None:
        self._library = library
        self._call = dispatcher_call

    async def execute(self, params: ReplaySkillParams) -> Result[ReplayResult]:
        skill_res = await self._library.fetch(params.name)
        if isinstance(skill_res, Err):
            return skill_res
        if skill_res.value is None:
            return err(
                InvalidArgumentFailure(
                    message=f"unknown skill {params.name!r}",
                    next_action="list_skills",
                )
            )
        sequence = skill_res.value["sequence"]
        overrides = params.overrides or {}
        ok_count = 0
        failed_at: int | None = None
        last_summary: str | None = None
        for idx, step in enumerate(sequence):
            args = _apply_overrides(step.get("args") or {}, overrides)
            envelope = await self._call(step["tool"], args)
            ok_step = bool(envelope.get("ok"))
            last_summary = (
                "ok"
                if ok_step
                else (envelope.get("error") or {}).get("code", "error")
            )
            if ok_step:
                ok_count += 1
            else:
                failed_at = idx
                break
        success = failed_at is None
        await self._library.record_use(params.name, success)
        return ok(
            ReplayResult(
                skill=params.name,
                steps_total=len(sequence),
                steps_ok=ok_count,
                success=success,
                failed_at=failed_at,
                last_envelope_summary=last_summary,
            )
        )


def _apply_overrides(args: dict, overrides: dict) -> dict:
    out: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str) and value.startswith("$") and value[1:] in overrides:
            out[key] = overrides[value[1:]]
        else:
            out[key] = value
    return out
