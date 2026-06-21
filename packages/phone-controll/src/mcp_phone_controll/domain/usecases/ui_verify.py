"""Composite verification helpers — encode "every action has a flow" mechanically.

`TapAndVerify` and `AssertNoErrorsSince` are deliberately thin orchestrations
on top of existing repos. They exist so an agent can express:

  "Tap 'Sign in', then verify 'Welcome' appears within 5s, with no ERROR logs."

…in two tool calls instead of three plus bespoke retry logic. Small models
in particular benefit from this — they tend to skip the verify step when it
is a separate concern, but they will dutifully chain when the verify is
baked into the action.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..entities import Artifact, ArtifactKind, LogEntry, LogLevel, UiElement
from ..failures import TestExecutionFailure, UiElementNotFoundFailure
from ..repositories import (
    ArtifactRepository,
    ObservationRepository,
    SessionStateRepository,
    UiRepository,
)
from ..result import Err, Result, err, ok
from ._helpers import resolve_serial
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class TapAndVerifyParams:
    text: str
    expect_text: str | None = None
    expect_resource_id: str | None = None
    timeout_s: float = 5.0
    exact: bool = False
    # On verify failure, attach a capped screenshot + recent error logs to
    # the failure — so diagnosing the miss costs no extra round-trip.
    capture_on_failure: bool = True
    serial: str | None = None


class TapAndVerify(BaseUseCase[TapAndVerifyParams, UiElement]):
    """Tap a target and assert that an expected element appears afterwards.

    Use this for any tap whose semantics include a navigation or state change
    the user should perceive. If the verification element does not appear,
    the failure carries `next_action="capture_diagnostics"` so the agent
    grabs a screenshot + logs before retrying.
    """

    def __init__(
        self,
        ui: UiRepository,
        state: SessionStateRepository,
        observation: ObservationRepository | None = None,
        artifacts: ArtifactRepository | None = None,
    ) -> None:
        self._ui = ui
        self._state = state
        # Optional: when both are wired, a verify failure folds in a
        # screenshot + recent error logs (no separate diagnose call).
        self._observation = observation
        self._artifacts = artifacts

    async def execute(self, params: TapAndVerifyParams) -> Result[UiElement]:
        if params.expect_text is None and params.expect_resource_id is None:
            return err(
                UiElementNotFoundFailure(
                    message="tap_and_verify requires expect_text or expect_resource_id",
                    next_action="fix_arguments",
                    details={
                        "corrected_example": {
                            "text": params.text,
                            "expect_text": "<text that must appear after tap>",
                        },
                    },
                )
            )
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        tap_res = await self._ui.tap_text(
            serial_res.value, params.text, params.exact
        )
        if isinstance(tap_res, Err):
            return tap_res
        wait_res = await self._ui.wait_for(
            serial_res.value,
            text=params.expect_text,
            resource_id=params.expect_resource_id,
            timeout_s=params.timeout_s,
        )
        if isinstance(wait_res, Err):
            failure = wait_res.failure
            details: dict = {
                "tapped": params.text,
                "expect_text": params.expect_text,
                "expect_resource_id": params.expect_resource_id,
                "underlying": failure.message,
            }
            next_action = "capture_diagnostics"
            if params.capture_on_failure:
                diag = await self._capture(serial_res.value)
                if diag:
                    details["diagnostics"] = diag
                    # Diagnostics are in-hand — point at the fix, not a
                    # follow-up capture call.
                    next_action = "inspect_diagnostics"
            return err(
                UiElementNotFoundFailure(
                    message=(
                        f"tapped {params.text!r} but verification element did "
                        f"not appear within {params.timeout_s}s"
                    ),
                    next_action=next_action,
                    details=details,
                )
            )
        return ok(wait_res.value)

    async def _capture(self, serial: str) -> dict | None:
        """Best-effort screenshot (capped) + recent error logs for a verify
        failure. Returns None if the observation/artifact repos aren't
        wired or capture fails — never raises into the action path."""
        if self._observation is None or self._artifacts is None:
            return None
        diag: dict = {}
        try:
            path_res = await self._artifacts.allocate_path(
                "screenshot", ".png", "tap-verify-fail"
            )
            if not isinstance(path_res, Err):
                shot_res = await self._observation.screenshot(serial, path_res.value)
                if not isinstance(shot_res, Err):
                    from ...data.image_capping import cap_image_in_place

                    cap_image_in_place(shot_res.value)
                    await self._artifacts.register(
                        Artifact(
                            path=shot_res.value,
                            kind=ArtifactKind.SCREENSHOT,
                            label="tap-verify-fail",
                        )
                    )
                    diag["screenshot"] = str(shot_res.value)
        except Exception:
            pass
        try:
            logs_res = await self._observation.read_logs(
                serial, since_s=30, min_level=LogLevel.ERROR, max_lines=20
            )
            if not isinstance(logs_res, Err) and logs_res.value:
                diag["recent_errors"] = [e.message[:200] for e in logs_res.value]
        except Exception:
            pass
        return diag or None


@dataclass(frozen=True, slots=True)
class AssertNoErrorsSinceParams:
    since_s: int = 30
    tag: str | None = None
    serial: str | None = None


class AssertNoErrorsSince(BaseUseCase[AssertNoErrorsSinceParams, list[LogEntry]]):
    """Fail if any ERROR-level log entry appeared in the last N seconds.

    Returns the offending entries on failure so the agent can quote them
    verbatim in its diagnosis.
    """

    def __init__(
        self,
        observation: ObservationRepository,
        state: SessionStateRepository,
    ) -> None:
        self._observation = observation
        self._state = state

    async def execute(
        self, params: AssertNoErrorsSinceParams
    ) -> Result[list[LogEntry]]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        logs_res = await self._observation.read_logs(
            serial_res.value,
            since_s=params.since_s,
            tag=params.tag,
            min_level=LogLevel.ERROR,
            max_lines=200,
        )
        if isinstance(logs_res, Err):
            return logs_res
        offending = [
            entry for entry in logs_res.value
            if entry.level in (LogLevel.ERROR, LogLevel.FATAL)
        ]
        if offending:
            return err(
                TestExecutionFailure(
                    message=(
                        f"{len(offending)} error log entries in the last "
                        f"{params.since_s}s"
                    ),
                    next_action="capture_diagnostics",
                    details={
                        "count": len(offending),
                        "first": offending[0].message[:200],
                        "tag": params.tag,
                    },
                )
            )
        return ok([])
