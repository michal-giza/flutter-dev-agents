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


VALID_DRIVER_KINDS = (
    "patrol_test", "flutter_test", "tap_text", "noop",
    "dev_session_action", "read_debug_log",
)
VALID_PHASES = (
    "PRE_FLIGHT", "CLEAN", "LAUNCHED",
    "<NAME>_GATE", "UNDER_TEST",
    "VERDICT_DECLINED", "VERDICT_BLOCKED",
    "OPEN_IDE", "DEV_SESSION_START", "HOT_RELOAD", "DEV_SESSION_STOP",
    "AR_SCENE_READY",
    "REFLECTION",
)
_TERMINAL_PHASES = ("VERDICT_DECLINED", "VERDICT_BLOCKED", "REPORT")

# Phases where a Reflexion-style retry might recover. Pre-flight, lifecycle
# and dev-session phases are NOT retryable — a failure there usually means
# the env or device state is wrong and retrying just postpones the diagnosis.
_REFLEXION_RETRYABLE = ("UNDER_TEST", "HOT_RELOAD")


def _is_gate_phase(name: str) -> bool:
    return name.endswith("_GATE")


def _summarise_failure(outcome) -> str:
    """One-sentence diagnosis the executor stamps onto a REFLECTION outcome.

    Synthetic, deterministic — we don't call back into an LLM here; the
    purpose is to give the agent a structured artefact to read on retry,
    grounded in the actual error envelope.
    """
    code = outcome.error_code or "UnknownError"
    msg = (outcome.error_message or "").strip()
    if len(msg) > 200:
        msg = msg[:197] + "…"
    return f"phase={outcome.phase} failed: {code}: {msg}"


class YamlPlanExecutor(PlanExecutor):
    """Plan interpreter wired to the same UseCases the MCP dispatches.

    To keep DI simple, takes a callable ``run_tool(name, args) -> envelope`` so
    it can call any registered tool without holding direct references to every
    use case. The container wires this to the real ToolDispatcher.
    """

    def __init__(
        self, dispatcher_call, reflexion_retries: int = 0
    ) -> None:
        self._call = dispatcher_call
        # Reflexion-style retry budget per failed retryable phase. 0 = off.
        # Shinn et al., 2023 (arXiv:2303.11366): self-critique-and-retry
        # improves long-horizon task success.
        self._reflexion_retries = max(0, int(reflexion_retries))

    async def run(self, plan: TestPlan) -> Result[PlanRun]:
        started = datetime.now()
        outcomes: list[PhaseOutcome] = []
        terminal_reached = False

        import asyncio as _asyncio

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

            phase_started_at = _asyncio.get_event_loop().time()
            outcome = await self._run_phase(plan, phase)
            phase_duration_ms = int(
                (_asyncio.get_event_loop().time() - phase_started_at) * 1000
            )
            # PhaseOutcome is frozen — rebuild with duration_ms.
            from dataclasses import replace

            outcome = replace(outcome, duration_ms=phase_duration_ms)
            outcomes.append(outcome)

            if not outcome.ok:
                # Reflexion-style retry when configured and the failed phase
                # is retryable. Each retry is preceded by a REFLECTION pseudo-
                # phase whose `notes` capture the diagnosis from the prior
                # attempt — that way the trace shows what the agent "thought"
                # at each retry boundary.
                retried_ok = False
                if (
                    self._reflexion_retries > 0
                    and (
                        phase.phase in _REFLEXION_RETRYABLE
                        or _is_gate_phase(phase.phase)
                    )
                ):
                    diagnosis = _summarise_failure(outcome)
                    for attempt in range(1, self._reflexion_retries + 1):
                        outcomes.append(
                            PhaseOutcome(
                                phase="REFLECTION",
                                ok=True,
                                planned_outcome=None,
                                actual_outcome=f"retry_{attempt}_of_{self._reflexion_retries}",
                                notes=diagnosis,
                            )
                        )
                        retry_started = _asyncio.get_event_loop().time()
                        retry_outcome = await self._run_phase(plan, phase)
                        retry_duration_ms = int(
                            (_asyncio.get_event_loop().time() - retry_started) * 1000
                        )
                        retry_outcome = replace(
                            retry_outcome, duration_ms=retry_duration_ms
                        )
                        outcomes.append(retry_outcome)
                        if retry_outcome.ok:
                            retried_ok = True
                            outcome = retry_outcome
                            break
                        diagnosis = _summarise_failure(retry_outcome)
                if retried_ok:
                    # Mark the original failure as recovered so overall_ok
                    # treats the run as a pass while preserving the audit trail.
                    original_idx = -(2 * self._reflexion_retries) - 1
                    # Find the original failed outcome we recorded right
                    # before the retries began. It's the most-recent ok=False
                    # entry whose phase matches the retried one.
                    for idx in range(len(outcomes) - 1, -1, -1):
                        cand = outcomes[idx]
                        if (
                            cand.phase == phase.phase
                            and not cand.ok
                            and cand.actual_outcome != "retried_successfully"
                        ):
                            outcomes[idx] = replace(
                                cand,
                                actual_outcome="retried_successfully",
                                notes=(cand.notes or "") + " | recovered via Reflexion retry",
                            )
                            break
                    continue
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
        overall_ok = all(
            o.ok
            for o in outcomes
            if o.phase not in ("VERDICT_BLOCKED",)
            and o.actual_outcome != "retried_successfully"
        )
        duration_ms = int((finished - started).total_seconds() * 1000)
        plan_run = PlanRun(
            plan_name=plan.name,
            started_at=started,
            finished_at=finished,
            overall_ok=overall_ok,
            phases=tuple(outcomes),
            duration_ms=duration_ms,
        )

        # Emit JUnit XML when the plan asks for it. Best-effort — never fail the
        # run because of report I/O.
        if plan.report_format == "junit":
            try:
                from pathlib import Path

                from ...infrastructure.junit_writer import write_junit

                # Write next to the plan's project, under build/test-results,
                # falling back to ~/.mcp_phone_controll/reports if no project_path.
                if plan.project_path is not None:
                    out = Path(plan.project_path) / "build" / "test-results" / f"{plan.name}.junit.xml"
                else:
                    out = Path.home() / ".mcp_phone_controll" / "reports" / f"{plan.name}.junit.xml"
                write_junit(plan_run, out)
                # Replace the plan_run with one that knows where the report landed
                from dataclasses import replace as _replace

                plan_run = _replace(plan_run, junit_path=out)
            except Exception:  # noqa: BLE001 — never fail the plan because of report I/O
                pass

        return ok(plan_run)

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
            if phase_name == "OPEN_IDE":
                return await self._open_ide(plan, phase)
            if phase_name == "DEV_SESSION_START":
                return await self._dev_session_start(plan, phase)
            if phase_name == "HOT_RELOAD":
                return await self._hot_reload(phase)
            if phase_name == "DEV_SESSION_STOP":
                return await self._dev_session_stop(phase)
            if phase_name == "AR_SCENE_READY":
                return await self._ar_scene_ready(phase)
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
        elif kind == "dev_session_action":
            method = phase.driver.target or "ext.flutter.debugDumpApp"
            res = await self._call(
                "call_service_extension",
                {"method": method, "args": phase.driver.args or None},
            )
        elif kind == "read_debug_log":
            res = await self._call(
                "read_debug_log",
                {
                    "since_s": int((phase.driver.args or {}).get("since_s", 30)),
                    "level": (phase.driver.args or {}).get("level", "all"),
                    "max_lines": int((phase.driver.args or {}).get("max_lines", 200)),
                },
            )
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

    async def _open_ide(self, plan: TestPlan, phase: PlanPhase) -> PhaseOutcome:
        project = phase.project_path or (
            str(plan.project_path) if plan.project_path else None
        )
        if not project:
            return PhaseOutcome(
                phase=phase.phase, ok=False,
                planned_outcome=phase.planned_outcome,
                actual_outcome="missing_project_path",
                error_code="InvalidArgumentFailure",
                error_message="OPEN_IDE phase needs project_path",
            )
        args = {
            "project_path": project,
            "ide": phase.extras.get("ide", "vscode"),
            "new_window": bool(phase.extras.get("new_window", True)),
        }
        res = await self._call("open_project_in_ide", args)
        if not res["ok"]:
            return self._fail(phase, res)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome="ide_opened",
        )

    async def _dev_session_start(
        self, plan: TestPlan, phase: PlanPhase
    ) -> PhaseOutcome:
        project = phase.project_path or (
            str(plan.project_path) if plan.project_path else None
        )
        if not project:
            return PhaseOutcome(
                phase=phase.phase, ok=False,
                planned_outcome=phase.planned_outcome,
                actual_outcome="missing_project_path",
                error_code="InvalidArgumentFailure",
                error_message="DEV_SESSION_START phase needs project_path",
            )
        args = {
            "project_path": project,
            "mode": phase.extras.get("mode", "debug"),
        }
        if phase.extras.get("flavor"):
            args["flavor"] = phase.extras["flavor"]
        if phase.extras.get("target"):
            args["target"] = phase.extras["target"]
        res = await self._call("start_debug_session", args)
        if not res["ok"]:
            return self._fail(phase, res)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome="dev_session_started",
        )

    async def _hot_reload(self, phase: PlanPhase) -> PhaseOutcome:
        res = await self._call(
            "restart_debug_session",
            {"full_restart": bool(phase.extras.get("full_restart", False))},
        )
        if not res["ok"]:
            return self._fail(phase, res)
        artifacts = await self._capture(phase)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome="reloaded", artifacts=artifacts,
        )

    async def _dev_session_stop(self, phase: PlanPhase) -> PhaseOutcome:
        res = await self._call("stop_debug_session", {})
        if not res["ok"]:
            return self._fail(phase, res)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome="dev_session_stopped",
        )

    async def _ar_scene_ready(self, phase: PlanPhase) -> PhaseOutcome:
        # Wait for AR session, then optionally assert pose stability for a marker.
        timeout_s = float(phase.extras.get("timeout_s", 30.0))
        wait = await self._call(
            "wait_for_ar_session_ready", {"timeout_s": timeout_s}
        )
        if not wait["ok"]:
            return self._fail(phase, wait)
        marker_id = phase.extras.get("marker_id")
        if marker_id is not None:
            stable = await self._call(
                "assert_pose_stable",
                {
                    "marker_id": int(marker_id),
                    "samples": int(phase.extras.get("samples", 8)),
                    "marker_size_m": float(phase.extras.get("marker_size_m", 0.05)),
                },
            )
            if not stable["ok"]:
                return self._fail(phase, stable)
        artifacts = await self._capture(phase)
        return PhaseOutcome(
            phase=phase.phase, ok=True, planned_outcome=phase.planned_outcome,
            actual_outcome="ar_ready", artifacts=artifacts,
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
            elif kind == "debug_log":
                await self._call("read_debug_log", {"since_s": 10, "level": "all"})
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
