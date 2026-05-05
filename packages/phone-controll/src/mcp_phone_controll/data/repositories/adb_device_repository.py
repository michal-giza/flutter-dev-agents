"""DeviceRepository implementation backed by adb."""

from __future__ import annotations

from ...domain.entities import Device, DeviceClass, Platform
from ...domain.failures import AdbFailure, DeviceNotFoundFailure
from ...domain.repositories import DeviceRepository
from ...domain.result import Result, err, ok
from ...infrastructure.adb_client import AdbClient
from ..parsers.adb_devices_parser import parse_devices_l


class AdbDeviceRepository(DeviceRepository):
    def __init__(self, adb: AdbClient) -> None:
        self._adb = adb

    async def list_devices(self) -> Result[list[Device]]:
        result = await self._adb.devices_l()
        if not result.ok:
            return err(AdbFailure(message="adb devices failed", details={"stderr": result.stderr}))
        devices = parse_devices_l(result.stdout)

        # Best-effort enrich Android version for online devices.
        enriched: list[Device] = []
        for device in devices:
            if device.state.value != "device":
                enriched.append(device)
                continue
            prop = await self._adb.get_prop(device.serial, "ro.build.version.release")
            version = prop.stdout.strip() if prop.ok else None
            enriched.append(
                Device(
                    serial=device.serial,
                    state=device.state,
                    model=device.model,
                    os_version=version,
                    platform=Platform.ANDROID,
                    device_class=device.device_class,
                )
            )
        return ok(enriched)

    async def get_device(self, serial: str) -> Result[Device]:
        listed = await self.list_devices()
        if listed.is_err:
            return listed  # type: ignore[return-value]
        for device in listed.value:  # type: ignore[union-attr]
            if device.serial == serial:
                return ok(device)
        return err(DeviceNotFoundFailure(message=f"Device {serial} not found"))
