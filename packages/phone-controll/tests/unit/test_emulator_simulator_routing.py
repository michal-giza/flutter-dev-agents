"""Tests proving Android-emulator and iOS-simulator paths route correctly
through the multi-source composites.

We use the already-existing fakes for the per-platform repos, just feed them
devices tagged with DeviceClass.EMULATOR / SIMULATOR.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.composite.composite_repositories import (
    CompositeDeviceRepository,
    CompositeLifecycleRepository,
    CompositeObservationRepository,
)
from mcp_phone_controll.data.repositories.composite.platform_resolver import (
    CachingPlatformResolver,
)
from mcp_phone_controll.data.repositories.ios_multi_source import (
    MultiSourceIosDeviceRepository,
    MultiSourceIosLifecycleRepository,
    MultiSourceIosObservationRepository,
)
from mcp_phone_controll.domain.entities import (
    Device,
    DeviceClass,
    DeviceState,
    Platform,
)
from mcp_phone_controll.domain.result import Err, Ok
from tests.fakes.fake_repositories import (
    FakeDeviceRepository,
    FakeLifecycleRepository,
    FakeObservationRepository,
)


# ---- Android emulator: same code path as physical, just tagged differently --


@pytest.mark.asyncio
async def test_android_emulator_appears_with_class_emulator():
    android_devices = FakeDeviceRepository(
        [
            Device(
                "emulator-5554",
                state=DeviceState.DEVICE,
                model="sdk_gphone",
                os_version="14",
                platform=Platform.ANDROID,
                device_class=DeviceClass.EMULATOR,
            )
        ]
    )
    ios_devices = FakeDeviceRepository([])
    resolver = CachingPlatformResolver()
    repo = CompositeDeviceRepository(android_devices, ios_devices, resolver)
    res = await repo.list_devices()
    assert isinstance(res, Ok)
    assert res.value[0].device_class is DeviceClass.EMULATOR
    kind = await resolver.kind_for("emulator-5554")
    assert isinstance(kind, Ok)
    assert kind.value.device_class is DeviceClass.EMULATOR


# ---- iOS multi-source: physical vs simulator routing -----------------------


@pytest.mark.asyncio
async def test_ios_multi_source_unions_and_tags():
    physical = FakeDeviceRepository(
        [
            Device(
                "UDID-PHYS",
                state=DeviceState.DEVICE,
                platform=Platform.IOS,
                device_class=DeviceClass.PHYSICAL,
            )
        ]
    )
    simulator = FakeDeviceRepository(
        [
            Device(
                "UDID-SIM",
                state=DeviceState.DEVICE,
                platform=Platform.IOS,
                device_class=DeviceClass.SIMULATOR,
            )
        ]
    )
    resolver = CachingPlatformResolver()
    repo = MultiSourceIosDeviceRepository(physical, simulator, resolver)
    res = await repo.list_devices()
    assert isinstance(res, Ok)
    serials = {d.serial: d.device_class for d in res.value}
    assert serials["UDID-PHYS"] is DeviceClass.PHYSICAL
    assert serials["UDID-SIM"] is DeviceClass.SIMULATOR


@pytest.mark.asyncio
async def test_ios_lifecycle_routes_simulator_separately(tmp_path: Path):
    physical = FakeLifecycleRepository(name="physical")
    simulator = FakeLifecycleRepository(name="simulator")
    resolver = CachingPlatformResolver()
    await resolver.remember_kind("UDID-SIM", Platform.IOS, DeviceClass.SIMULATOR)
    repo = MultiSourceIosLifecycleRepository(physical, simulator, resolver)

    await repo.install("UDID-SIM", tmp_path / "Runner.app")
    assert any(c[0] == "simulator" and c[1] == "install" for c in simulator.calls)
    assert physical.calls == []


@pytest.mark.asyncio
async def test_ios_lifecycle_routes_physical():
    physical = FakeLifecycleRepository(name="physical")
    simulator = FakeLifecycleRepository(name="simulator")
    resolver = CachingPlatformResolver()
    await resolver.remember_kind("UDID-PHYS", Platform.IOS, DeviceClass.PHYSICAL)
    repo = MultiSourceIosLifecycleRepository(physical, simulator, resolver)

    await repo.launch("UDID-PHYS", "com.x")
    assert any(c[0] == "physical" and c[1] == "launch" for c in physical.calls)
    assert simulator.calls == []


@pytest.mark.asyncio
async def test_ios_observation_routes_to_simulator(tmp_path: Path):
    physical = FakeObservationRepository(name="physical")
    simulator = FakeObservationRepository(name="simulator")
    resolver = CachingPlatformResolver()
    await resolver.remember_kind("UDID-SIM", Platform.IOS, DeviceClass.SIMULATOR)
    repo = MultiSourceIosObservationRepository(physical, simulator, resolver)
    out = tmp_path / "shot.png"
    await repo.screenshot("UDID-SIM", out)
    assert out.read_bytes() == b"simulator"


# ---- top-level composite delegates to ios multi-source ----------------------


@pytest.mark.asyncio
async def test_top_composite_routes_simulator_through_ios_multi_source():
    android_devices = FakeDeviceRepository([])
    physical_ios = FakeDeviceRepository([])
    sim_ios = FakeDeviceRepository(
        [
            Device(
                "UDID-SIM",
                state=DeviceState.DEVICE,
                platform=Platform.IOS,
                device_class=DeviceClass.SIMULATOR,
            )
        ]
    )
    resolver = CachingPlatformResolver()
    ios_devices = MultiSourceIosDeviceRepository(physical_ios, sim_ios, resolver)
    top = CompositeDeviceRepository(android_devices, ios_devices, resolver)
    res = await top.list_devices()
    assert isinstance(res, Ok)
    assert res.value[0].serial == "UDID-SIM"
    kind = await resolver.kind_for("UDID-SIM")
    assert isinstance(kind, Ok)
    assert kind.value.device_class is DeviceClass.SIMULATOR
