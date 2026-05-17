"""Build app bundle and install/uninstall on device."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import AppBundle, BuildMode, Platform
from ..failures import FilesystemFailure, InvalidArgumentFailure
from ..repositories import (
    BuildRepository,
    DeviceRepository,
    LifecycleRepository,
    SessionStateRepository,
)
from ..result import Err, Result, err, ok
from ._helpers import resolve_serial
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class BuildAppParams:
    project_path: Path
    mode: BuildMode = BuildMode.DEBUG
    platform: Platform = Platform.ANDROID
    flavor: str | None = None


class BuildApp(BaseUseCase[BuildAppParams, AppBundle]):
    def __init__(self, builds: BuildRepository) -> None:
        self._builds = builds

    async def execute(self, params: BuildAppParams) -> Result[AppBundle]:
        return await self._builds.build_bundle(
            params.project_path, params.mode, params.platform, params.flavor
        )


@dataclass(frozen=True, slots=True)
class InstallAppParams:
    bundle_path: Path | None = None
    project_path: Path | None = None
    mode: BuildMode = BuildMode.DEBUG
    platform: Platform | None = None
    flavor: str | None = None
    serial: str | None = None


class InstallApp(BaseUseCase[InstallAppParams, AppBundle]):
    """Install a pre-built bundle, or build then install. Routes by device platform."""

    def __init__(
        self,
        builds: BuildRepository,
        lifecycle: LifecycleRepository,
        devices: DeviceRepository,
        state: SessionStateRepository,
    ) -> None:
        self._builds = builds
        self._lifecycle = lifecycle
        self._devices = devices
        self._state = state

    async def _resolve_platform(
        self, explicit: Platform | None, serial: str
    ) -> Result[Platform]:
        if explicit is not None:
            return ok(explicit)
        device_res = await self._devices.get_device(serial)
        if isinstance(device_res, Err):
            return device_res
        return ok(device_res.value.platform or Platform.ANDROID)

    async def execute(self, params: InstallAppParams) -> Result[AppBundle]:
        if params.bundle_path is None and params.project_path is None:
            return err(
                InvalidArgumentFailure(
                    message="install requires either bundle_path or project_path"
                )
            )

        # Path-traversal guard. install_app EXECUTES the supplied bundle
        # on the device — a prompt-injected `install_app(bundle_path=
        # "/path/to/attacker-controlled.apk")` would install whatever
        # the attacker pointed at. Restrict bundle_path to artifact /
        # tmp / project roots; restrict project_path to project roots.
        from ..path_guard import check_path_allowed, check_project_path_allowed

        if params.bundle_path is not None:
            g = check_path_allowed(
                Path(params.bundle_path).expanduser(),
                tool_name="install_app",
            )
            if not g.ok:
                # Also accept project roots — APKs built from a project
                # legitimately live under ~/Projects/<app>/build/...
                g2 = check_project_path_allowed(
                    Path(params.bundle_path).expanduser(),
                    tool_name="install_app",
                )
                if not g2.ok:
                    return err(
                        FilesystemFailure(
                            message=(
                                f"bundle_path {params.bundle_path} is not "
                                "under an artifact root or a recognised "
                                "project root. Set MCP_INSTALL_APP_ALLOWED_ROOTS "
                                "or MCP_PROJECT_PATHS_ROOTS to extend."
                            ),
                            next_action="path_not_in_allowed_roots",
                            details={
                                "path": str(params.bundle_path),
                                "tried_roots": (
                                    [str(r) for r in g.allowed_roots]
                                    + [str(r) for r in g2.allowed_roots]
                                ),
                            },
                        )
                    )
        if params.project_path is not None:
            g = check_project_path_allowed(
                Path(params.project_path).expanduser(),
                tool_name="install_app",
            )
            if not g.ok:
                return err(
                    FilesystemFailure(
                        message=g.reason or "project_path not allowed",
                        next_action="path_not_in_allowed_roots",
                        details={
                            "project_path": str(params.project_path),
                            "allowed_roots": [str(r) for r in g.allowed_roots],
                        },
                    )
                )

        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res

        platform_res = await self._resolve_platform(params.platform, serial_res.value)
        if isinstance(platform_res, Err):
            return platform_res
        platform = platform_res.value

        if params.bundle_path is not None:
            bundle = AppBundle(
                path=params.bundle_path,
                mode=params.mode,
                platform=platform,
                flavor=params.flavor,
            )
        else:
            assert params.project_path is not None
            build_res = await self._builds.build_bundle(
                params.project_path, params.mode, platform, params.flavor
            )
            if isinstance(build_res, Err):
                return build_res
            bundle = build_res.value

        install_res = await self._lifecycle.install(serial_res.value, bundle.path)
        if isinstance(install_res, Err):
            return install_res
        return ok(bundle)


@dataclass(frozen=True, slots=True)
class UninstallAppParams:
    package_id: str
    serial: str | None = None


class UninstallApp(BaseUseCase[UninstallAppParams, None]):
    def __init__(self, lifecycle: LifecycleRepository, state: SessionStateRepository) -> None:
        self._lifecycle = lifecycle
        self._state = state

    async def execute(self, params: UninstallAppParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._lifecycle.uninstall(serial_res.value, params.package_id)
