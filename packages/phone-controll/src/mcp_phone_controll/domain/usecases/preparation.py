"""Composite preparation — atomic CLEAN-phase handoff with proof of state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..repositories import (
    ArtifactRepository,
    LifecycleRepository,
    ObservationRepository,
    SessionStateRepository,
    UiRepository,
)
from ..result import Err, Result, ok
from .base import BaseUseCase
from ._helpers import resolve_serial


@dataclass(frozen=True, slots=True)
class PrepareForTestParams:
    package_id: str
    serial: str | None = None
    skip_clear: bool = False               # iOS / non-Android paths
    capture_evidence: bool = True


@dataclass(frozen=True, slots=True)
class PreparationResult:
    serial: str
    package_id: str
    actions_run: tuple[str, ...] = ()
    evidence_screenshot: str | None = None


class PrepareForTest(BaseUseCase[PrepareForTestParams, PreparationResult]):
    """Atomic clean handoff: stop, clear data, home, screenshot."""

    def __init__(
        self,
        lifecycle: LifecycleRepository,
        ui: UiRepository,
        observation: ObservationRepository,
        artifacts: ArtifactRepository,
        state: SessionStateRepository,
    ) -> None:
        self._lifecycle = lifecycle
        self._ui = ui
        self._observation = observation
        self._artifacts = artifacts
        self._state = state

    async def execute(self, params: PrepareForTestParams) -> Result[PreparationResult]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        serial = serial_res.value
        actions: list[str] = []

        stop_res = await self._lifecycle.stop(serial, params.package_id)
        if isinstance(stop_res, Err) and "not running" not in stop_res.failure.message.lower():
            return stop_res
        actions.append("stop_app")

        if not params.skip_clear:
            clear_res = await self._lifecycle.clear_data(serial, params.package_id)
            if isinstance(clear_res, Err):
                return clear_res
            actions.append("clear_app_data")

        home_res = await self._ui.press_key(serial, "home")
        if isinstance(home_res, Err):
            return home_res
        actions.append("press_key_home")

        screenshot_path: str | None = None
        if params.capture_evidence:
            path_res = await self._artifacts.allocate_path(
                "screenshot", ".png", "PRE_FLIGHT-home"
            )
            if isinstance(path_res, Err):
                return path_res
            shot_res = await self._observation.screenshot(serial, path_res.value)
            if isinstance(shot_res, Err):
                return shot_res
            # Cap dimensions before returning the path — Claude Code auto-
            # embeds returned PNG paths inline, and uncapped Galaxy/iPhone
            # screenshots blow the 2000px multi-image limit. Original
            # preserved at `<path>.orig.png`.
            from ...data.image_capping import cap_image_in_place

            cap_image_in_place(shot_res.value)
            screenshot_path = str(shot_res.value)
            actions.append("take_screenshot")

        return ok(
            PreparationResult(
                serial=serial,
                package_id=params.package_id,
                actions_run=tuple(actions),
                evidence_screenshot=screenshot_path,
            )
        )
