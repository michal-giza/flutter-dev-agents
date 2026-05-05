"""LifecycleRepository implementation backed by adb."""

from __future__ import annotations

from pathlib import Path

from ...domain.failures import (
    AdbFailure,
    InstallFailure,
    LaunchFailure,
)
from ...domain.repositories import LifecycleRepository
from ...domain.result import Result, err, ok
from ...infrastructure.adb_client import AdbClient


class AdbLifecycleRepository(LifecycleRepository):
    def __init__(self, adb: AdbClient) -> None:
        self._adb = adb

    async def install(
        self, serial: str, bundle_path: Path, replace: bool = True
    ) -> Result[None]:
        result = await self._adb.install(serial, bundle_path, replace=replace)
        if not result.ok or "Failure" in result.stdout:
            return err(
                InstallFailure(
                    message="adb install failed",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        return ok(None)

    async def uninstall(self, serial: str, package_id: str) -> Result[None]:
        result = await self._adb.uninstall(serial, package_id)
        if not result.ok:
            return err(
                AdbFailure(message="adb uninstall failed", details={"stderr": result.stderr})
            )
        return ok(None)

    async def launch(
        self, serial: str, package_id: str, activity: str | None = None
    ) -> Result[None]:
        if activity:
            target = f"{package_id}/{activity}"
            result = await self._adb.shell(serial, "am", "start", "-n", target)
        else:
            result = await self._adb.shell(
                serial,
                "monkey",
                "-p",
                package_id,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            )
        if not result.ok:
            return err(
                LaunchFailure(
                    message="launch failed",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        return ok(None)

    async def stop(self, serial: str, package_id: str) -> Result[None]:
        result = await self._adb.shell(serial, "am", "force-stop", package_id)
        if not result.ok:
            return err(AdbFailure(message="force-stop failed", details={"stderr": result.stderr}))
        return ok(None)

    async def clear_data(self, serial: str, package_id: str) -> Result[None]:
        result = await self._adb.shell(serial, "pm", "clear", package_id)
        if not result.ok or "Success" not in result.stdout:
            return err(
                AdbFailure(
                    message="pm clear failed",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        return ok(None)

    async def grant_permission(
        self, serial: str, package_id: str, permission: str
    ) -> Result[None]:
        result = await self._adb.shell(serial, "pm", "grant", package_id, permission)
        if not result.ok:
            return err(
                AdbFailure(
                    message="pm grant failed",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        return ok(None)
