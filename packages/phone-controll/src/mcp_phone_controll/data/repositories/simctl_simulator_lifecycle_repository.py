"""LifecycleRepository implementation for iOS Simulators."""

from __future__ import annotations

from pathlib import Path

from ...domain.failures import (
    FlutterCliFailure,
    InstallFailure,
    LaunchFailure,
)
from ...domain.repositories import LifecycleRepository
from ...domain.result import Result, err, ok
from ...infrastructure.simctl_client import SimctlClient

# Map our generic Android-style permission names to simctl privacy services
# where there's a sensible mapping; otherwise pass through verbatim.
_PERMISSION_MAP = {
    "android.permission.CAMERA": "camera",
    "android.permission.RECORD_AUDIO": "microphone",
    "android.permission.ACCESS_FINE_LOCATION": "location",
    "android.permission.ACCESS_COARSE_LOCATION": "location",
    "android.permission.READ_CONTACTS": "contacts",
    "android.permission.WRITE_CONTACTS": "contacts",
    "android.permission.READ_MEDIA_IMAGES": "photos",
    "android.permission.READ_EXTERNAL_STORAGE": "photos",
}


class SimctlSimulatorLifecycleRepository(LifecycleRepository):
    """iOS Simulator lifecycle via xcrun simctl.

    Notes:
    - install accepts .app bundles (NOT .ipa). Flutter `flutter build ios --simulator`
      produces an .app at build/ios/iphonesimulator/Runner.app.
    - clear_data isn't a native simctl op; we approximate with uninstall.
    - grant_permission maps Android permission strings to simctl privacy services.
    """

    def __init__(self, client: SimctlClient) -> None:
        self._client = client

    async def install(
        self, serial: str, bundle_path: Path, replace: bool = True
    ) -> Result[None]:
        result = await self._client.install(serial, bundle_path)
        if not result.ok:
            return err(
                InstallFailure(
                    message="simctl install failed",
                    details={"stderr": result.stderr},
                    next_action="check_bundle_format",
                )
            )
        return ok(None)

    async def uninstall(self, serial: str, package_id: str) -> Result[None]:
        result = await self._client.uninstall(serial, package_id)
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="simctl uninstall failed",
                    details={"stderr": result.stderr},
                )
            )
        return ok(None)

    async def launch(
        self, serial: str, package_id: str, activity: str | None = None
    ) -> Result[None]:
        # `activity` is Android-only; ignored on iOS simulators.
        result = await self._client.launch(serial, package_id)
        if not result.ok:
            return err(
                LaunchFailure(
                    message="simctl launch failed",
                    details={"stderr": result.stderr},
                )
            )
        return ok(None)

    async def stop(self, serial: str, package_id: str) -> Result[None]:
        result = await self._client.terminate(serial, package_id)
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="simctl terminate failed",
                    details={"stderr": result.stderr},
                )
            )
        return ok(None)

    async def clear_data(self, serial: str, package_id: str) -> Result[None]:
        # Approximation: uninstall removes both the app and its data.
        # Reinstall is the caller's responsibility (matches install_app loop).
        return await self.uninstall(serial, package_id)

    async def grant_permission(
        self, serial: str, package_id: str, permission: str
    ) -> Result[None]:
        service = _PERMISSION_MAP.get(permission, permission.lower())
        result = await self._client.privacy_grant(serial, service, package_id)
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="simctl privacy grant failed",
                    details={
                        "stderr": result.stderr,
                        "service": service,
                        "hint": (
                            "valid services: camera, microphone, location, photos, "
                            "contacts, calendar, reminders, media-library, motion, all"
                        ),
                    },
                    next_action="fix_arguments",
                )
            )
        return ok(None)
