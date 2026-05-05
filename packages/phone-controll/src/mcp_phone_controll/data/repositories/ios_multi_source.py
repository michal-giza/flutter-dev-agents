"""Multi-source iOS repositories — union of physical (pymobiledevice3) and
simulator (simctl) sources, routing per call by the resolver's DeviceKind.

These repositories implement the same Protocols as the per-platform repos so
they slot into the existing top-level CompositeDeviceRepository unchanged.
"""

from __future__ import annotations

from pathlib import Path

from ...domain.entities import (
    Device,
    DeviceClass,
    LogEntry,
    LogLevel,
    Platform,
)
from ...domain.failures import DeviceNotFoundFailure
from ...domain.repositories import (
    DeviceRepository,
    LifecycleRepository,
    ObservationRepository,
)
from ...domain.result import Err, Result, err, ok
from .composite.platform_resolver import CachingPlatformResolver


class _IosSourceRouter:
    """Mixin: serial → physical or simulator impl via resolver kind."""

    def __init__(
        self,
        physical,
        simulator,
        resolver: CachingPlatformResolver,
    ) -> None:
        self._physical = physical
        self._simulator = simulator
        self._resolver = resolver

    async def _route(self, serial: str):
        kind_res = await self._resolver.kind_for(serial)
        if isinstance(kind_res, Err):
            return kind_res
        if kind_res.value.platform is not Platform.IOS:
            return err(
                DeviceNotFoundFailure(
                    message=f"{serial} is not an iOS device",
                    next_action="select_device",
                )
            )
        impl = (
            self._simulator
            if kind_res.value.device_class is DeviceClass.SIMULATOR
            else self._physical
        )
        return ok(impl)


class MultiSourceIosDeviceRepository(DeviceRepository):
    """Unions iOS physical + simulator sources, taggings each."""

    def __init__(
        self,
        physical: DeviceRepository,
        simulator: DeviceRepository,
        resolver: CachingPlatformResolver,
    ) -> None:
        self._physical = physical
        self._simulator = simulator
        self._resolver = resolver
        self._last_physical_error: object | None = None
        self._last_simulator_error: object | None = None

    async def list_devices(self) -> Result[list[Device]]:
        merged: list[Device] = []
        # Physical: best-effort (toolchain may be missing).
        try:
            phys = await self._physical.list_devices()
        except Exception as e:  # noqa: BLE001
            self._last_physical_error = f"{type(e).__name__}: {e}"
        else:
            if isinstance(phys, Err):
                self._last_physical_error = phys.failure
            else:
                self._last_physical_error = None
                for d in phys.value:
                    await self._resolver.remember_kind(
                        d.serial, Platform.IOS, DeviceClass.PHYSICAL
                    )
                    merged.append(d)
        # Simulator: best-effort (Xcode may be missing on non-mac CI).
        try:
            sim = await self._simulator.list_devices()
        except Exception as e:  # noqa: BLE001
            self._last_simulator_error = f"{type(e).__name__}: {e}"
        else:
            if isinstance(sim, Err):
                self._last_simulator_error = sim.failure
            else:
                self._last_simulator_error = None
                for d in sim.value:
                    await self._resolver.remember_kind(
                        d.serial, Platform.IOS, DeviceClass.SIMULATOR
                    )
                    merged.append(d)
        return ok(merged)

    async def get_device(self, serial: str) -> Result[Device]:
        kind_res = await self._resolver.kind_for(serial)
        if not isinstance(kind_res, Err):
            target = (
                self._simulator
                if kind_res.value.device_class is DeviceClass.SIMULATOR
                else self._physical
            )
            return await target.get_device(serial)
        # Cache miss: probe both, remember winner.
        for repo, cls in (
            (self._physical, DeviceClass.PHYSICAL),
            (self._simulator, DeviceClass.SIMULATOR),
        ):
            res = await repo.get_device(serial)
            if not isinstance(res, Err):
                await self._resolver.remember_kind(serial, Platform.IOS, cls)
                return res
        return err(
            DeviceNotFoundFailure(
                message=f"iOS device {serial} not found (physical or simulator)",
                next_action="list_devices",
            )
        )


class MultiSourceIosLifecycleRepository(_IosSourceRouter, LifecycleRepository):
    async def install(
        self, serial: str, bundle_path: Path, replace: bool = True
    ) -> Result[None]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.install(serial, bundle_path, replace)

    async def uninstall(self, serial: str, package_id: str) -> Result[None]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.uninstall(serial, package_id)

    async def launch(
        self, serial: str, package_id: str, activity: str | None = None
    ) -> Result[None]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.launch(serial, package_id, activity)

    async def stop(self, serial: str, package_id: str) -> Result[None]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.stop(serial, package_id)

    async def clear_data(self, serial: str, package_id: str) -> Result[None]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.clear_data(serial, package_id)

    async def grant_permission(
        self, serial: str, package_id: str, permission: str
    ) -> Result[None]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.grant_permission(serial, package_id, permission)


class MultiSourceIosObservationRepository(_IosSourceRouter, ObservationRepository):
    async def screenshot(self, serial: str, output_path: Path) -> Result[Path]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.screenshot(serial, output_path)

    async def start_recording(self, serial: str, output_path: Path) -> Result[None]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.start_recording(serial, output_path)

    async def stop_recording(self, serial: str) -> Result[Path]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.stop_recording(serial)

    async def read_logs(
        self,
        serial: str,
        since_s: int = 30,
        tag: str | None = None,
        min_level: LogLevel = LogLevel.WARN,
        max_lines: int = 500,
    ) -> Result[list[LogEntry]]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.read_logs(
            serial, since_s=since_s, tag=tag, min_level=min_level, max_lines=max_lines
        )

    async def tail_logs_until(
        self,
        serial: str,
        until_pattern: str,
        tag: str | None = None,
        timeout_s: float = 30.0,
    ) -> Result[list[LogEntry]]:
        impl = await self._route(serial)
        if isinstance(impl, Err):
            return impl
        return await impl.value.tail_logs_until(
            serial, until_pattern=until_pattern, tag=tag, timeout_s=timeout_s
        )
