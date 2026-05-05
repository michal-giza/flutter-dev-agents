"""PlanExecutor — walks a TestPlan, enforcing entry/exit, capturing artifacts.

Architecture:
  The executor consumes the same use cases the MCP exposes — it is not a fork.
  Phases map to existing operations:
    PRE_FLIGHT     → check_environment + new_session
    CLEAN          → prepare_for_test
    LAUNCHED       → launch_app + wait_for_element on key/text
    <GATE>         → driver (patrol_test | tap_text)
    UNDER_TEST     → driver (patrol_test)
    VERDICT_*      → capture phase: screenshot + read_logs + STOP

Decline branches (planned_outcome="decline") naturally lead to VERDICT_DECLINED;
the executor refuses to advance past such a phase.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ...domain.entities import (
    PhaseOutcome,
    PlanPhase,
    PlanRun,
    TestPlan,
)
from ...domain.failures import InvalidArgumentFailure, PlanExecutionFailure
from ...domain.repositories import PlanExecutor
from ...domain.result import Err, Result, err, ok


VALID_DRIVER_KINDS = ("patrol_test", "flutter_test", "tap_text", "noop")
VALID_PHASES = (
    "PRE_FLIGHT", "CLEAN", "LAUNCHED",
    "<NAME>_GATE", "UNDER_TEST",
    "VERDICT_DECLINED", "VERDICT_BLOCKED",
)
_TERMINAL_PHASES = ("VERDICT_DECLINED", "VERDICT_BLOCKED", "REPORT")


class YamlPlanExecutor(PlanExecutor):
    """Plan interpreter wired to the same UseCases the MCP dispatches.

    To keep DI simple, takes a callable ``run_tool(name, args) -> envelope`` so
    it can call any registered tool without holding direct references to every
    use case. The container wires this to the real ToolDispatcher.
    """

    def __init__(self, dispatcher_call) -> None:
        self._call = dispatcher_call

    async def run(self, plan: TestPlan) -> Result[PlanRun]:
        started = datetime.now()
        outcomes: list[PhaseOutcome] = []
        terminal_reached = False

        for phase in plan.phases:
            if terminal_reached:
                outcomes.append(
                    PhaseOutcome(
                        phase=phase.phase,
                        ok=False,
                        planned_outcome=phase.planned_outcome,
                        actual_outcome="skipped_after_terminal",
                        notes="A previous phase reached a terminal state.",
                    )
                )
                continue

            outcome = await self._run_phase(plan, phase)
            outcomes.append(outcome)

            if not outcome.ok:
                outcomes.append(
                    PhaseOutcome(
                        phase="VERDICT_BLOCKED",
                        ok=False,
                        planned_outcome=None,
                        actual_outcome="blocked",
                        error_code=outcome.error_code,
                        error_message=outcome.error_message,
                    )
                )
                terminal_reached = True
                continue

            if (
                phase.phase in _TERMINAL_PHASES
                or phase.planned_outcome in ("decline", "decided")
            ):
                terminal_reached = True

        finished = datetime.now()
        overall_ok = all(o.ok for o in outcomes if o.phase not in ("VERDICT_BLOCKED",))
        return ok(
            PlanRun(
                plan_name=plan.name,
                started_at=started,
                finished_at=finished,
                overall_ok=overall_ok,
                phases=tuple(outcomes),
            )
        )

    # ---------- per-phase implementations ----------

    async def _run_phase(self, plan: TestPlan, phase: PlanPhase) -> PhaseOutcome:
        phase_name = phase.phase
        try:
            if phase_name == "PRE_FLIGHT":
                return await self._pre_flight(phase)
            if phase_name == "CLEAN":
                return await self._clean(phase)
            if phase_name == "LAUNCHED":
                return await self._launched(phase)
            if phase_name.endswith("_GATE") or phase_name == "UNDER_TEST":
                return await self._driver_phase(plan, phase)
            if phase_name == "VERDICT_DECLINED" or phase_name == "VERDICT_BLOCKED":
                return await self._verdict(phase)
            # Friendly hint when the user wrote "VERDICT" without a suffix.
            hint = (
                "did you mean VERDICT_DECLINED or VERDICT_BLOCKED?"
                if phase_name == "VERDICT" or phase_name.startswith("VERDICT")
                else f"valid phases: {list(VALID_PHASES)}"
            )
            return PhaseOutcome(
                phase=phase_name,
                ok=False,
                planned_outcome=phase.planned_outcome,
                actual_outcome="unknown_phase",
                error_code="InvalidArgumentFailure",
                error_message=f"unknown phase {phase_name!r} — {hint}",
            )
        except Exception as e:  # noqa: BLE001 — boundary
            return PhaseOutcome(
                phase=phase_name,
                ok=False,
                planned_outcome=phase.planned_outcome,
                actual_outcome="raised",
                error_code=type(e).__name__,
                error_message=str(e),
            )

    async def _pre_flight(self, phase: PlanPhase) -> PhaseOutcome:
        env = await self._call("check_environment", {})
        if not env["ok"]:
            return self._fail(phase, env)
        sess = await self._call("new_session", {"label": f"plan-{phase.notes or 'run'}"})
        if not sess["ok"]:
            return self._fail(phase, sess)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome="ready",
        )

    async def _clean(self, phase: PlanPhase) -> PhaseOutcome:
        if not phase.package_id:
            return PhaseOutcome(
                phase=phase.phase, ok=False,
                planned_outcome=phase.planned_outcome,
                actual_outcome="missing_package_id",
                error_code="InvalidArgumentFailure",
                error_message="CLEAN phase requires package_id",
            )
        res = await self._call("prepare_for_test", {"package_id": phase.package_id})
        if not res["ok"]:
            return self._fail(phase, res)
        artifacts = ()
        if isinstance(res.get("data"), dict) and res["data"].get("evidence_screenshot"):
            artifacts = (res["data"]["evidence_screenshot"],)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome="clean", artifacts=artifacts,
        )

    async def _launched(self, phase: PlanPhase) -> PhaseOutcome:
        if not phase.package_id:
            return PhaseOutcome(
                phase=phase.phase, ok=False,
                planned_outcome=phase.planned_outcome,
                actual_outcome="missing_package_id",
                error_code="InvalidArgumentFailure",
                error_message="LAUNCHED phase requires package_id",
            )
        launch = await self._call("launch_app", {"package_id": phase.package_id})
        if not launch["ok"]:
            return self._fail(phase, launch)
        if phase.wait_for_key or phase.wait_for_text:
            args: dict[str, Any] = {"timeout_s": phase.timeout_s or 15.0}
            if phase.wait_for_key:
                args["resource_id"] = phase.wait_for_key
            if phase.wait_for_text:
                args["text"] = phase.wait_for_text
            wait = await self._call("wait_for_element", args)
            if not wait["ok"]:
                return self._fail(phase, wait)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome="launched",
        )

    async def _driver_phase(self, plan: TestPlan, phase: PlanPhase) -> PhaseOutcome:
        if phase.driver is None:
            example = (
                "  driver:\n    kind: flutter_test          # or patrol_test, tap_text, noop\n"
                "    target: integration_test/auth_test.dart"
            )
            return PhaseOutcome(
                phase=phase.phase, ok=False,
                planned_outcome=phase.planned_outcome,
                actual_outcome="missing_driver",
                error_code="InvalidArgumentFailure",
                error_message=(
                    f"phase {phase.phase} requires a driver. "
                    f"Valid kinds: {list(VALID_DRIVER_KINDS)}. Example:\n{example}"
                ),
            )
        kind = phase.driver.kind
        if kind == "patrol_test":
            project = phase.project_path or (str(plan.project_path) if plan.project_path else None)
            if not project:
                return PhaseOutcome(
                    phase=phase.phase, ok=False,
                    planned_outcome=phase.planned_outcome,
                    actual_outcome="missing_project_path",
                    error_code="InvalidArgumentFailure",
                    error_message="patrol_test driver needs project_path (set on phase or top-level spec.project.path)",
                )
            args = {"project_path": project, "test_path": phase.driver.target}
            res = await self._call("run_patrol_test", args)
        elif kind == "flutter_test":
            project = phase.project_path or (str(plan.project_path) if plan.project_path else None)
            if not project:
                return PhaseOutcome(
                    phase=phase.phase, ok=False,
                    planned_outcome=phase.planned_outcome,
                    actual_outcome="missing_project_path",
                    error_code="InvalidArgumentFailure",
                    error_message="flutter_test driver needs project_path (set on phase or top-level spec.project.path)",
                )
            target = str(phase.driver.target) if phase.driver.target else "integration_test/"
            args = {"project_path": project, "test_path": target}
            res = await self._call("run_integration_tests", args)
        elif kind == "tap_text":
            res = await self._call("tap_text", {"text": phase.driver.target or ""})
        elif kind == "noop":
            res = {"ok": True, "data": "noop"}
        else:
            return PhaseOutcome(
                phase=phase.phase, ok=False,
                planned_outcome=phase.planned_outcome,
                actual_outcome="unknown_driver",
                error_code="InvalidArgumentFailure",
                error_message=(
                    f"unknown driver kind {kind!r}. "
                    f"Valid kinds: {list(VALID_DRIVER_KINDS)}"
                ),
            )
        if not res["ok"]:
            return self._fail(phase, res)
        artifacts = await self._capture(phase)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome=phase.planned_outcome or "passed",
            artifacts=artifacts,
        )

    async def _verdict(self, phase: PlanPhase) -> PhaseOutcome:
        artifacts = await self._capture(phase)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome="terminal", artifacts=artifacts,
        )

    async def _capture(self, phase: PlanPhase) -> tuple[str, ...]:
        captured: list[str] = []
        for kind in phase.capture:
            if kind == "screenshot":
                res = await self._call("take_screenshot", {"label": phase.phase})
                if res["ok"] and isinstance(res["data"], str):
                    captured.append(res["data"])
            elif kind == "logs":
                await self._call("read_logs", {"since_s": 5, "min_level": "I"})
                # logs are returned inline; we don't persist them as files here yet
            elif kind == "ui_dump":
                await self._call("dump_ui", {})
        return tuple(captured)

    def _fail(self, phase: PlanPhase, envelope: dict) -> PhaseOutcome:
        err_obj = envelope.get("error") or {}
        return PhaseOutcome(
            phase=phase.phase,
            ok=False,
            planned_outcome=phase.planned_outcome,
            actual_outcome="failed",
            error_code=err_obj.get("code"),
            error_message=err_obj.get("message"),
        )
