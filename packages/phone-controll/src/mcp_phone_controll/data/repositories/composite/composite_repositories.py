"""Composite repositories that route every call to an Android or iOS implementation
based on serial → Platform lookup.

Each composite implements the same domain Protocol as its delegates, so use cases
remain identical. The single chokepoint for "which platform owns this serial?" is
the PlatformResolver.
"""

from __future__ import annotations

from pathlib import Path

from ....domain.entities import (
    AppBundle,
    BuildMode,
    Device,
    LogEntry,
    LogLevel,
    Platform,
    TestRun,
    UiElement,
)
from ....domain.failures import DeviceNotFoundFailure, InvalidArgumentFailure
from ....domain.repositories import (
    BuildRepository,
    DeviceRepository,
    LifecycleRepository,
    ObservationRepository,
    TestRepository,
    UiRepository,
)
from ....domain.result import Err, Result, err, ok
from .platform_resolver import CachingPlatformResolver


class CompositeDeviceRepository(DeviceRepository):
    """Unions devices from every per-platform repo. Updates the resolver cache."""

    def __init__(
        self,
        android: DeviceRepository,
        ios: DeviceRepository,
        resolver: CachingPlatformResolver,
    ) -> None:
        self._android = android
        self._ios = ios
        self._resolver = resolver
        self._last_ios_error = None

    async def list_devices(self) -> Result[list[Device]]:
        merged: list[Device] = []
        a = await self._android.list_devices()
        if isinstance(a, Err):
            return a
        for d in a.value:
            await self._resolver.remember_kind(d.serial, Platform.ANDROID, d.device_class)
            merged.append(d)
        # iOS enumeration must never propagate an exception: missing toolchain,
        # missing python module, dead tunneld — Android always wins.
        try:
            i = await self._ios.list_devices()
        except Exception as e:  # noqa: BLE001
            self._last_ios_error = f"{type(e).__name__}: {e}"
            return ok(merged)
        if isinstance(i, Err):
            self._last_ios_error = i.failure
        else:
            self._last_ios_error = None
            for d in i.value:
                await self._resolver.remember_kind(d.serial, Platform.IOS, d.device_class)
                merged.append(d)
        return ok(merged)

    async def get_device(self, serial: str) -> Result[Device]:
        # Try resolver-known platform first; otherwise probe both.
        platform_res = await self._resolver.platform_for(serial)
        if not isinstance(platform_res, Err):
            target = self._android if platform_res.value is Platform.ANDROID else self._ios
            return await target.get_device(serial)
        for repo, platform in ((self._android, Platform.ANDROID), (self._ios, Platform.IOS)):
            res = await repo.get_device(serial)
            if not isinstance(res, Err):
                await self._resolver.remember(serial, platform)
                return res
        return err(DeviceNotFoundFailure(message=f"device {serial} not found on any platform"))


class _PlatformRouted:
    """Mixin that resolves serial → impl. SRP: routing only."""

    def __init__(
        self, android, ios, resolver: CachingPlatformResolver
    ) -> None:
        self._android = android
        self._ios = ios
        self._resolver = resolver

    async def _route(self, serial: str):
        platform_res = await self._resolver.platform_for(serial)
        if isinstance(platform_res, Err):
            return platform_res
        impl = self._android if platform_res.value is Platform.ANDROID else self._ios
        return ok(impl)


class CompositeLifecycleRepository(_PlatformRouted, LifecycleRepository):
    async def install(
        self, serial: str, bundle_path: Path, replace: bool = True
    ) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.install(serial, bundle_path, replace)

    async def uninstall(self, serial: str, package_id: str) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.uninstall(serial, package_id)

    async def launch(
        self, serial: str, package_id: str, activity: str | None = None
    ) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.launch(serial, package_id, activity)

    async def stop(self, serial: str, package_id: str) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.stop(serial, package_id)

    async def clear_data(self, serial: str, package_id: str) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.clear_data(serial, package_id)

    async def grant_permission(
        self, serial: str, package_id: str, permission: str
    ) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.grant_permission(serial, package_id, permission)


class CompositeBuildRepository(BuildRepository):
    """Builds route by explicit Platform parameter — no serial available."""

    def __init__(self, android: BuildRepository, ios: BuildRepository) -> None:
        self._android = android
        self._ios = ios

    async def build_bundle(
        self,
        project_path: Path,
        mode: BuildMode,
        platform: Platform = Platform.ANDROID,
        flavor: str | None = None,
    ) -> Result[AppBundle]:
        if platform is Platform.ANDROID:
            return await self._android.build_bundle(project_path, mode, platform, flavor)
        if platform is Platform.IOS:
            return await self._ios.build_bundle(project_path, mode, platform, flavor)
        return err(InvalidArgumentFailure(message=f"unsupported platform: {platform}"))


class CompositeUiRepository(_PlatformRouted, UiRepository):
    async def tap(self, serial: str, x: int, y: int) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.tap(serial, x, y)

    async def tap_text(self, serial: str, text: str, exact: bool = False) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.tap_text(serial, text, exact)

    async def swipe(
        self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.swipe(serial, x1, y1, x2, y2, duration_ms)

    async def type_text(self, serial: str, text: str) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.type_text(serial, text)

    async def press_key(self, serial: str, keycode: str) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.press_key(serial, keycode)

    async def find(
        self,
        serial: str,
        text: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        timeout_s: float = 5.0,
    ) -> Result[UiElement | None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.find(
            serial, text=text, resource_id=resource_id, class_name=class_name, timeout_s=timeout_s
        )

    async def wait_for(
        self,
        serial: str,
        text: str | None = None,
        resource_id: str | None = None,
        timeout_s: float = 10.0,
    ) -> Result[UiElement]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.wait_for(
            serial, text=text, resource_id=resource_id, timeout_s=timeout_s
        )

    async def dump_ui(self, serial: str) -> Result[str]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.dump_ui(serial)


class CompositeObservationRepository(_PlatformRouted, ObservationRepository):
    async def screenshot(self, serial: str, output_path: Path) -> Result[Path]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.screenshot(serial, output_path)

    async def start_recording(self, serial: str, output_path: Path) -> Result[None]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.start_recording(serial, output_path)

    async def stop_recording(self, serial: str) -> Result[Path]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.stop_recording(serial)

    async def read_logs(
        self,
        serial: str,
        since_s: int = 30,
        tag: str | None = None,
        min_level: LogLevel = LogLevel.WARN,
        max_lines: int = 500,
    ) -> Result[list[LogEntry]]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.read_logs(
            serial, since_s=since_s, tag=tag, min_level=min_level, max_lines=max_lines
        )

    async def tail_logs_until(
        self,
        serial: str,
        until_pattern: str,
        tag: str | None = None,
        timeout_s: float = 30.0,
    ) -> Result[list[LogEntry]]:
        impl_res = await self._route(serial)
        if isinstance(impl_res, Err):
            return impl_res
        return await impl_res.value.tail_logs_until(
            serial, until_pattern=until_pattern, tag=tag, timeout_s=timeout_s
        )


class CompositeTestRepository(TestRepository):
    """Routes test runs by *test framework first* (Patrol if available, else
    plain Flutter), then by platform. Project inspection picks the framework.

    Adding a new framework (XCUITest, Espresso, Detox, Playwright...) means:
      1. Implement TestRepository for that framework.
      2. Add a TestFramework enum value + ProjectInspector recognizing it.
      3. Inject the new impl here keyed by TestFramework.
    """

    def __init__(
        self,
        android: TestRepository,
        ios: TestRepository,
        resolver: CachingPlatformResolver,
        framework_runners: dict | None = None,
        inspector=None,
    ) -> None:
        self._android = android
        self._ios = ios
        self._resolver = resolver
        # Optional: per-framework runners (e.g. {TestFramework.PATROL: PatrolTestRepository}).
        self._framework_runners = framework_runners or {}
        self._inspector = inspector

    async def run_unit_tests(self, project_path: Path) -> Result[TestRun]:
        runner = await self._pick_runner(project_path) or self._android
        return await runner.run_unit_tests(project_path)

    async def run_integration_tests(
        self,
        project_path: Path,
        device_serial: str,
        test_path: str = "integration_test/",
    ) -> Result[TestRun]:
        framework_runner = await self._pick_runner(project_path)
        if framework_runner is not None:
            return await framework_runner.run_integration_tests(
                project_path, device_serial, test_path
            )
        platform_res = await self._resolver.platform_for(device_serial)
        if isinstance(platform_res, Err):
            return platform_res
        impl = self._android if platform_res.value is Platform.ANDROID else self._ios
        return await impl.run_integration_tests(project_path, device_serial, test_path)

    async def _pick_runner(self, project_path: Path):
        if self._inspector is None or not self._framework_runners:
            return None
        info_res = await self._inspector.inspect(project_path)
        if isinstance(info_res, Err):
            return None
        for framework in info_res.value.test_frameworks:
            runner = self._framework_runners.get(framework)
            if runner is not None:
                return runner
        return None
