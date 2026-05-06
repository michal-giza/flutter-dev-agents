"""Tests for autonomy primitives: capabilities, session_summary, prepare_for_test,
the YAML plan loader, and the YamlPlanExecutor against a fake dispatcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.in_memory_session_trace_repository import (
    InMemorySessionTraceRepository,
)
from mcp_phone_controll.data.repositories.static_capabilities_provider import (
    StaticCapabilitiesProvider,
)
from mcp_phone_controll.data.repositories.yaml_plan_executor import YamlPlanExecutor
from mcp_phone_controll.domain.entities import (
    PhaseDriver,
    PlanPhase,
    TestPlan,
    TraceEntry,
)
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.base import NoParams
from mcp_phone_controll.domain.usecases.discovery import (
    DescribeCapabilities,
    SessionSummary,
    SessionSummaryParams,
)
from mcp_phone_controll.domain.usecases.plan import RunTestPlan, RunTestPlanParams
from mcp_phone_controll.domain.usecases.preparation import (
    PrepareForTest,
    PrepareForTestParams,
)
from mcp_phone_controll.infrastructure.yaml_plan_loader import YamlPlanLoader
from tests.fakes.fake_repositories import (
    FakeArtifactRepository,
    FakeLifecycleRepository,
    FakeObservationRepository,
    FakeSessionStateRepository,
    FakeUiRepository,
)


# -- capabilities ----------------------------------------------------------


@pytest.mark.asyncio
async def test_describe_capabilities_includes_core_surfaces():
    from mcp_phone_controll.domain.usecases.discovery import (
        DescribeCapabilitiesParams,
    )
    uc = DescribeCapabilities(StaticCapabilitiesProvider())
    res = await uc(DescribeCapabilitiesParams())
    assert isinstance(res, Ok)
    cap = res.value
    assert "android" in cap.platforms
    assert "ios" in cap.platforms
    assert "patrol" in cap.test_frameworks
    assert "UMP" in cap.gates_handled
    names = {c.name for c in cap.capabilities}
    assert {"adb", "patrol", "test_plans", "session_trace"} <= names


# -- session trace ---------------------------------------------------------


@pytest.mark.asyncio
async def test_session_trace_round_trips():
    repo = InMemorySessionTraceRepository()
    for i in range(3):
        await repo.record(
            TraceEntry(
                sequence=repo.next_sequence(),
                tool_name=f"tool_{i}",
                args={"i": i},
                ok=True,
                error_code=None,
                summary="ok",
            )
        )
    uc = SessionSummary(repo)
    res = await uc(SessionSummaryParams())
    assert isinstance(res, Ok)
    assert len(res.value.entries) == 3
    assert res.value.entries[0].tool_name == "tool_0"


# -- prepare_for_test ------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_for_test_runs_full_clean_sequence(tmp_path: Path):
    lifecycle = FakeLifecycleRepository(name="droid")
    ui = FakeUiRepository(name="droid")
    observation = FakeObservationRepository(name="droid")
    artifacts = FakeArtifactRepository(root=tmp_path)
    state = FakeSessionStateRepository(serial="EMU01")
    uc = PrepareForTest(lifecycle, ui, observation, artifacts, state)

    res = await uc(PrepareForTestParams(package_id="pl.openclaw.myapp"))
    assert isinstance(res, Ok)
    assert "stop_app" in res.value.actions_run
    assert "clear_app_data" in res.value.actions_run
    assert "press_key_home" in res.value.actions_run
    assert "take_screenshot" in res.value.actions_run
    assert res.value.evidence_screenshot is not None


@pytest.mark.asyncio
async def test_prepare_for_test_skip_clear_on_ios(tmp_path: Path):
    lifecycle = FakeLifecycleRepository()
    ui = FakeUiRepository()
    observation = FakeObservationRepository()
    artifacts = FakeArtifactRepository(root=tmp_path)
    state = FakeSessionStateRepository(serial="UDID01")
    uc = PrepareForTest(lifecycle, ui, observation, artifacts, state)

    res = await uc(
        PrepareForTestParams(package_id="com.example.ios", skip_clear=True)
    )
    assert isinstance(res, Ok)
    assert "clear_app_data" not in res.value.actions_run


# -- YAML plan loader ------------------------------------------------------


VALID_PLAN_YAML = """
apiVersion: phone-controll/v1
kind: TestPlan
metadata: { name: ump-decline-smoke }
spec:
  device:    { platform: android, pool: any }
  project:   { path: . }
  phases:
    - { phase: PRE_FLIGHT }
    - { phase: CLEAN, package_id: pl.openclaw.myapp }
    - { phase: LAUNCHED, package_id: pl.openclaw.myapp, wait_for_key: splashLogo, timeout_s: 15 }
    - phase: UMP_GATE
      driver: { kind: patrol_test, target: integration_test/ump_decline_test.dart }
      planned_outcome: decline
    - phase: VERDICT_DECLINED
      capture: [screenshot, logs]
  report: { format: junit }
"""


def test_yaml_plan_loader_parses_valid_v1():
    loader = YamlPlanLoader()
    res = loader.load_str(VALID_PLAN_YAML)
    assert isinstance(res, Ok)
    plan = res.value
    assert plan.name == "ump-decline-smoke"
    assert plan.device_platform == "android"
    assert len(plan.phases) == 5
    ump = next(p for p in plan.phases if p.phase == "UMP_GATE")
    assert ump.driver is not None and ump.driver.kind == "patrol_test"
    assert ump.planned_outcome == "decline"
    verdict = next(p for p in plan.phases if p.phase == "VERDICT_DECLINED")
    assert verdict.capture == ("screenshot", "logs")


def test_yaml_plan_loader_rejects_unknown_api_version():
    loader = YamlPlanLoader()
    res = loader.load_str(VALID_PLAN_YAML.replace("phone-controll/v1", "v0"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


def test_yaml_plan_loader_rejects_missing_phases():
    loader = YamlPlanLoader()
    res = loader.load_str(
        "apiVersion: phone-controll/v1\nkind: TestPlan\nmetadata: { name: x }\nspec: {}\n"
    )
    assert isinstance(res, Err)
    assert "phases" in res.failure.message


# -- YamlPlanExecutor ------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_executor_walks_phases_and_stops_after_decline():
    """The executor must stop driving after a planned-decline phase."""
    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(name: str, args):
        calls.append((name, dict(args or {})))
        if name == "take_screenshot":
            return {"ok": True, "data": "/tmp/fake.png"}
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(fake_dispatch)
    plan = TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="decline-smoke",
        device_platform="android",
        device_pool=None,
        project_path=Path("/proj"),
        phases=(
            PlanPhase(phase="PRE_FLIGHT"),
            PlanPhase(phase="CLEAN", package_id="com.x"),
            PlanPhase(phase="LAUNCHED", package_id="com.x", wait_for_key="splash", timeout_s=5),
            PlanPhase(
                phase="UMP_GATE",
                driver=PhaseDriver(kind="patrol_test", target="integration_test/ump.dart"),
                planned_outcome="decline",
                capture=("screenshot",),
            ),
            PlanPhase(phase="UNDER_TEST", driver=PhaseDriver(kind="noop")),
        ),
    )
    res = await executor.run(plan)
    assert isinstance(res, Ok)
    run = res.value
    phase_names = [o.phase for o in run.phases]
    # UNDER_TEST must NOT have been executed (skipped after decline)
    under = next(o for o in run.phases if o.phase == "UNDER_TEST")
    assert under.actual_outcome == "skipped_after_terminal"
    # Concrete dispatcher calls — UMP triggered patrol_test, UNDER_TEST did not
    invoked = {c[0] for c in calls}
    assert "run_patrol_test" in invoked
    # No tool was called for the post-decline UNDER_TEST phase
    # (more than zero noop dispatch calls would be a regression)


@pytest.mark.asyncio
async def test_plan_executor_marks_blocked_on_phase_failure():
    async def fake_dispatch(name, args):
        if name == "launch_app":
            return {"ok": False, "error": {"code": "LaunchFailure", "message": "boom"}}
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(fake_dispatch)
    plan = TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="blocked",
        device_platform="android",
        device_pool=None,
        project_path=None,
        phases=(
            PlanPhase(phase="PRE_FLIGHT"),
            PlanPhase(phase="LAUNCHED", package_id="com.x"),
        ),
    )
    res = await executor.run(plan)
    assert isinstance(res, Ok)
    blocked = [o for o in res.value.phases if o.phase == "VERDICT_BLOCKED"]
    assert len(blocked) == 1
    assert blocked[0].error_code == "LaunchFailure"


# -- run_test_plan use case --------------------------------------------

@pytest.mark.asyncio
async def test_run_test_plan_use_case_dispatches_loader_and_executor(tmp_path: Path):
    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text(VALID_PLAN_YAML)

    from tests.fakes.fake_repositories import FakePlanExecutor

    loader = YamlPlanLoader()
    executor = FakePlanExecutor()
    uc = RunTestPlan(executor, loader)

    res = await uc(RunTestPlanParams(plan_path=plan_path))
    assert isinstance(res, Ok)
    assert executor.calls and executor.calls[0].name == "ump-decline-smoke"
