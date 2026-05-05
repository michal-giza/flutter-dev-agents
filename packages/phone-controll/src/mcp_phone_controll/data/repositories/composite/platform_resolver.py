"""Resolves a serial → Platform and DeviceClass.

Backed by a cache populated when CompositeDeviceRepository.list_devices runs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from ....domain.entities import DeviceClass, Platform
from ....domain.failures import DeviceNotFoundFailure
from ....domain.result import Result, err, ok


@dataclass(frozen=True, slots=True)
class DeviceKind:
    platform: Platform
    device_class: DeviceClass


class PlatformResolver(Protocol):
    async def platform_for(self, serial: str) -> Result[Platform]: ...
    async def kind_for(self, serial: str) -> Result[DeviceKind]: ...
    async def remember(self, serial: str, platform: Platform) -> None: ...
    async def remember_kind(
        self, serial: str, platform: Platform, device_class: DeviceClass
    ) -> None: ...


class CachingPlatformResolver:
    def __init__(self) -> None:
        self._platforms: dict[str, Platform] = {}
        self._classes: dict[str, DeviceClass] = {}
        self._lock = asyncio.Lock()

    async def remember(self, serial: str, platform: Platform) -> None:
        async with self._lock:
            self._platforms[serial] = platform

    async def remember_kind(
        self, serial: str, platform: Platform, device_class: DeviceClass
    ) -> None:
        async with self._lock:
            self._platforms[serial] = platform
            self._classes[serial] = device_class

    async def forget(self, serial: str) -> None:
        async with self._lock:
            self._platforms.pop(serial, None)
            self._classes.pop(serial, None)

    async def platform_for(self, serial: str) -> Result[Platform]:
        async with self._lock:
            platform = self._platforms.get(serial)
        if platform is None:
            return err(
                DeviceNotFoundFailure(
                    message=f"unknown device {serial}; call list_devices first",
                    next_action="list_devices",
                )
            )
        return ok(platform)

    async def kind_for(self, serial: str) -> Result[DeviceKind]:
        async with self._lock:
            platform = self._platforms.get(serial)
            cls = self._classes.get(serial, DeviceClass.UNKNOWN)
        if platform is None:
            return err(
                DeviceNotFoundFailure(
                    message=f"unknown device {serial}; call list_devices first",
                    next_action="list_devices",
                )
            )
        return ok(DeviceKind(platform=platform, device_class=cls))
