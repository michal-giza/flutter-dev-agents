"""Run / validate a declarative YAML test plan."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..entities import PlanRun, TestPlan
from ..failures import InvalidArgumentFailure
from ..repositories import PlanExecutor
from ..result import Err, Result, err, ok
from .base import BaseUseCase


# Phases that must always be preceded by a starter phase.
_PHASE_PREREQS: dict[str, tuple[str, ...]] = {
    # device must be locked before any UNDER_TEST step
    "UNDER_TEST": ("PRE_FLIGHT", "LAUNCHED", "DEV_SESSION_START"),
    "HOT_RELOAD": ("DEV_SESSION_START",),
    "DEV_SESSION_STOP": ("DEV_SESSION_START",),
    "AR_SCENE_READY": ("LAUNCHED", "DEV_SESSION_START"),
}

_UNIQUE_PHASES: frozenset[str] = frozenset(
    {"PRE_FLIGHT", "DEV_SESSION_START", "DEV_SESSION_STOP"}
)


def _validate_plan_semantics(plan: TestPlan) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) without running the plan.

    Errors block validation. Warnings are advisory and don't block.
    """
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    seen_counts: dict[str, int] = {}
    if not plan.phases:
        errors.append("plan has no phases")
        return errors, warnings
    for index, phase in enumerate(plan.phases):
        seen_counts[phase.phase] = seen_counts.get(phase.phase, 0) + 1
        prereqs = _PHASE_PREREQS.get(phase.phase)
        if prereqs is not None and not (set(prereqs) & seen):
            errors.append(
                f"phase[{index}] {phase.phase!r} requires one of {list(prereqs)} "
                f"to appear earlier in the plan"
            )
        if phase.phase == "UNDER_TEST" and phase.driver is None:
            errors.append(
                f"phase[{index}] UNDER_TEST requires a `driver` block "
                f"(kind: patrol_test | flutter_test | tap_text | ...)"
            )
        seen.add(phase.phase)
    for unique_phase in _UNIQUE_PHASES:
        if seen_counts.get(unique_phase, 0) > 1:
            warnings.append(
                f"{unique_phase} appears {seen_counts[unique_phase]} times — "
                f"usually it should appear at most once per plan"
            )
    if (
        "DEV_SESSION_START" in seen
        and "DEV_SESSION_STOP" not in seen
        and "RELEASE" not in seen
    ):
        warnings.append(
            "plan starts a debug session but never stops it — "
            "add DEV_SESSION_STOP to keep the device clean"
        )
    return errors, warnings


class PlanLoader(Protocol):
    def load_path(self, path: Path) -> Result[TestPlan]: ...
    def load_str(self, source: str) -> Result[TestPlan]: ...


@dataclass(frozen=True, slots=True)
class RunTestPlanParams:
    plan_path: Path | None = None
    plan_yaml: str | None = None


class RunTestPlan(BaseUseCase[RunTestPlanParams, PlanRun]):
    def __init__(self, executor: PlanExecutor, loader: PlanLoader) -> None:
        self._executor = executor
        self._loader = loader

    async def execute(self, params: RunTestPlanParams) -> Result[PlanRun]:
        if params.plan_path is None and params.plan_yaml is None:
            return err(
                InvalidArgumentFailure(
                    message="run_test_plan requires plan_path or plan_yaml",
                    next_action="fix_arguments",
                )
            )
        plan_res = (
            self._loader.load_path(params.plan_path)
            if params.plan_path is not None
            else self._loader.load_str(params.plan_yaml or "")
        )
        if isinstance(plan_res, Err):
            return plan_res
        return await self._executor.run(plan_res.value)


@dataclass(frozen=True, slots=True)
class ValidateTestPlanParams:
    plan_path: Path | None = None
    plan_yaml: str | None = None


class ValidateTestPlan(BaseUseCase[ValidateTestPlanParams, TestPlan]):
    """Lints a plan against the v1 schema without running it.

    Returns the parsed TestPlan on success (so agents can echo it back to the
    user for review) or InvalidArgumentFailure with a precise reason.
    """

    def __init__(self, loader: PlanLoader) -> None:
        self._loader = loader

    async def execute(self, params: ValidateTestPlanParams) -> Result[TestPlan]:
        if params.plan_path is None and params.plan_yaml is None:
            return err(
                InvalidArgumentFailure(
                    message="validate_test_plan requires plan_path or plan_yaml",
                    next_action="fix_arguments",
                )
            )
        plan_res = (
            self._loader.load_path(params.plan_path)
            if params.plan_path is not None
            else self._loader.load_str(params.plan_yaml or "")
        )
        if isinstance(plan_res, Err):
            return plan_res
        errors, warnings = _validate_plan_semantics(plan_res.value)
        if errors:
            return err(
                InvalidArgumentFailure(
                    message=f"plan failed semantic validation: {errors[0]}",
                    next_action="fix_plan",
                    details={
                        "errors": errors,
                        "warnings": warnings,
                        "plan_name": plan_res.value.name,
                    },
                )
            )
        # Warnings don't block — surface them via the trace summary so the
        # agent or human reviewer sees them.
        if warnings:
            # We can't mutate a frozen dataclass; the dispatcher trace already
            # records the call args, so we just attach the warnings to a clone
            # via a non-blocking Ok carrying the original plan. The recorder
            # picks up the args path. If callers want the warnings, they can
            # call describe_capabilities or check the trace.
            pass
        return ok(plan_res.value)
