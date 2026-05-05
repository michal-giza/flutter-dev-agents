"""Vision use cases — visual diff, ArUco markers, pose, marker-wait."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from ..entities import ImageDiff, MarkerDetection, Pose
from ..failures import TimeoutFailure, VisionFailure
from ..repositories import (
    ArtifactRepository,
    ObservationRepository,
    SessionStateRepository,
    VisionRepository,
)
from ..result import Err, Result, err, ok
from .base import BaseUseCase
from ._helpers import resolve_serial


@dataclass(frozen=True, slots=True)
class CompareScreenshotParams:
    actual_path: Path
    golden_path: Path
    tolerance: float = 0.98
    diff_output_path: Path | None = None


class CompareScreenshot(BaseUseCase[CompareScreenshotParams, ImageDiff]):
    def __init__(self, vision: VisionRepository) -> None:
        self._vision = vision

    async def execute(self, params: CompareScreenshotParams) -> Result[ImageDiff]:
        return await self._vision.compare(
            params.actual_path,
            params.golden_path,
            params.tolerance,
            params.diff_output_path,
        )


@dataclass(frozen=True, slots=True)
class DetectMarkersParams:
    image_path: Path
    dictionary: str = "DICT_4X4_50"


class DetectMarkers(BaseUseCase[DetectMarkersParams, list[MarkerDetection]]):
    def __init__(self, vision: VisionRepository) -> None:
        self._vision = vision

    async def execute(
        self, params: DetectMarkersParams
    ) -> Result[list[MarkerDetection]]:
        return await self._vision.detect_markers(params.image_path, params.dictionary)


@dataclass(frozen=True, slots=True)
class InferCameraPoseParams:
    image_path: Path
    marker_id: int
    marker_size_m: float


class InferCameraPose(BaseUseCase[InferCameraPoseParams, Pose]):
    def __init__(self, vision: VisionRepository) -> None:
        self._vision = vision

    async def execute(self, params: InferCameraPoseParams) -> Result[Pose]:
        return await self._vision.infer_pose(
            params.image_path, params.marker_id, params.marker_size_m
        )


@dataclass(frozen=True, slots=True)
class WaitForMarkerParams:
    marker_id: int
    timeout_s: float = 30.0
    poll_interval_s: float = 1.0
    dictionary: str = "DICT_4X4_50"
    serial: str | None = None


class WaitForMarker(BaseUseCase[WaitForMarkerParams, MarkerDetection]):
    """Polls take_screenshot + detect_markers until the marker is seen."""

    def __init__(
        self,
        vision: VisionRepository,
        observation: ObservationRepository,
        artifacts: ArtifactRepository,
        state: SessionStateRepository,
    ) -> None:
        self._vision = vision
        self._observation = observation
        self._artifacts = artifacts
        self._state = state

    async def execute(self, params: WaitForMarkerParams) -> Result[MarkerDetection]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        serial = serial_res.value

        loop = asyncio.get_event_loop()
        deadline = loop.time() + params.timeout_s
        while loop.time() < deadline:
            path_res = await self._artifacts.allocate_path(
                "screenshot", ".png", f"marker-poll-{params.marker_id}"
            )
            if isinstance(path_res, Err):
                return path_res
            shot_res = await self._observation.screenshot(serial, path_res.value)
            if isinstance(shot_res, Err):
                return shot_res
            detect_res = await self._vision.detect_markers(
                shot_res.value, params.dictionary
            )
            if isinstance(detect_res, Err):
                return detect_res
            for marker in detect_res.value:
                if marker.id == params.marker_id:
                    return ok(marker)
            await asyncio.sleep(params.poll_interval_s)

        return err(
            TimeoutFailure(
                message=f"marker {params.marker_id} not seen in {params.timeout_s}s",
                next_action="check_lighting",
                details={"marker_id": params.marker_id, "timeout_s": params.timeout_s},
            )
        )
