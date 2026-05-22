"""Tests for the v0.3.0 phase-11.5 senior-tester pre-write
discipline.

The tool encodes 8 principles from the senior-tester rubric:
AC-first, atomic, should_X_when_Y naming, builder pattern,
Gherkin discretion, exploratory charter, cross-cutting as
first-class, and the gap protocol.

These tests verify each principle is actually enforced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.design_test_plan import (
    DesignTestPlan,
    DesignTestPlanParams,
)


async def _run(**kwargs) -> Ok | Err:
    return await DesignTestPlan()(DesignTestPlanParams(**kwargs))


# ---- error handling ----------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_feature_kind_returns_failure():
    res = await _run(feature_kind="cryptocurrency")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_invalid_team_style_returns_failure():
    res = await _run(team_style="hybrid_remote_async")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_missing_project_path_returns_failure(tmp_path: Path):
    res = await _run(project_path=tmp_path / "does_not_exist")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ---- happy path: explicit ACs ------------------------------------------


@pytest.mark.asyncio
async def test_explicit_acs_produce_complete_grade():
    res = await _run(
        user_story="As a user I want to sign in to access my data",
        acceptance_criteria=(
            "User can sign in with valid credentials",
            "User cannot sign in with invalid credentials",
        ),
        feature_kind="auth",
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.grade == "complete"
    assert len(v.ac_coverage) == 2
    assert v.notes_for_afterwork == ()  # nothing to remember


# ---- AC-first discipline (principle 1) ---------------------------------


@pytest.mark.asyncio
async def test_each_ac_has_happy_negative_and_boundary_cases():
    """EP+BVA: every AC gets a happy path + 2-3 negatives + 2-3
    boundaries. The discipline is non-negotiable."""
    res = await _run(
        acceptance_criteria=("User can submit valid form input",),
        feature_kind="form",
    )
    assert isinstance(res, Ok)
    ac = res.value.ac_coverage[0]
    assert len(ac.happy_path) == 1
    assert len(ac.negative_cases) >= 2
    assert len(ac.boundary_cases) >= 3


# ---- naming convention (principle 3) -----------------------------------


@pytest.mark.asyncio
async def test_all_test_case_names_use_should_x_when_y():
    """Every generated TestCase name must start with `should_`."""
    res = await _run(
        acceptance_criteria=(
            "User can complete a payment",
            "Failed payment is recoverable",
        ),
        feature_kind="payment",
    )
    assert isinstance(res, Ok)
    for ac in res.value.ac_coverage:
        for case in ac.happy_path + ac.negative_cases + ac.boundary_cases:
            assert case.name.startswith("should_"), (
                f"Test name doesn't follow convention: {case.name}"
            )
    assert res.value.naming_convention == "should_X_when_Y"


# ---- test data factories (principle 4) ---------------------------------


@pytest.mark.asyncio
async def test_auth_feature_recommends_user_factory():
    res = await _run(
        acceptance_criteria=("User can sign in",),
        feature_kind="auth",
    )
    assert isinstance(res, Ok)
    factory_names = {f.factory_name for f in res.value.test_data_factories}
    assert "UserFactory" in factory_names


@pytest.mark.asyncio
async def test_payment_feature_recommends_order_factory():
    res = await _run(
        acceptance_criteria=("Order is paid for",),
        feature_kind="payment",
    )
    assert isinstance(res, Ok)
    factory_names = {f.factory_name for f in res.value.test_data_factories}
    assert "OrderFactory" in factory_names


@pytest.mark.asyncio
async def test_failure_factory_always_recommended():
    """Discipline #7 — every happy path needs a paired failure.
    The FailureFactory backs that, so it should always be present."""
    for kind in ("auth", "form", "list", "payment", "generic"):
        res = await _run(
            acceptance_criteria=("Test AC",),
            feature_kind=kind,
        )
        assert isinstance(res, Ok)
        factory_names = {
            f.factory_name for f in res.value.test_data_factories
        }
        assert "FailureFactory" in factory_names, (
            f"FailureFactory missing for feature_kind={kind}"
        )


# ---- Gherkin discretion (principle 5) ----------------------------------


@pytest.mark.asyncio
async def test_developer_heavy_team_does_not_use_gherkin():
    res = await _run(
        acceptance_criteria=("AC",),
        team_style="developer_heavy",
    )
    assert isinstance(res, Ok)
    assert res.value.use_gherkin is False
    # No E2E layer recommended
    layer_names = {layer.layer for layer in res.value.test_layers}
    assert "e2e" not in layer_names


@pytest.mark.asyncio
async def test_mixed_with_business_enables_gherkin():
    res = await _run(
        acceptance_criteria=("AC",),
        team_style="mixed_with_business",
    )
    assert isinstance(res, Ok)
    assert res.value.use_gherkin is True
    layer_names = {layer.layer for layer in res.value.test_layers}
    assert "e2e" in layer_names


# ---- exploratory charter (principle 6) ---------------------------------


@pytest.mark.asyncio
async def test_charter_always_present():
    """Every feature gets a charter — discipline #6."""
    res = await _run(acceptance_criteria=("AC",))
    assert isinstance(res, Ok)
    assert res.value.exploratory_charter is not None


@pytest.mark.asyncio
async def test_charter_respects_time_box():
    res = await _run(
        acceptance_criteria=("AC",),
        time_box_min=90,
    )
    assert isinstance(res, Ok)
    assert res.value.exploratory_charter.time_box_min == 90


@pytest.mark.asyncio
async def test_charter_time_box_min_15():
    """Even when caller passes a tiny time-box, the discipline
    enforces a sensible minimum."""
    res = await _run(
        acceptance_criteria=("AC",),
        time_box_min=2,
    )
    assert isinstance(res, Ok)
    assert res.value.exploratory_charter.time_box_min >= 15


@pytest.mark.asyncio
async def test_charter_expects_new_cases():
    res = await _run(acceptance_criteria=("AC",))
    assert isinstance(res, Ok)
    assert "2-3" in res.value.exploratory_charter.expected_outcomes


# ---- cross-cutting concerns (principle 7) ------------------------------


@pytest.mark.asyncio
async def test_cross_cutting_a11y_always_present():
    res = await _run(acceptance_criteria=("AC",))
    assert isinstance(res, Ok)
    concerns = {c.concern for c in res.value.cross_cutting_required}
    assert "a11y" in concerns
    assert "l10n" in concerns
    assert "lifecycle" in concerns


@pytest.mark.asyncio
async def test_cross_cutting_payment_adds_idempotency():
    res = await _run(
        acceptance_criteria=("Pay the order",),
        feature_kind="payment",
    )
    assert isinstance(res, Ok)
    concerns = {c.concern for c in res.value.cross_cutting_required}
    assert "idempotency" in concerns
    assert "audit" in concerns


@pytest.mark.asyncio
async def test_cross_cutting_auth_adds_session():
    res = await _run(
        acceptance_criteria=("Sign in",),
        feature_kind="auth",
    )
    assert isinstance(res, Ok)
    concerns = {c.concern for c in res.value.cross_cutting_required}
    assert "session" in concerns


# ---- gap protocol (principle 8) ----------------------------------------


@pytest.mark.asyncio
async def test_no_acs_engages_gap_protocol():
    """No ACs provided — must produce notes_for_afterwork."""
    res = await _run(
        user_story="User wants to do a thing",
        feature_kind="auth",
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.grade == "needs_acceptance_criteria"
    assert v.gaps != ()
    assert v.notes_for_afterwork != ()
    # Notes must mention reverse-engineering
    assert any(
        "reverse-engineer" in n.lower() or "afterwork" in n.lower()
        for n in v.notes_for_afterwork
    )


@pytest.mark.asyncio
async def test_no_acs_still_produces_test_plan():
    """Gap protocol: proceed but log. The plan is still useful,
    just flagged."""
    res = await _run(feature_kind="auth")
    assert isinstance(res, Ok)
    # Coverage should still be populated (heuristic ACs)
    assert len(res.value.ac_coverage) >= 3


@pytest.mark.asyncio
async def test_partial_grade_when_story_missing_but_acs_provided():
    res = await _run(
        acceptance_criteria=("Test AC",),
        feature_kind="generic",
    )
    assert isinstance(res, Ok)
    assert res.value.grade == "partial"
    assert any("user_story" in g.lower() for g in res.value.gaps)


# ---- test layers (principle 1 + 5) -------------------------------------


@pytest.mark.asyncio
async def test_unit_and_widget_layers_always_present():
    res = await _run(acceptance_criteria=("AC",))
    assert isinstance(res, Ok)
    layer_names = {layer.layer for layer in res.value.test_layers}
    assert "unit" in layer_names
    assert "widget" in layer_names


@pytest.mark.asyncio
async def test_payment_recommends_integration_layer():
    res = await _run(
        acceptance_criteria=("Pay the order",),
        feature_kind="payment",
    )
    assert isinstance(res, Ok)
    layer_names = {layer.layer for layer in res.value.test_layers}
    assert "integration" in layer_names


# ---- advice ------------------------------------------------------------


@pytest.mark.asyncio
async def test_advice_mentions_grade():
    res = await _run(
        user_story="Story",
        acceptance_criteria=("AC",),
    )
    assert isinstance(res, Ok)
    assert res.value.grade in res.value.advice


@pytest.mark.asyncio
async def test_advice_flags_reverse_engineered_acs():
    res = await _run(feature_kind="auth")
    assert isinstance(res, Ok)
    # Should warn about synthesized ACs
    assert "synthesised" in res.value.advice.lower() or "⚠" in res.value.advice
