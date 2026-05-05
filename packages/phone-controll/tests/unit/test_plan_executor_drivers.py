"""Tests for the new flutter_test driver, enriched error envelopes, and
self-describing plan_schema in describe_capabilities.

Covers the gaps surfaced by the live smoke against the user's checkaiapp project.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.static_capabilities_provider import (
    StaticCapabilitiesProvider,
)
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
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.base import NoParams
from mcp_phone_controll.domain.usecases.discovery import DescribeCapabilities
from mcp_phone_controll.domain.usecases.plan import (
    ValidateTestPlan,
    ValidateTestPlanParams,
)
from mcp_phone_controll.infrastructure.yaml_plan_loader import YamlPlanLoader


# ----- flutter_test driver -------------------------------------------------


@pytest.mark.asyncio
async def test_flutter_test_driver_calls_run_integration_tests():
    """The new flutter_test driver dispatches `run_integration_tests` (not patrol)."""
    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(name: str, args):
        calls.append((name, dict(args or {})))
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(fake_dispatch)
    plan = TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="flutter-only",
        device_platform="android",
        device_pool=None,
        project_path=Path("/work/myapp"),
        phases=(
            PlanPhase(phase="PRE_FLIGHT"),
            PlanPhase(
                phase="UNDER_TEST",
                driver=PhaseDriver(
                    kind="flutter_test", target="integration_test/auth_test.dart"
                ),
            ),
        ),
    )
    res = await executor.run(plan)
    assert isinstance(res, Ok)
    assert any(c[0] == "run_integration_tests" for c in calls)
    invoked = next(c for c in calls if c[0] == "run_integration_tests")
    assert invoked[1]["test_path"] == "integration_test/auth_test.dart"
    assert invoked[1]["project_path"] == "/work/myapp"


@pytest.mark.asyncio
async def test_flutter_test_driver_requires_project_path():
    async def fake_dispatch(name, args):
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(fake_dispatch)
    plan = TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="missing-path",
        device_platform="android",
        device_pool=None,
        project_path=None,
        phases=(
            PlanPhase(
                phase="UNDER_TEST",
                driver=PhaseDriver(kind="flutter_test", target="x.dart"),
            ),
        ),
    )
    res = await executor.run(plan)
    assert isinstance(res, Ok)
    blocked = next(o for o in res.value.phases if o.phase == "VERDICT_BLOCKED")
    assert blocked.error_code == "InvalidArgumentFailure"


# ----- enriched error envelopes -------------------------------------------


@pytest.mark.asyncio
async def test_unknown_phase_suggests_verdict_variants():
    async def noop_dispatch(name, args):
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(noop_dispatch)
    plan = TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="bad-phase",
        device_platform="android",
        device_pool=None,
        project_path=None,
        phases=(PlanPhase(phase="VERDICT"),),
    )
    res = await executor.run(plan)
    assert isinstance(res, Ok)
    bad = next(o for o in res.value.phases if o.actual_outcome == "unknown_phase")
    assert "VERDICT_DECLINED" in (bad.error_message or "")
    assert "VERDICT_BLOCKED" in (bad.error_message or "")


@pytest.mark.asyncio
async def test_missing_driver_lists_valid_kinds_and_example():
    async def noop_dispatch(name, args):
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(noop_dispatch)
    plan = TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="no-driver",
        device_platform="android",
        device_pool=None,
        project_path=None,
        phases=(PlanPhase(phase="UMP_GATE"),),
    )
    res = await executor.run(plan)
    assert isinstance(res, Ok)
    bad = next(o for o in res.value.phases if o.actual_outcome == "missing_driver")
    msg = bad.error_message or ""
    for kind in VALID_DRIVER_KINDS:
        assert kind in msg
    assert "Example" in msg
    assert "kind: flutter_test" in msg


@pytest.mark.asyncio
async def test_unknown_driver_kind_lists_valid_kinds():
    async def noop_dispatch(name, args):
        return {"ok": True, "data": None}

    executor = YamlPlanExecutor(noop_dispatch)
    plan = TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="bad-driver",
        device_platform="android",
        device_pool=None,
        project_path=Path("/x"),
        phases=(
            PlanPhase(
                phase="UNDER_TEST",
                driver=PhaseDriver(kind="madeup_kind", target="x"),
            ),
        ),
    )
    res = await executor.run(plan)
    assert isinstance(res, Ok)
    bad = next(o for o in res.value.phases if o.actual_outcome == "unknown_driver")
    for kind in VALID_DRIVER_KINDS:
        assert kind in (bad.error_message or "")


# ----- describe_capabilities now self-documents plans ----------------------


@pytest.mark.asyncio
async def test_describe_capabilities_includes_plan_schema():
    uc = DescribeCapabilities(StaticCapabilitiesProvider())
    res = await uc(NoParams())
    assert isinstance(res, Ok)
    schema = res.value.plan_schema
    assert isinstance(schema, dict)
    assert schema["version"] == "phone-controll/v1"
    assert "PRE_FLIGHT" in schema["valid_phases"]
    assert "VERDICT_DECLINED" in schema["valid_phases"]
    assert "flutter_test" in schema["valid_driver_kinds"]
    assert "patrol_test" in schema["valid_driver_kinds"]
    assert "minimal_plan_yaml" in schema
    # the minimal example should round-trip through the loader
    loader = YamlPlanLoader()
    parsed = loader.load_str(schema["minimal_plan_yaml"])
    assert isinstance(parsed, Ok)


# ----- validate_test_plan -------------------------------------------------


@pytest.mark.asyncio
async def test_validate_test_plan_accepts_valid_yaml():
    uc = ValidateTestPlan(YamlPlanLoader())
    valid = (
        "apiVersion: phone-controll/v1\n"
        "kind: TestPlan\n"
        "metadata: { name: x }\n"
        "spec:\n"
        "  device: { platform: android, pool: any }\n"
        "  project: { path: . }\n"
        "  phases: [ { phase: PRE_FLIGHT } ]\n"
    )
    res = await uc(ValidateTestPlanParams(plan_yaml=valid))
    assert isinstance(res, Ok)
    assert res.value.name == "x"


@pytest.mark.asyncio
async def test_validate_test_plan_rejects_invalid_yaml():
    uc = ValidateTestPlan(YamlPlanLoader())
    res = await uc(ValidateTestPlanParams(plan_yaml="apiVersion: bogus/v0\nkind: x"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_validate_test_plan_requires_input():
    uc = ValidateTestPlan(YamlPlanLoader())
    res = await uc(ValidateTestPlanParams())
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ----- self-consistency check -------------------------------------------


def test_valid_phases_and_drivers_match_implementation():
    """The constants exposed in the executor and the schema published in
    describe_capabilities must agree."""
    schema = StaticCapabilitiesProvider()
    # imported here so we use the same module reference
    from mcp_phone_controll.data.repositories.static_capabilities_provider import (
        _PLAN_SCHEMA,
    )

    assert tuple(_PLAN_SCHEMA["valid_driver_kinds"]) == VALID_DRIVER_KINDS
    assert tuple(_PLAN_SCHEMA["valid_phases"]) == VALID_PHASES
