"""Semantic validation of test plans — ordering and prerequisite checks."""

from __future__ import annotations

from mcp_phone_controll.domain.entities import PhaseDriver, PlanPhase, TestPlan
from mcp_phone_controll.domain.usecases.plan import _validate_plan_semantics


def _plan(*phases: PlanPhase) -> TestPlan:
    return TestPlan(
        api_version="phone-controll/v1",
        kind="TestPlan",
        name="t",
        device_platform=None,
        device_pool=None,
        project_path=None,
        phases=tuple(phases),
    )


def test_under_test_without_starter_is_error():
    plan = _plan(
        PlanPhase(phase="UNDER_TEST", driver=PhaseDriver(kind="patrol_test")),
    )
    errors, _ = _validate_plan_semantics(plan)
    assert any("UNDER_TEST" in e for e in errors)


def test_hot_reload_without_dev_session_is_error():
    plan = _plan(PlanPhase(phase="PRE_FLIGHT"), PlanPhase(phase="HOT_RELOAD"))
    errors, _ = _validate_plan_semantics(plan)
    assert any("HOT_RELOAD" in e for e in errors)


def test_under_test_missing_driver_is_error():
    plan = _plan(
        PlanPhase(phase="PRE_FLIGHT"),
        PlanPhase(phase="UNDER_TEST"),  # no driver
    )
    errors, _ = _validate_plan_semantics(plan)
    assert any("driver" in e for e in errors)


def test_dev_session_start_without_stop_warns():
    plan = _plan(
        PlanPhase(phase="PRE_FLIGHT"),
        PlanPhase(phase="DEV_SESSION_START"),
    )
    errors, warnings = _validate_plan_semantics(plan)
    assert errors == []
    assert any("never stops it" in w for w in warnings)


def test_clean_dev_loop_validates():
    plan = _plan(
        PlanPhase(phase="PRE_FLIGHT"),
        PlanPhase(phase="DEV_SESSION_START"),
        PlanPhase(phase="HOT_RELOAD"),
        PlanPhase(phase="UNDER_TEST", driver=PhaseDriver(kind="flutter_test")),
        PlanPhase(phase="DEV_SESSION_STOP"),
    )
    errors, _ = _validate_plan_semantics(plan)
    assert errors == []


def test_duplicate_pre_flight_warns():
    plan = _plan(
        PlanPhase(phase="PRE_FLIGHT"),
        PlanPhase(phase="PRE_FLIGHT"),
    )
    _, warnings = _validate_plan_semantics(plan)
    assert any("PRE_FLIGHT" in w and "2" in w for w in warnings)


def test_empty_plan_is_error():
    plan = _plan()
    errors, _ = _validate_plan_semantics(plan)
    assert any("no phases" in e for e in errors)
