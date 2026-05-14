"""App lifecycle: launch, stop, clear data, grant permission."""

from __future__ import annotations

from dataclasses import dataclass

from ..repositories import LifecycleRepository, SessionStateRepository
from ..result import Err, Result
from ._helpers import resolve_serial
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class LaunchAppParams:
    package_id: str
    activity: str | None = None
    serial: str | None = None


class LaunchApp(BaseUseCase[LaunchAppParams, None]):
    def __init__(self, lifecycle: LifecycleRepository, state: SessionStateRepository) -> None:
        self._lifecycle = lifecycle
        self._state = state

    async def execute(self, params: LaunchAppParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._lifecycle.launch(serial_res.value, params.package_id, params.activity)


@dataclass(frozen=True, slots=True)
class StopAppParams:
    package_id: str
    serial: str | None = None


class StopApp(BaseUseCase[StopAppParams, None]):
    def __init__(self, lifecycle: LifecycleRepository, state: SessionStateRepository) -> None:
        self._lifecycle = lifecycle
        self._state = state

    async def execute(self, params: StopAppParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._lifecycle.stop(serial_res.value, params.package_id)


@dataclass(frozen=True, slots=True)
class ClearAppDataParams:
    package_id: str
    serial: str | None = None


class ClearAppData(BaseUseCase[ClearAppDataParams, None]):
    def __init__(self, lifecycle: LifecycleRepository, state: SessionStateRepository) -> None:
        self._lifecycle = lifecycle
        self._state = state

    async def execute(self, params: ClearAppDataParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._lifecycle.clear_data(serial_res.value, params.package_id)


@dataclass(frozen=True, slots=True)
class GrantPermissionParams:
    package_id: str
    permission: str
    serial: str | None = None


class GrantPermission(BaseUseCase[GrantPermissionParams, None]):
    def __init__(self, lifecycle: LifecycleRepository, state: SessionStateRepository) -> None:
        self._lifecycle = lifecycle
        self._state = state

    async def execute(self, params: GrantPermissionParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._lifecycle.grant_permission(
            serial_res.value, params.package_id, params.permission
        )
