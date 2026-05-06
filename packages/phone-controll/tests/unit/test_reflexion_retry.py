"""Reflexion-style retry on retryable phase failures.

The plan walker normally walks straight to VERDICT_BLOCKED on any phase
failure. With `reflexion_retries > 0`, it inserts a REFLECTION pseudo-
phase whose `notes` carry the diagnosis, then retries the failed phase
up to N times. If a retry succeeds, the run continues normally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.yaml_plan_executor import (
    YamlPlanExecutor,
)
from mcp_phone_controll.domain.entities import (
    PhaseDriver,
    PlanPhase,
    TestPlan,
)


def _plan_under_test() -> TestPlan:
    return TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="t",
        device_platform=None,
        device_pool=None,
        project_path=Path("/tmp/fake-project"),
        phases=(
            PlanPhase(phase="PRE_FLIGHT"),
            PlanPhase(
                phase="UNDER_TEST",
                driver=PhaseDriver(kind="patrol_test", target="x.dart"),
            ),
        ),
    )


class _FlakyDispatch:
    """Fake `_dispatch(name, args)` that fails the patrol_test the first
    `fail_count` times and succeeds afterwards."""

    def __init__(self, fail_count: int):
        self._fail_count = fail_count
        self._calls = 0

    async def __call__(self, name, args):
        if name == "run_patrol_test":
            self._calls += 1
            if self._calls <= self._fail_count:
                return {
                    "ok": False,
                    "error": {
                        "code": "TestExecutionFailure",
                        "message": "boom",
                        "next_action": "capture_diagnostics",
                    },
                }
            return {"ok": True, "data": {"passed": 1, "failed": 0}}
        # PRE_FLIGHT and friends always succeed in this fake.
        return {"ok": True, "data": {}}


@pytest.mark.asyncio
async def test_no_retry_when_disabled_blocks_immediately():
    dispatch = _FlakyDispatch(fail_count=99)
    executor = YamlPlanExecutor(dispatch, reflexion_retries=0)
    res = await executor.run(_plan_under_test())
    assert res.is_ok
    phases = [p.phase for p in res.value.phases]
    assert "VERDICT_BLOCKED" in phases
    assert "REFLECTION" not in phases
    # Failed once, no retries.
    assert dispatch._calls == 1


@pytest.mark.asyncio
async def test_reflexion_retries_recover_when_attempts_eventually_succeed():
    dispatch = _FlakyDispatch(fail_count=1)  # fails once, succeeds on retry
    executor = YamlPlanExecutor(dispatch, reflexion_retries=2)
    res = await executor.run(_plan_under_test())
    assert res.is_ok
    phases = [p.phase for p in res.value.phases]
    # We should see REFLECTION before the successful retry.
    assert "REFLECTION" in phases
    assert "VERDICT_BLOCKED" not in phases
    # Run continued past the recovered failure.
    assert res.value.overall_ok is True
    assert dispatch._calls == 2


@pytest.mark.asyncio
async def test_reflexion_exhausts_retries_then_blocks():
    dispatch = _FlakyDispatch(fail_count=99)
    executor = YamlPlanExecutor(dispatch, reflexion_retries=2)
    res = await executor.run(_plan_under_test())
    assert res.is_ok
    phases = [p.phase for p in res.value.phases]
    assert phases.count("REFLECTION") == 2
    assert "VERDICT_BLOCKED" in phases
    # Original failure + 2 retries = 3 dispatch calls.
    assert dispatch._calls == 3


@pytest.mark.asyncio
async def test_reflection_notes_carry_failure_diagnosis():
    dispatch = _FlakyDispatch(fail_count=99)
    executor = YamlPlanExecutor(dispatch, reflexion_retries=1)
    res = await executor.run(_plan_under_test())
    assert res.is_ok
    reflections = [p for p in res.value.phases if p.phase == "REFLECTION"]
    assert reflections
    assert "TestExecutionFailure" in (reflections[0].notes or "")
