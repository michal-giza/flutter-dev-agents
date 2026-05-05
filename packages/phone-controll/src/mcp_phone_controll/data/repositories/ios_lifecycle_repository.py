"""LifecycleRepository implementation backed by pymobiledevice3."""

from __future__ import annotations

from pathlib import Path

from ...domain.failures import (
    FlutterCliFailure,
    InstallFailure,
    LaunchFailure,
)
from ...domain.repositories import LifecycleRepository
from ...domain.result import Result, err, ok
from ...infrastructure.pymobiledevice3_cli import PyMobileDevice3Cli


class IosLifecycleRepository(LifecycleRepository):
    """iOS lifecycle. `clear_data` and `grant_permission` are not supported on iOS."""

    def __init__(self, cli: PyMobileDevice3Cli) -> None:
        self._cli = cli

    async def install(
        self, serial: str, bundle_path: Path, replace: bool = True
    ) -> Result[None]:
        result = await self._cli.install(serial, bundle_path)
        if not result.ok:
            return err(
                InstallFailure(
                    message="pymobiledevice3 install failed",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        return ok(None)

    async def uninstall(self, serial: str, package_id: str) -> Result[None]:
        result = await self._cli.uninstall(serial, package_id)
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="pymobiledevice3 uninstall failed",
                    details={"stderr": result.stderr},
                )
            )
        return ok(None)

    async def launch(
        self, serial: str, package_id: str, activity: str | None = None
    ) -> Result[None]:
        # `activity` is Android-only; ignored on iOS.
        result = await self._cli.launch(serial, package_id)
        if not result.ok:
            return err(
                LaunchFailure(
                    message="pymobiledevice3 launch failed (DDI mounted?)",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        return ok(None)

    async def stop(self, serial: str, package_id: str) -> Result[None]:
        result = await self._cli.kill(serial, package_id)
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="pymobiledevice3 kill failed",
                    details={"stderr": result.stderr},
                )
            )
        return ok(None)

    async def clear_data(self, serial: str, package_id: str) -> Result[None]:
        return err(
            FlutterCliFailure(
                message="clear_data is not supported on iOS",
                details={"alternative": "uninstall and reinstall"},
            )
        )

    async def grant_permission(
        self, serial: str, package_id: str, permission: str
    ) -> Result[None]:
        return err(
            FlutterCliFailure(
                message="grant_permission is not supported on iOS",
                details={
                    "note": "iOS permissions must be accepted interactively or via TCC profile"
                },
            )
        )
