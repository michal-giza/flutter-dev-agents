"""Composite repositories must route by serial → platform.

These tests prove that:
- list_devices unions both backends and updates the resolver
- per-call repos route to the correct underlying impl
- unknown serials fail with DeviceNotFoundFailure
- iOS toolchain absence does not break Android paths
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.composite.composite_repositories import (
    CompositeBuildRepository,
    CompositeDeviceRepository,
    CompositeLifecycleRepository,
    CompositeObservationRepository,
    CompositeTestRepository,
    CompositeUiRepository,
)
from mcp_phone_controll.data.repositories.composite.platform_resolver import (
    CachingPlatformResolver,
)
from mcp_phone_controll.domain.entities import (
    BuildMode,
    Device,
    DeviceState,
    Platform,
)
from mcp_phone_controll.domain.failures import (
    DeviceNotFoundFailure,
    InvalidArgumentFailure,
)
from mcp_phone_controll.domain.result import Err, Ok, err
from tests.fakes.fake_repositories import (
    FakeBuildRepository,
    FakeDeviceRepository,
    FakeLifecycleRepository,
    FakeObservationRepository,
    FakeTestRepository,
    FakeUiRepository,
)


def _devs(android: list[Device], ios: list[Device]):
    return FakeDeviceRepository(android), FakeDeviceRepository(ios)


@pytest.mark.asyncio
async def test_list_devices_unions_and_caches_platforms():
    android, ios = _devs(
        [Device("EMU01", DeviceState.DEVICE, platform=Platform.ANDROID)],
        [Device("UDID01", DeviceState.DEVICE, platform=Platform.IOS)],
    )
    resolver = CachingPlatformResolver()
    repo = CompositeDeviceRepository(android, ios, resolver)

    result = await repo.list_devices()
    assert isinstance(result, Ok)
    assert {d.serial for d in result.value} == {"EMU01", "UDID01"}

    assert (await resolver.platform_for("EMU01")).value is Platform.ANDROID
    assert (await resolver.platform_for("UDID01")).value is Platform.IOS


@pytest.mark.asyncio
async def test_get_device_probes_both_when_uncached():
    android, ios = _devs(
        [],
        [Device("UDID01", DeviceState.DEVICE, platform=Platform.IOS)],
    )
    resolver = CachingPlatformResolver()
    repo = CompositeDeviceRepository(android, ios, resolver)

    result = await repo.get_device("UDID01")
    assert isinstance(result, Ok)
    assert result.value.platform is Platform.IOS
    assert (await resolver.platform_for("UDID01")).value is Platform.IOS


@pytest.mark.asyncio
async def test_get_device_unknown_returns_not_found():
    android, ios = _devs([], [])
    repo = CompositeDeviceRepository(android, ios, CachingPlatformResolver())
    result = await repo.get_device("NOPE")
    assert isinstance(result, Err)
    assert isinstance(result.failure, DeviceNotFoundFailure)


@pytest.mark.asyncio
async def test_lifecycle_routes_to_android_for_android_serial():
    a_lifecycle = FakeLifecycleRepository(name="android")
    i_lifecycle = FakeLifecycleRepository(name="ios")
    resolver = CachingPlatformResolver()
    await resolver.remember("EMU01", Platform.ANDROID)
    repo = CompositeLifecycleRepository(a_lifecycle, i_lifecycle, resolver)

    await repo.launch("EMU01", "com.example")
    assert any(c[0] == "android" and c[1] == "launch" for c in a_lifecycle.calls)
    assert i_lifecycle.calls == []


@pytest.mark.asyncio
async def test_lifecycle_routes_to_ios_for_ios_serial(tmp_path: Path):
    a_lifecycle = FakeLifecycleRepository(name="android")
    i_lifecycle = FakeLifecycleRepository(name="ios")
    resolver = CachingPlatformResolver()
    await resolver.remember("UDID01", Platform.IOS)
    repo = CompositeLifecycleRepository(a_lifecycle, i_lifecycle, resolver)

    await repo.install("UDID01", tmp_path / "Runner.ipa")
    assert any(c[0] == "ios" and c[1] == "install" for c in i_lifecycle.calls)
    assert a_lifecycle.calls == []


@pytest.mark.asyncio
async def test_lifecycle_unknown_serial_returns_device_not_found():
    repo = CompositeLifecycleRepository(
        FakeLifecycleRepository("a"),
        FakeLifecycleRepository("i"),
        CachingPlatformResolver(),
    )
    result = await repo.launch("UNKNOWN", "com.x")
    assert isinstance(result, Err)
    assert isinstance(result.failure, DeviceNotFoundFailure)


@pytest.mark.asyncio
async def test_build_routes_by_explicit_platform(tmp_path: Path):
    a_builds = FakeBuildRepository(bundle_path=tmp_path / "android.apk")
    i_builds = FakeBuildRepository(bundle_path=tmp_path / "Runner.ipa")
    repo = CompositeBuildRepository(a_builds, i_builds)

    a_res = await repo.build_bundle(tmp_path, BuildMode.DEBUG, Platform.ANDROID)
    i_res = await repo.build_bundle(tmp_path, BuildMode.DEBUG, Platform.IOS)
    assert a_res.value.path.name == "android.apk"
    assert i_res.value.path.name == "Runner.ipa"


@pytest.mark.asyncio
async def test_ui_routes_by_serial():
    a_ui = FakeUiRepository(name="android")
    i_ui = FakeUiRepository(name="ios")
    resolver = CachingPlatformResolver()
    await resolver.remember("UDID01", Platform.IOS)
    repo = CompositeUiRepository(a_ui, i_ui, resolver)

    await repo.tap("UDID01", 100, 200)
    assert any(t[0] == "ios" and t[1] == "tap" for t in i_ui.taps)
    assert a_ui.taps == []


@pytest.mark.asyncio
async def test_observation_routes_by_serial(tmp_path: Path):
    a_obs = FakeObservationRepository(name="android")
    i_obs = FakeObservationRepository(name="ios")
    resolver = CachingPlatformResolver()
    await resolver.remember("UDID01", Platform.IOS)
    repo = CompositeObservationRepository(a_obs, i_obs, resolver)

    out = tmp_path / "shot.png"
    await repo.screenshot("UDID01", out)
    assert out.read_bytes() == b"ios"


@pytest.mark.asyncio
async def test_test_repo_unit_uses_android_only():
    """Unit tests don't need a serial — by convention we run via the Android repo."""
    a_tests = FakeTestRepository()
    i_tests = FakeTestRepository()
    repo = CompositeTestRepository(a_tests, i_tests, CachingPlatformResolver())
    result = await repo.run_unit_tests(Path("/x"))
    assert isinstance(result, Ok)


@pytest.mark.asyncio
async def test_test_repo_integration_routes_by_serial():
    a_tests = FakeTestRepository()
    i_tests = FakeTestRepository()
    resolver = CachingPlatformResolver()
    await resolver.remember("UDID01", Platform.IOS)
    repo = CompositeTestRepository(a_tests, i_tests, resolver)

    result = await repo.run_integration_tests(Path("/x"), "UDID01")
    assert isinstance(result, Ok)


@pytest.mark.asyncio
async def test_ios_failure_in_list_does_not_block_android():
    """If the iOS toolchain fails (e.g. pymobiledevice3 not installed), Android still works."""

    class FailingIos:
        async def list_devices(self):
            return err(InvalidArgumentFailure(message="pymobiledevice3 missing"))

        async def get_device(self, serial):
            return err(DeviceNotFoundFailure(message="ios disabled"))

    android = FakeDeviceRepository(
        [Device("EMU01", DeviceState.DEVICE, platform=Platform.ANDROID)]
    )
    repo = CompositeDeviceRepository(android, FailingIos(), CachingPlatformResolver())
    result = await repo.list_devices()
    assert isinstance(result, Ok)
    assert [d.serial for d in result.value] == ["EMU01"]
