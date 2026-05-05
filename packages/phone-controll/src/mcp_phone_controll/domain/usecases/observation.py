"""Observation: screenshots, recordings, log reads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import Artifact, ArtifactKind, LogEntry, LogLevel
from ..repositories import (
    ArtifactRepository,
    ObservationRepository,
    SessionStateRepository,
)
from ..result import Err, Result, ok
from .base import BaseUseCase
from ._helpers import resolve_serial


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
        await self._artifacts.register(
            Artifact(path=shot_res.value, kind=ArtifactKind.SCREENSHOT, label=params.label)
        )
        return ok(shot_res.value)


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
