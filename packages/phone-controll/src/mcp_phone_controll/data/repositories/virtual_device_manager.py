"""VirtualDeviceManager — start/stop AVDs and iOS Simulators."""

from __future__ import annotations

import asyncio

from ...domain.entities import Device, DeviceClass, DeviceState, Platform
from ...domain.failures import (
    DeviceNotFoundFailure,
    FlutterCliFailure,
    InvalidArgumentFailure,
    LaunchFailure,
)
from ...domain.repositories import VirtualDeviceManager
from ...domain.result import Result, err, ok
from ...infrastructure.adb_client import AdbClient
from ...infrastructure.android_emulator_cli import AndroidEmulatorCli
from ...infrastructure.simctl_client import SimctlClient
from ..parsers.simctl_parser import parse_simctl_devices


class CompositeVirtualDeviceManager(VirtualDeviceManager):
    def __init__(
        self,
        emulator_cli: AndroidEmulatorCli,
        simctl: SimctlClient,
        adb: AdbClient,
    ) -> None:
        self._emulator = emulator_cli
        self._simctl = simctl
        self._adb = adb

    # ----- AVD ----------------------------------------------------------

    async def list_avds(self) -> Result[list[str]]:
        result = await self._emulator.list_avds()
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="emulator -list-avds failed",
                    details={"stderr": result.stderr},
                    next_action="install_android_sdk",
                )
            )
        names = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and not line.startswith("INFO")
        ]
        return ok(names)

    async def start_emulator(
        self, avd_name: str, headless: bool = False
    ) -> Result[str]:
        if not avd_name:
            return err(
                InvalidArgumentFailure(
                    message="avd_name is required", next_action="fix_arguments"
                )
            )
        # Spawn detached and poll adb until a new emulator-* serial appears.
        before = await self._serials_set()
        try:
            proc = await self._emulator.start(avd_name, headless=headless)
        except FileNotFoundError as e:
            return err(
                LaunchFailure(
                    message=f"emulator binary not found: {e}",
                    next_action="install_android_sdk",
                )
            )
        # We don't await the emulator process — it runs for the session lifetime.
        # Just give it up to 90 s to register with adb.
        deadline = asyncio.get_event_loop().time() + 90
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(2)
            current = await self._serials_set()
            new = current - before
            for serial in new:
                if serial.startswith("emulator-"):
                    # Confirm the emulator finished booting via adb getprop.
                    boot_check = await self._adb.shell(
                        serial, "getprop", "sys.boot_completed", timeout_s=10.0
                    )
                    if boot_check.ok and boot_check.stdout.strip() == "1":
                        return ok(serial)
        # Best-effort cleanup of the process if it didn't register
        if proc.returncode is None:
            proc.terminate()
        return err(
            LaunchFailure(
                message=f"emulator '{avd_name}' did not register with adb in 90s",
                next_action="check_avd_health",
            )
        )

    async def _serials_set(self) -> set[str]:
        result = await self._adb.devices_l(timeout_s=5.0)
        if not result.ok:
            return set()
        from ..parsers.adb_devices_parser import parse_devices_l

        return {d.serial for d in parse_devices_l(result.stdout)}

    # ----- shared shutdown ---------------------------------------------

    async def stop_virtual_device(self, serial: str) -> Result[None]:
        if serial.startswith("emulator-"):
            result = await self._adb.shell(serial, "reboot", "-p", timeout_s=10.0)
            # `adb -s emulator-X emu kill` is the canonical way; reboot -p is a
            # fallback. Use emu kill primarily.
            kill_result = await self._adb._runner.run(  # noqa: SLF001 — single-purpose
                ["adb", "-s", serial, "emu", "kill"], timeout_s=10.0
            )
            if not kill_result.ok and not result.ok:
                return err(
                    FlutterCliFailure(
                        message="failed to stop emulator",
                        details={"stderr": kill_result.stderr},
                    )
                )
            return ok(None)
        # Otherwise treat as iOS simulator UDID.
        result = await self._simctl.shutdown(serial)
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="simctl shutdown failed",
                    details={"stderr": result.stderr},
                )
            )
        return ok(None)

    # ----- iOS simulators ----------------------------------------------

    async def list_simulators(
        self, include_shutdown: bool = True
    ) -> Result[list[Device]]:
        result = await self._simctl.list_devices_json()
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="xcrun simctl list devices failed",
                    details={"stderr": result.stderr},
                    next_action="install_xcode_clt",
                )
            )
        return ok(
            parse_simctl_devices(result.stdout, only_booted=not include_shutdown)
        )

    async def boot_simulator(self, name_or_udid: str) -> Result[Device]:
        # Find by name OR udid in the full list (including shutdown).
        listed = await self.list_simulators(include_shutdown=True)
        if listed.is_err:
            return listed  # type: ignore[return-value]
        candidates = [
            d
            for d in listed.value  # type: ignore[union-attr]
            if d.serial == name_or_udid or (d.model or "") == name_or_udid
        ]
        if not candidates:
            return err(
                DeviceNotFoundFailure(
                    message=f"no simulator named or with udid {name_or_udid!r}",
                    next_action="list_simulators",
                )
            )
        target = candidates[0]
        boot = await self._simctl.boot(target.serial)
        if not boot.ok and "Booted" not in boot.stderr:
            return err(
                LaunchFailure(
                    message="simctl boot failed",
                    details={"stderr": boot.stderr},
                )
            )
        # Re-emit the device in DEVICE state so callers can immediately select it.
        return ok(
            Device(
                serial=target.serial,
                state=DeviceState.DEVICE,
                model=target.model,
                os_version=target.os_version,
                platform=Platform.IOS,
                device_class=DeviceClass.SIMULATOR,
            )
        )
