"""Device discovery, selection, and cross-session lock management."""

from __future__ import annotations

from dataclasses import dataclass

from ..entities import Device, DeviceLock
from ..failures import DeviceNotFoundFailure
from ..repositories import (
    DeviceLockRepository,
    DeviceRepository,
    SessionStateRepository,
)
from ..result import Err, Result, ok
from .base import BaseUseCase, NoParams


class ListDevices(BaseUseCase[NoParams, list[Device]]):
    def __init__(self, repo: DeviceRepository) -> None:
        self._repo = repo

    async def execute(self, params: NoParams) -> Result[list[Device]]:
        return await self._repo.list_devices()


@dataclass(frozen=True, slots=True)
class SelectDeviceParams:
    serial: str
    force: bool = False
    note: str | None = None


class SelectDevice(BaseUseCase[SelectDeviceParams, Device]):
    """Select a device for this session AND acquire the cross-session lock."""

    def __init__(
        self,
        devices: DeviceRepository,
        state: SessionStateRepository,
        locks: DeviceLockRepository,
        session_id: str,
    ) -> None:
        self._devices = devices
        self._state = state
        self._locks = locks
        self._session_id = session_id

    async def execute(self, params: SelectDeviceParams) -> Result[Device]:
        device_res = await self._devices.get_device(params.serial)
        if isinstance(device_res, Err):
            return device_res
        lock_res = await self._locks.acquire(
            params.serial,
            session_id=self._session_id,
            force=params.force,
            note=params.note,
        )
        if isinstance(lock_res, Err):
            return lock_res
        set_res = await self._state.set_selected_serial(params.serial)
        if isinstance(set_res, Err):
            return set_res
        return device_res


class GetSelectedDevice(BaseUseCase[NoParams, Device | None]):
    def __init__(self, devices: DeviceRepository, state: SessionStateRepository) -> None:
        self._devices = devices
        self._state = state

    async def execute(self, params: NoParams) -> Result[Device | None]:
        serial_result = await self._state.get_selected_serial()
        if isinstance(serial_result, Err):
            return serial_result
        if serial_result.value is None:
            return ok(None)
        device_result = await self._devices.get_device(serial_result.value)
        if isinstance(device_result, Err):
            if isinstance(device_result.failure, DeviceNotFoundFailure):
                return ok(None)
            return device_result
        return ok(device_result.value)


@dataclass(frozen=True, slots=True)
class ReleaseDeviceParams:
    serial: str | None = None


class ReleaseDevice(BaseUseCase[ReleaseDeviceParams, None]):
    """Release the lock held by this session on `serial` (or the selected one)."""

    def __init__(
        self,
        state: SessionStateRepository,
        locks: DeviceLockRepository,
        session_id: str,
    ) -> None:
        self._state = state
        self._locks = locks
        self._session_id = session_id

    async def execute(self, params: ReleaseDeviceParams) -> Result[None]:
        target = params.serial
        if target is None:
            sel = await self._state.get_selected_serial()
            if isinstance(sel, Err):
                return sel
            target = sel.value
        if target is None:
            return ok(None)
        release_res = await self._locks.release(target, self._session_id)
        if isinstance(release_res, Err):
            return release_res
        await self._state.set_selected_serial(None)
        return ok(None)


class ListLocks(BaseUseCase[NoParams, list[DeviceLock]]):
    def __init__(self, locks: DeviceLockRepository) -> None:
        self._locks = locks

    async def execute(self, params: NoParams) -> Result[list[DeviceLock]]:
        return await self._locks.list_locks()


@dataclass(frozen=True, slots=True)
class ForceReleaseLockParams:
    serial: str


class ForceReleaseLock(BaseUseCase[ForceReleaseLockParams, None]):
    """Admin — break a lock without holding it. Use when another session crashed."""

    def __init__(self, locks: DeviceLockRepository) -> None:
        self._locks = locks

    async def execute(self, params: ForceReleaseLockParams) -> Result[None]:
        return await self._locks.force_release(params.serial)
