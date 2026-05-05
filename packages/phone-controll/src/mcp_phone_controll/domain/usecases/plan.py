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
        return ok(plan_res.value)
