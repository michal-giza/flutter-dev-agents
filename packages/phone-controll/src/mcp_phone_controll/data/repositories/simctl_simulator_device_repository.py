"""DeviceRepository implementation for iOS Simulators (xcrun simctl)."""

from __future__ import annotations

from ...domain.entities import Device
from ...domain.failures import DeviceNotFoundFailure, FlutterCliFailure
from ...domain.repositories import DeviceRepository
from ...domain.result import Result, err, ok
from ...infrastructure.simctl_client import SimctlClient
from ..parsers.simctl_parser import parse_simctl_devices


class SimctlSimulatorDeviceRepository(DeviceRepository):
    """Lists iOS simulators. By default only booted ones — set
    `include_shutdown=True` to also expose shutdown ones (useful for boot tools).
    """

    def __init__(
        self, client: SimctlClient, include_shutdown: bool = False
    ) -> None:
        self._client = client
        self._include_shutdown = include_shutdown

    async def list_devices(self) -> Result[list[Device]]:
        result = await self._client.list_devices_json()
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="xcrun simctl list devices failed",
                    details={"stderr": result.stderr},
                    next_action="install_xcode_clt",
                )
            )
        return ok(parse_simctl_devices(result.stdout, only_booted=not self._include_shutdown))

    async def get_device(self, serial: str) -> Result[Device]:
        listed = await self.list_devices()
        if listed.is_err:
            return listed  # type: ignore[return-value]
        for d in listed.value:  # type: ignore[union-attr]
            if d.serial == serial:
                return ok(d)
        return err(
            DeviceNotFoundFailure(
                message=f"iOS simulator {serial} not found",
                next_action="list_devices",
            )
        )
