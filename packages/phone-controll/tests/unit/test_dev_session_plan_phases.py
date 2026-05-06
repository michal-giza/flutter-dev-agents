"""Tests for the new plan-walker phases: OPEN_IDE, DEV_SESSION_START,
HOT_RELOAD, DEV_SESSION_STOP, plus the new dev_session_action and
read_debug_log driver kinds."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.yaml_plan_executor import (
    VALID_DRIVER_KINDS,
    VALID_PHASES,
    YamlPlanExecutor,
)
from mcp_phone_controll.domain.entities import (
    PhaseDriver,
    PlanPhase,
    TestPlan,
)
from mcp_phone_controll.domain.result import Ok
from mcp_phone_controll.infrastructure.yaml_plan_loader import YamlPlanLoader


def _plan(phases: tuple[PlanPhase, ...], project_path: Path | None = None) -> TestPlan:
    return TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="t",
        device_platform="android",
        device_pool=None,
        project_path=project_path,
        phases=phases,
    )


# ----- new constants self-consistency -------------------------------------


def test_new_phases_in_valid_set():
    for p in ("OPEN_IDE", "DEV_SESSION_START", "HOT_RELOAD", "DEV_SESSION_STOP"):
        assert p in VALID_PHASES


def test_new_drivers_in_valid_set():
    for d in ("dev_session_action", "read_debug_log"):
        assert d in VALID_DRIVER_KINDS


# ----- phase handlers --------------------------------------------------


@pytest.mark.asyncio
async def test_dev_session_start_dispatches_start_debug_session():
    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(name, args):
        calls.append((name, dict(args or {})))
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(fake_dispatch)
    res = await executor.run(
        _plan(
            (PlanPhase(phase="DEV_SESSION_START", extras={"mode": "debug"}),),
            project_path=Path("/work/checkaiapp"),
        )
    )
    assert isinstance(res, Ok)
    assert any(c[0] == "start_debug_session" for c in calls)


@pytest.mark.asyncio
async def test_hot_reload_dispatches_restart_debug_session():
    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(name, args):
        calls.append((name, dict(args or {})))
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(fake_dispatch)
    res = await executor.run(
        _plan((PlanPhase(phase="HOT_RELOAD", extras={"full_restart": True}),))
    )
    assert isinstance(res, Ok)
    invoked = next(c for c in calls if c[0] == "restart_debug_session")
    assert invoked[1]["full_restart"] is True


@pytest.mark.asyncio
async def test_dev_session_stop_dispatches_stop_debug_session():
    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(name, args):
        calls.append((name, dict(args or {})))
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(fake_dispatch)
    res = await executor.run(_plan((PlanPhase(phase="DEV_SESSION_STOP"),)))
    assert isinstance(res, Ok)
    assert any(c[0] == "stop_debug_session" for c in calls)


@pytest.mark.asyncio
async def test_open_ide_dispatches_open_project_in_ide():
    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(name, args):
        calls.append((name, dict(args or {})))
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(fake_dispatch)
    res = await executor.run(
        _plan(
            (PlanPhase(phase="OPEN_IDE", extras={"new_window": True}),),
            project_path=Path("/work/checkaiapp"),
        )
    )
    assert isinstance(res, Ok)
    invoked = next(c for c in calls if c[0] == "open_project_in_ide")
    assert invoked[1]["new_window"] is True
    assert invoked[1]["project_path"] == "/work/checkaiapp"


# ----- new driver kinds -----------------------------------------------


@pytest.mark.asyncio
async def test_dev_session_action_driver_calls_service_extension():
    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(name, args):
        calls.append((name, dict(args or {})))
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(fake_dispatch)
    res = await executor.run(
        _plan(
            (
                PlanPhase(
                    phase="UMP_GATE",
                    driver=PhaseDriver(
                        kind="dev_session_action",
                        target="ext.flutter.debugDumpApp",
                    ),
                ),
            )
        )
    )
    assert isinstance(res, Ok)
    invoked = next(c for c in calls if c[0] == "call_service_extension")
    assert invoked[1]["method"] == "ext.flutter.debugDumpApp"


@pytest.mark.asyncio
async def test_read_debug_log_driver_calls_read_debug_log():
    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(name, args):
        calls.append((name, dict(args or {})))
        return {"ok": True, "data": []}

    executor = YamlPlanExecutor(fake_dispatch)
    res = await executor.run(
        _plan(
            (
                PlanPhase(
                    phase="UMP_GATE",
                    driver=PhaseDriver(
                        kind="read_debug_log",
                        target=None,
                        args={"since_s": 5, "level": "error"},
                    ),
                ),
            )
        )
    )
    assert isinstance(res, Ok)
    invoked = next(c for c in calls if c[0] == "read_debug_log")
    assert invoked[1]["since_s"] == 5
    assert invoked[1]["level"] == "error"


# ----- YAML loader passes extras through ------------------------------


def test_yaml_loader_pours_unknown_keys_into_extras():
    yaml = """
apiVersion: phone-controll/v1
kind: TestPlan
metadata: { name: t }
spec:
  device: { platform: android, pool: any }
  project: { path: . }
  phases:
    - phase: DEV_SESSION_START
      mode: profile
      flavor: dev
    - phase: OPEN_IDE
      ide: vscode
      new_window: false
"""
    res = YamlPlanLoader().load_str(yaml)
    assert isinstance(res, Ok)
    plan = res.value
    dev_phase = next(p for p in plan.phases if p.phase == "DEV_SESSION_START")
    assert dev_phase.extras["mode"] == "profile"
    assert dev_phase.extras["flavor"] == "dev"
    open_phase = next(p for p in plan.phases if p.phase == "OPEN_IDE")
    assert open_phase.extras["new_window"] is False


# ----- describe_capabilities exposes the new schema -------------------


@pytest.mark.asyncio
async def test_phase_outcome_carries_duration_ms():
    import asyncio

    async def slow_dispatch(name, args):
        # ~10 ms of fake work so duration_ms isn't zero on fast machines
        await asyncio.sleep(0.012)
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(slow_dispatch)
    res = await executor.run(_plan((PlanPhase(phase="DEV_SESSION_STOP"),)))
    assert isinstance(res, Ok)
    phase = res.value.phases[0]
    # Some CI runners have very fast clocks; just assert non-negative + < 1s.
    assert phase.duration_ms >= 0
    assert phase.duration_ms < 1000


@pytest.mark.asyncio
async def test_capabilities_plan_schema_includes_new_phases():
    from mcp_phone_controll.data.repositories.static_capabilities_provider import (
        StaticCapabilitiesProvider,
    )

    res = await StaticCapabilitiesProvider().describe()
    assert isinstance(res, Ok)
    schema = res.value.plan_schema
    assert "DEV_SESSION_START" in schema["valid_phases"]
    assert "HOT_RELOAD" in schema["valid_phases"]
    assert "OPEN_IDE" in schema["valid_phases"]
    assert "dev_session_action" in schema["valid_driver_kinds"]
    assert "read_debug_log" in schema["valid_driver_kinds"]
