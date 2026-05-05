"""Dev-session use cases — driving `flutter run --machine`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import (
    BuildMode,
    DebugLogEntry,
    DebugSession,
    ServiceExtensionResult,
)
from ..repositories import DebugSessionRepository, SessionStateRepository
from ..result import Err, Result
from .base import BaseUseCase, NoParams
from ._helpers import resolve_serial


@dataclass(frozen=True, slots=True)
class StartDebugSessionParams:
    project_path: Path
    mode: BuildMode = BuildMode.DEBUG
    flavor: str | None = None
    target: str | None = None
    serial: str | None = None


class StartDebugSession(BaseUseCase[StartDebugSessionParams, DebugSession]):
    def __init__(
        self, repo: DebugSessionRepository, state: SessionStateRepository
    ) -> None:
        self._repo = repo
        self._state = state

    async def execute(self, params: StartDebugSessionParams) -> Result[DebugSession]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._repo.start(
            project_path=params.project_path,
            device_serial=serial_res.value,
            mode=params.mode,
            flavor=params.flavor,
            target=params.target,
        )


@dataclass(frozen=True, slots=True)
class StopDebugSessionParams:
    session_id: str | None = None


class StopDebugSession(BaseUseCase[StopDebugSessionParams, None]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: StopDebugSessionParams) -> Result[None]:
        return await self._repo.stop(params.session_id)


@dataclass(frozen=True, slots=True)
class RestartDebugSessionParams:
    session_id: str | None = None
    full_restart: bool = False


class RestartDebugSession(BaseUseCase[RestartDebugSessionParams, DebugSession]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: RestartDebugSessionParams) -> Result[DebugSession]:
        return await self._repo.restart(params.session_id, params.full_restart)


class ListDebugSessions(BaseUseCase[NoParams, list[DebugSession]]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: NoParams) -> Result[list[DebugSession]]:
        return await self._repo.list_sessions()


@dataclass(frozen=True, slots=True)
class AttachDebugSessionParams:
    vm_service_uri: str
    project_path: Path


class AttachDebugSession(BaseUseCase[AttachDebugSessionParams, DebugSession]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: AttachDebugSessionParams) -> Result[DebugSession]:
        return await self._repo.attach(params.vm_service_uri, params.project_path)


@dataclass(frozen=True, slots=True)
class ReadDebugLogParams:
    session_id: str | None = None
    since_s: int = 30
    level: str = "all"
    max_lines: int = 500


class ReadDebugLog(BaseUseCase[ReadDebugLogParams, list[DebugLogEntry]]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: ReadDebugLogParams) -> Result[list[DebugLogEntry]]:
        return await self._repo.read_log(
            session_id=params.session_id,
            since_s=params.since_s,
            level=params.level,
            max_lines=params.max_lines,
        )


@dataclass(frozen=True, slots=True)
class TailDebugLogParams:
    until_pattern: str
    session_id: str | None = None
    timeout_s: float = 30.0


class TailDebugLog(BaseUseCase[TailDebugLogParams, list[DebugLogEntry]]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: TailDebugLogParams) -> Result[list[DebugLogEntry]]:
        return await self._repo.tail_log(
            session_id=params.session_id,
            until_pattern=params.until_pattern,
            timeout_s=params.timeout_s,
        )


@dataclass(frozen=True, slots=True)
class CallServiceExtensionParams:
    method: str
    args: dict | None = None
    session_id: str | None = None


class CallServiceExtension(BaseUseCase[CallServiceExtensionParams, ServiceExtensionResult]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(
        self, params: CallServiceExtensionParams
    ) -> Result[ServiceExtensionResult]:
        return await self._repo.call_service_extension(
            session_id=params.session_id, method=params.method, args=params.args
        )


@dataclass(frozen=True, slots=True)
class DumpWidgetTreeParams:
    session_id: str | None = None


class DumpWidgetTree(BaseUseCase[DumpWidgetTreeParams, ServiceExtensionResult]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: DumpWidgetTreeParams) -> Result[ServiceExtensionResult]:
        return await self._repo.call_service_extension(
            session_id=params.session_id, method="ext.flutter.debugDumpApp"
        )


class DumpRenderTree(BaseUseCase[DumpWidgetTreeParams, ServiceExtensionResult]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: DumpWidgetTreeParams) -> Result[ServiceExtensionResult]:
        return await self._repo.call_service_extension(
            session_id=params.session_id, method="ext.flutter.debugDumpRenderTree"
        )


@dataclass(frozen=True, slots=True)
class ToggleInspectorParams:
    enabled: bool
    session_id: str | None = None


class ToggleInspector(BaseUseCase[ToggleInspectorParams, ServiceExtensionResult]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: ToggleInspectorParams) -> Result[ServiceExtensionResult]:
        return await self._repo.call_service_extension(
            session_id=params.session_id,
            method="ext.flutter.inspector.show",
            args={"enabled": params.enabled},
        )
