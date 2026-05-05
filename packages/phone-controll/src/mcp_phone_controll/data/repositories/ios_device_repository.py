"""DeviceRepository implementation backed by pymobiledevice3."""

from __future__ import annotations

from ...domain.entities import Device
from ...domain.failures import DeviceNotFoundFailure, FlutterCliFailure
from ...domain.repositories import DeviceRepository
from ...domain.result import Result, err, ok
from ...infrastructure.pymobiledevice3_cli import PyMobileDevice3Cli
from ..parsers.pymobiledevice3_parser import parse_usbmux_list


class IosDeviceRepository(DeviceRepository):
    def __init__(self, cli: PyMobileDevice3Cli) -> None:
        self._cli = cli

    async def list_devices(self) -> Result[list[Device]]:
        result = await self._cli.usbmux_list()
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="pymobiledevice3 usbmux list failed",
                    details={"stderr": result.stderr},
                )
            )
        return ok(parse_usbmux_list(result.stdout))

    async def get_device(self, serial: str) -> Result[Device]:
        listed = await self.list_devices()
        if listed.is_err:
            return listed  # type: ignore[return-value]
        for device in listed.value:  # type: ignore[union-attr]
            if device.serial == serial:
                return ok(device)
        return err(DeviceNotFoundFailure(message=f"iOS device {serial} not found"))
