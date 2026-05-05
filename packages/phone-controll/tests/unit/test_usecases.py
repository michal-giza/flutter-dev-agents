"""Use-case tests against in-memory fakes."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.entities import BuildMode, Bounds, Platform, UiElement
from mcp_phone_controll.domain.failures import (
    DeviceNotFoundFailure,
    NoDeviceSelectedFailure,
    UiElementNotFoundFailure,
)
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.base import NoParams
from mcp_phone_controll.domain.usecases.build_install import (
    InstallApp,
    InstallAppParams,
)
from mcp_phone_controll.domain.usecases.devices import (
    GetSelectedDevice,
    ListDevices,
    SelectDevice,
    SelectDeviceParams,
)
from mcp_phone_controll.domain.usecases.lifecycle import (
    LaunchApp,
    LaunchAppParams,
)
from mcp_phone_controll.domain.usecases.ui_query import (
    AssertVisible,
    AssertVisibleParams,
)
from tests.fakes.fake_repositories import (
    FakeArtifactRepository,
    FakeBuildRepository,
    FakeDeviceRepository,
    FakeLifecycleRepository,
    FakeSessionStateRepository,
    FakeUiRepository,
)


@pytest.mark.asyncio
async def test_list_devices_returns_devices():
    uc = ListDevices(FakeDeviceRepository())
    result = await uc(NoParams())
    assert isinstance(result, Ok)
    assert result.value[0].serial == "EMU01"


@pytest.mark.asyncio
async def test_select_device_persists_selection():
    devices = FakeDeviceRepository()
    state = FakeSessionStateRepository()
    from mcp_phone_controll.data.repositories.in_memory_device_lock_repository import (
        InMemoryDeviceLockRepository,
    )
    uc = SelectDevice(devices, state, InMemoryDeviceLockRepository(), "test-session")
    result = await uc(SelectDeviceParams(serial="EMU01"))
    assert isinstance(result, Ok)
    assert state.serial == "EMU01"


@pytest.mark.asyncio
async def test_select_device_unknown_returns_err():
    from mcp_phone_controll.data.repositories.in_memory_device_lock_repository import (
        InMemoryDeviceLockRepository,
    )
    uc = SelectDevice(
        FakeDeviceRepository(),
        FakeSessionStateRepository(),
        InMemoryDeviceLockRepository(),
        "test-session",
    )
    result = await uc(SelectDeviceParams(serial="NOPE"))
    assert isinstance(result, Err)
    assert isinstance(result.failure, DeviceNotFoundFailure)


@pytest.mark.asyncio
async def test_get_selected_device_when_unselected_returns_none():
    uc = GetSelectedDevice(FakeDeviceRepository(), FakeSessionStateRepository())
    result = await uc(NoParams())
    assert isinstance(result, Ok)
    assert result.value is None


@pytest.mark.asyncio
async def test_install_uses_selected_serial(tmp_path: Path):
    apk = tmp_path / "fake.apk"
    apk.write_bytes(b"X")
    builds = FakeBuildRepository(bundle_path=apk)
    lifecycle = FakeLifecycleRepository()
    devices = FakeDeviceRepository()
    state = FakeSessionStateRepository(serial="EMU01")
    uc = InstallApp(builds, lifecycle, devices, state)

    result = await uc(InstallAppParams(bundle_path=apk))
    assert isinstance(result, Ok)
    assert any(c[1] == "install" and c[2] == "EMU01" for c in lifecycle.calls)


@pytest.mark.asyncio
async def test_install_without_selected_device_errors(tmp_path: Path):
    builds = FakeBuildRepository()
    lifecycle = FakeLifecycleRepository()
    devices = FakeDeviceRepository()
    state = FakeSessionStateRepository()
    uc = InstallApp(builds, lifecycle, devices, state)

    result = await uc(InstallAppParams(bundle_path=tmp_path / "x.apk"))
    assert isinstance(result, Err)
    assert isinstance(result.failure, NoDeviceSelectedFailure)


@pytest.mark.asyncio
async def test_install_builds_when_only_project_path_given():
    builds = FakeBuildRepository(bundle_path=Path("/tmp/built.apk"))
    lifecycle = FakeLifecycleRepository()
    devices = FakeDeviceRepository()
    state = FakeSessionStateRepository(serial="EMU01")
    uc = InstallApp(builds, lifecycle, devices, state)

    result = await uc(
        InstallAppParams(project_path=Path("/work/myapp"), mode=BuildMode.DEBUG)
    )
    assert isinstance(result, Ok)
    assert result.value.path == Path("/tmp/built.apk")
    assert result.value.platform is Platform.ANDROID


@pytest.mark.asyncio
async def test_launch_passes_activity():
    lifecycle = FakeLifecycleRepository()
    state = FakeSessionStateRepository(serial="EMU01")
    uc = LaunchApp(lifecycle, state)

    result = await uc(LaunchAppParams(package_id="com.x", activity=".Main"))
    assert isinstance(result, Ok)
    assert ("fake", "launch", "EMU01", "com.x", ".Main") in lifecycle.calls


@pytest.mark.asyncio
async def test_assert_visible_succeeds_when_found():
    elem = UiElement(
        text="Sign in",
        resource_id=None,
        class_name="android.widget.Button",
        content_description=None,
        bounds=Bounds(0, 0, 100, 50),
        enabled=True,
        clickable=True,
    )
    ui = FakeUiRepository(found=elem)
    state = FakeSessionStateRepository(serial="EMU01")
    uc = AssertVisible(ui, state)
    result = await uc(AssertVisibleParams(text="Sign in"))
    assert isinstance(result, Ok)
    assert result.value is elem


@pytest.mark.asyncio
async def test_assert_visible_errors_when_missing():
    ui = FakeUiRepository(found=None)
    state = FakeSessionStateRepository(serial="EMU01")
    uc = AssertVisible(ui, state)
    result = await uc(AssertVisibleParams(text="Nope"))
    assert isinstance(result, Err)
    assert isinstance(result.failure, UiElementNotFoundFailure)


@pytest.mark.asyncio
async def test_artifact_session_returned_by_fake(tmp_path: Path):
    artifacts = FakeArtifactRepository(root=tmp_path)
    res = await artifacts.new_session("smoke")
    assert isinstance(res, Ok)
    assert res.value.label == "smoke"
    assert res.value.root.exists()
