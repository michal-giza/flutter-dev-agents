"""Use cases for virtual-device management (AVDs + iOS simulators)."""

from __future__ import annotations

from dataclasses import dataclass

from ..entities import Device
from ..repositories import VirtualDeviceManager
from ..result import Result
from .base import BaseUseCase, NoParams


class ListAvds(BaseUseCase[NoParams, list[str]]):
    def __init__(self, manager: VirtualDeviceManager) -> None:
        self._manager = manager

    async def execute(self, params: NoParams) -> Result[list[str]]:
        return await self._manager.list_avds()


@dataclass(frozen=True, slots=True)
class StartEmulatorParams:
    avd_name: str
    headless: bool = False


class StartEmulator(BaseUseCase[StartEmulatorParams, str]):
    def __init__(self, manager: VirtualDeviceManager) -> None:
        self._manager = manager

    async def execute(self, params: StartEmulatorParams) -> Result[str]:
        return await self._manager.start_emulator(params.avd_name, params.headless)


@dataclass(frozen=True, slots=True)
class StopVirtualDeviceParams:
    serial: str


class StopVirtualDevice(BaseUseCase[StopVirtualDeviceParams, None]):
    def __init__(self, manager: VirtualDeviceManager) -> None:
        self._manager = manager

    async def execute(self, params: StopVirtualDeviceParams) -> Result[None]:
        return await self._manager.stop_virtual_device(params.serial)


@dataclass(frozen=True, slots=True)
class ListSimulatorsParams:
    include_shutdown: bool = True


class ListSimulators(BaseUseCase[ListSimulatorsParams, list[Device]]):
    def __init__(self, manager: VirtualDeviceManager) -> None:
        self._manager = manager

    async def execute(self, params: ListSimulatorsParams) -> Result[list[Device]]:
        return await self._manager.list_simulators(params.include_shutdown)


@dataclass(frozen=True, slots=True)
class BootSimulatorParams:
    name_or_udid: str


class BootSimulator(BaseUseCase[BootSimulatorParams, Device]):
    def __init__(self, manager: VirtualDeviceManager) -> None:
        self._manager = manager

    async def execute(self, params: BootSimulatorParams) -> Result[Device]:
        return await self._manager.boot_simulator(params.name_or_udid)
