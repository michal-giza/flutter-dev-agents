"""Observation: screenshots, recordings, log reads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import Artifact, ArtifactKind, LogEntry, LogLevel
from ..failures import FilesystemFailure
from ..repositories import (
    ArtifactRepository,
    ObservationRepository,
    SessionStateRepository,
)
from ..result import Err, Result, err, ok
from ._helpers import resolve_serial
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class TakeScreenshotParams:
    label: str | None = None
    serial: str | None = None


class TakeScreenshot(BaseUseCase[TakeScreenshotParams, Path]):
    def __init__(
        self,
        observation: ObservationRepository,
        artifacts: ArtifactRepository,
        state: SessionStateRepository,
    ) -> None:
        self._observation = observation
        self._artifacts = artifacts
        self._state = state

    async def execute(self, params: TakeScreenshotParams) -> Result[Path]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        path_res = await self._artifacts.allocate_path("screenshot", ".png", params.label)
        if isinstance(path_res, Err):
            return path_res
        shot_res = await self._observation.screenshot(serial_res.value, path_res.value)
        if isinstance(shot_res, Err):
            return shot_res
        # Cap dimensions for vision-model compatibility (Claude 2000px hard
        # limit on multi-image conversations; LLaVA/Qwen-VL prefer ≤1024px).
        # Original is preserved at `<path>.orig.png` for visual-diff workflows.
        from ...data.image_capping import (
            _read_png_dimensions,
            cap_image_in_place,
            is_within_cap,
        )

        cap_image_in_place(shot_res.value)
        # Defense-in-depth verification (May 2026 incident):
        #   On a stale subprocess running pre-cap code, `cap_image_in_place`
        #   silently doesn't run, and the agent receives a path to a
        #   1080x2340 PNG that crashes the conversation with the 2000px
        #   API error. The dispatcher's safety-net middleware should
        #   catch this — but if that middleware itself is from a stale
        #   subprocess, both layers are broken. This third check sits
        #   inside the use case where every code path producing a
        #   screenshot MUST pass through. Hard ceiling 1900 px is the
        #   API limit minus 100 px of safety margin.
        from ...observability import warn

        if not is_within_cap(shot_res.value, max_dim=1900):
            dims = _read_png_dimensions(shot_res.value) or (0, 0)
            warn(
                "take_screenshot_cap_failed_post_check",
                path=str(shot_res.value),
                dims=f"{dims[0]}x{dims[1]}",
                hint=(
                    "cap pipeline failed silently — check available_backends() "
                    "and consider restarting the MCP subprocess if you suspect "
                    "stale code (mcp_ping reports image_cap_px and git_sha)"
                ),
            )
            # Return a structured failure rather than the oversized path.
            # Agent gets `next_action="install_image_backend"` and the
            # diagnostic to bring up to the operator.
            return err(
                FilesystemFailure(
                    message=(
                        f"Screenshot at {shot_res.value} is {dims[0]}x{dims[1]} — "
                        "over the 1900px API hard ceiling. The image-cap "
                        "pipeline failed to bring it down. Likely cause: a "
                        "stale MCP subprocess running pre-cap code, or no "
                        "image-cap backend available (cv2/PIL/sips). Call "
                        "mcp_ping to verify version + backends; fully quit "
                        "and relaunch the host if image_cap_px is missing "
                        "or > 1900."
                    ),
                    next_action="install_image_backend",
                    details={
                        "path": str(shot_res.value),
                        "width": dims[0],
                        "height": dims[1],
                        "max_allowed_px": 1900,
                    },
                )
            )
        await self._artifacts.register(
            Artifact(path=shot_res.value, kind=ArtifactKind.SCREENSHOT, label=params.label)
        )
        return ok(shot_res.value)


@dataclass(frozen=True, slots=True)
class ZoomScreenshotParams:
    # Region to magnify, in DEVICE PIXELS (same space as dump_ui bounds).
    region: tuple[int, int, int, int]  # x1, y1, x2, y2
    path: Path | None = None           # crop this image; else capture fresh
    scale: float = 2.0                 # upscale factor for the crop
    label: str | None = None
    serial: str | None = None


class ZoomScreenshot(BaseUseCase[ZoomScreenshotParams, Path]):
    """Crop a region of a screenshot and upscale it — for reading small UI
    (tiny picker thumbnails, dense labels) the full frame renders too small
    to identify. Captures a FULL-RES frame so the region coords match
    device pixels / dump_ui bounds, crops, upscales, then caps the *crop*
    for vision-model safety. Mirrors computer-use's zoom(region)."""

    def __init__(
        self,
        observation: ObservationRepository,
        artifacts: ArtifactRepository,
        state: SessionStateRepository,
    ) -> None:
        self._observation = observation
        self._artifacts = artifacts
        self._state = state

    async def execute(self, params: ZoomScreenshotParams) -> Result[Path]:
        x1, y1, x2, y2 = params.region
        if x2 <= x1 or y2 <= y1:
            return err(
                FilesystemFailure(
                    message=f"invalid region {params.region}: need x2>x1 and y2>y1",
                    next_action="fix_arguments",
                )
            )

        # Source frame. Capture FULL-RES (not via take_screenshot, which
        # caps to ≤1900px and would shift the coordinate space) so the
        # region maps to true device pixels.
        if params.path is not None:
            src = params.path
            if not src.is_file():
                return err(
                    FilesystemFailure(
                        message=f"source screenshot not found: {src}",
                        next_action="fix_arguments",
                    )
                )
        else:
            serial_res = await resolve_serial(params.serial, self._state)
            if isinstance(serial_res, Err):
                return serial_res
            cap_res = await self._artifacts.allocate_path("screenshot", ".png")
            if isinstance(cap_res, Err):
                return cap_res
            shot_res = await self._observation.screenshot(serial_res.value, cap_res.value)
            if isinstance(shot_res, Err):
                return shot_res
            src = shot_res.value

        out_res = await self._artifacts.allocate_path("zoom", ".png", params.label)
        if isinstance(out_res, Err):
            return out_res
        out_path = out_res.value

        try:
            from PIL import Image
        except ImportError:
            return err(
                FilesystemFailure(
                    message="zoom needs Pillow (PIL) to crop/upscale; not installed.",
                    next_action="install_image_backend",
                )
            )

        try:
            import asyncio

            def _crop_and_scale() -> None:
                with Image.open(src) as img:
                    w, h = img.size
                    # Clamp the region to the image so an over-wide bounds
                    # rect doesn't error — just crops what's there.
                    cx1, cy1 = max(0, x1), max(0, y1)
                    cx2, cy2 = min(w, x2), min(h, y2)
                    crop = img.crop((cx1, cy1, cx2, cy2))
                    if params.scale and params.scale != 1.0:
                        crop = crop.resize(
                            (
                                max(1, int(crop.width * params.scale)),
                                max(1, int(crop.height * params.scale)),
                            )
                        )
                    crop.save(out_path)

            await asyncio.to_thread(_crop_and_scale)
        except Exception as e:
            return err(FilesystemFailure(message=f"zoom failed: {e}"))

        # Cap the (upscaled) crop so it can't blow the vision API's pixel limit.
        from ...data.image_capping import cap_image_in_place

        cap_image_in_place(out_path)
        await self._artifacts.register(
            Artifact(path=out_path, kind=ArtifactKind.SCREENSHOT, label=params.label)
        )
        return ok(out_path)


@dataclass(frozen=True, slots=True)
class StartRecordingParams:
    label: str | None = None
    serial: str | None = None


class StartRecording(BaseUseCase[StartRecordingParams, Path]):
    def __init__(
        self,
        observation: ObservationRepository,
        artifacts: ArtifactRepository,
        state: SessionStateRepository,
    ) -> None:
        self._observation = observation
        self._artifacts = artifacts
        self._state = state

    async def execute(self, params: StartRecordingParams) -> Result[Path]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        path_res = await self._artifacts.allocate_path("recording", ".mp4", params.label)
        if isinstance(path_res, Err):
            return path_res
        rec_res = await self._observation.start_recording(serial_res.value, path_res.value)
        if isinstance(rec_res, Err):
            return rec_res
        return ok(path_res.value)


@dataclass(frozen=True, slots=True)
class StopRecordingParams:
    serial: str | None = None


class StopRecording(BaseUseCase[StopRecordingParams, Path]):
    def __init__(
        self,
        observation: ObservationRepository,
        artifacts: ArtifactRepository,
        state: SessionStateRepository,
    ) -> None:
        self._observation = observation
        self._artifacts = artifacts
        self._state = state

    async def execute(self, params: StopRecordingParams) -> Result[Path]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        stop_res = await self._observation.stop_recording(serial_res.value)
        if isinstance(stop_res, Err):
            return stop_res
        await self._artifacts.register(Artifact(path=stop_res.value, kind=ArtifactKind.RECORDING))
        return ok(stop_res.value)


@dataclass(frozen=True, slots=True)
class ReadLogsParams:
    since_s: int = 30
    tag: str | None = None
    min_level: LogLevel = LogLevel.WARN
    max_lines: int = 500
    serial: str | None = None


class ReadLogs(BaseUseCase[ReadLogsParams, list[LogEntry]]):
    def __init__(
        self, observation: ObservationRepository, state: SessionStateRepository
    ) -> None:
        self._observation = observation
        self._state = state

    async def execute(self, params: ReadLogsParams) -> Result[list[LogEntry]]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._observation.read_logs(
            serial_res.value,
            since_s=params.since_s,
            tag=params.tag,
            min_level=params.min_level,
            max_lines=params.max_lines,
        )


@dataclass(frozen=True, slots=True)
class TailLogsParams:
    until_pattern: str
    tag: str | None = None
    timeout_s: float = 30.0
    serial: str | None = None


class TailLogs(BaseUseCase[TailLogsParams, list[LogEntry]]):
    def __init__(
        self, observation: ObservationRepository, state: SessionStateRepository
    ) -> None:
        self._observation = observation
        self._state = state

    async def execute(self, params: TailLogsParams) -> Result[list[LogEntry]]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._observation.tail_logs_until(
            serial_res.value,
            until_pattern=params.until_pattern,
            tag=params.tag,
            timeout_s=params.timeout_s,
        )
