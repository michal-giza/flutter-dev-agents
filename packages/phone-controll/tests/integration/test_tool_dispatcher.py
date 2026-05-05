"""End-to-end dispatcher tests using fake repositories all the way through."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.usecases.artifacts import GetArtifactsDir, NewSession
from mcp_phone_controll.domain.usecases.build_install import (
    BuildApp,
    InstallApp,
    UninstallApp,
)
from mcp_phone_controll.data.repositories.in_memory_device_lock_repository import (
    InMemoryDeviceLockRepository,
)
from mcp_phone_controll.domain.usecases.devices import (
    ForceReleaseLock,
    GetSelectedDevice,
    ListDevices,
    ListLocks,
    ReleaseDevice,
    SelectDevice,
)
from mcp_phone_controll.domain.usecases.lifecycle import (
    ClearAppData,
    GrantPermission,
    LaunchApp,
    StopApp,
)
from mcp_phone_controll.domain.usecases.observation import (
    ReadLogs,
    StartRecording,
    StopRecording,
    TailLogs,
    TakeScreenshot,
)
from mcp_phone_controll.domain.usecases.discovery import (
    DescribeCapabilities,
    SessionSummary,
)
from mcp_phone_controll.domain.usecases.doctor import CheckEnvironment
from mcp_phone_controll.domain.usecases.patrol import (
    ListPatrolTests,
    RunPatrolSuite,
    RunPatrolTest,
)
from mcp_phone_controll.domain.usecases.plan import RunTestPlan, ValidateTestPlan
from mcp_phone_controll.domain.usecases.preparation import PrepareForTest
from mcp_phone_controll.domain.usecases.projects import InspectProject
from mcp_phone_controll.domain.usecases.vision import (
    CompareScreenshot,
    DetectMarkers,
    InferCameraPose,
    WaitForMarker,
)
from mcp_phone_controll.domain.usecases.virtual_devices import (
    BootSimulator,
    ListAvds,
    ListSimulators,
    StartEmulator,
    StopVirtualDevice,
)
from mcp_phone_controll.domain.usecases.testing import (
    RunIntegrationTests,
    RunUnitTests,
)
from mcp_phone_controll.domain.usecases.ui_input import (
    PressKey,
    Swipe,
    Tap,
    TapText,
    TypeText,
)
from mcp_phone_controll.domain.usecases.ui_query import (
    AssertVisible,
    DumpUi,
    FindElement,
    WaitForElement,
)
from mcp_phone_controll.presentation.tool_registry import (
    ToolDispatcher,
    UseCases,
    build_registry,
)
from tests.fakes.fake_vision import FakeVisionRepository
from tests.fakes.fake_repositories import (
    FakeArtifactRepository,
    FakeVirtualDeviceManager,
    FakeBuildRepository,
    FakeCapabilitiesProvider,
    FakeDeviceRepository,
    FakeEnvironmentRepository,
    FakeLifecycleRepository,
    FakeObservationRepository,
    FakePatrolRepository,
    FakePlanExecutor,
    FakePlanLoader,
    FakeProjectInspector,
    FakeSessionStateRepository,
    FakeSessionTraceRepository,
    FakeTestRepository,
    FakeUiRepository,
)


def _build_fake_dispatcher(tmp_path: Path) -> ToolDispatcher:
    devices = FakeDeviceRepository()
    lifecycle = FakeLifecycleRepository()
    builds = FakeBuildRepository(bundle_path=tmp_path / "fake.apk")
    (tmp_path / "fake.apk").write_bytes(b"X")
    ui = FakeUiRepository()
    observation = FakeObservationRepository()
    tests = FakeTestRepository()
    artifacts = FakeArtifactRepository(root=tmp_path / "sessions")
    state = FakeSessionStateRepository()

    patrol = FakePatrolRepository()
    inspector = FakeProjectInspector()
    environment = FakeEnvironmentRepository()
    capabilities = FakeCapabilitiesProvider()
    trace = FakeSessionTraceRepository()
    plan_loader = FakePlanLoader()
    plan_executor = FakePlanExecutor()

    from mcp_phone_controll.domain.usecases.preparation import PrepareForTest as _PrepFT

    locks = InMemoryDeviceLockRepository()
    session_id = "test-session-1"

    use_cases = UseCases(
        list_devices=ListDevices(devices),
        select_device=SelectDevice(devices, state, locks, session_id),
        get_selected_device=GetSelectedDevice(devices, state),
        release_device=ReleaseDevice(state, locks, session_id),
        list_locks=ListLocks(locks),
        force_release_lock=ForceReleaseLock(locks),
        check_environment=CheckEnvironment(environment),
        describe_capabilities=DescribeCapabilities(capabilities),
        session_summary=SessionSummary(trace),
        inspect_project=InspectProject(inspector),
        prepare_for_test=_PrepFT(lifecycle, ui, observation, artifacts, state),
        run_test_plan=RunTestPlan(plan_executor, plan_loader),
        validate_test_plan=ValidateTestPlan(plan_loader),
        build_app=BuildApp(builds),
        install_app=InstallApp(builds, lifecycle, devices, state),
        uninstall_app=UninstallApp(lifecycle, state),
        launch_app=LaunchApp(lifecycle, state),
        stop_app=StopApp(lifecycle, state),
        clear_app_data=ClearAppData(lifecycle, state),
        grant_permission=GrantPermission(lifecycle, state),
        tap=Tap(ui, state),
        tap_text=TapText(ui, state),
        swipe=Swipe(ui, state),
        type_text=TypeText(ui, state),
        press_key=PressKey(ui, state),
        find_element=FindElement(ui, state),
        wait_for_element=WaitForElement(ui, state),
        dump_ui=DumpUi(ui, state),
        assert_visible=AssertVisible(ui, state),
        take_screenshot=TakeScreenshot(observation, artifacts, state),
        start_recording=StartRecording(observation, artifacts, state),
        stop_recording=StopRecording(observation, artifacts, state),
        read_logs=ReadLogs(observation, state),
        tail_logs=TailLogs(observation, state),
        run_unit_tests=RunUnitTests(tests),
        run_integration_tests=RunIntegrationTests(tests, state),
        list_patrol_tests=ListPatrolTests(patrol),
        run_patrol_test=RunPatrolTest(patrol, state),
        run_patrol_suite=RunPatrolSuite(patrol, state),
        compare_screenshot=CompareScreenshot(FakeVisionRepository()),
        detect_markers=DetectMarkers(FakeVisionRepository()),
        infer_camera_pose=InferCameraPose(FakeVisionRepository()),
        wait_for_marker=WaitForMarker(
            FakeVisionRepository(), observation, artifacts, state
        ),
        list_avds=ListAvds(FakeVirtualDeviceManager()),
        start_emulator=StartEmulator(FakeVirtualDeviceManager()),
        stop_virtual_device=StopVirtualDevice(FakeVirtualDeviceManager()),
        list_simulators=ListSimulators(FakeVirtualDeviceManager()),
        boot_simulator=BootSimulator(FakeVirtualDeviceManager()),
        # dev-session
        start_debug_session=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["StartDebugSession"]
        ).StartDebugSession(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository(),
            state,
        ),
        stop_debug_session=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["StopDebugSession"]
        ).StopDebugSession(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        restart_debug_session=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["RestartDebugSession"]
        ).RestartDebugSession(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        list_debug_sessions=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["ListDebugSessions"]
        ).ListDebugSessions(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        attach_debug_session=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["AttachDebugSession"]
        ).AttachDebugSession(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        read_debug_log=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["ReadDebugLog"]
        ).ReadDebugLog(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        tail_debug_log=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["TailDebugLog"]
        ).TailDebugLog(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        call_service_extension=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["CallServiceExtension"]
        ).CallServiceExtension(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        dump_widget_tree=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["DumpWidgetTree"]
        ).DumpWidgetTree(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        dump_render_tree=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["DumpRenderTree"]
        ).DumpRenderTree(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        toggle_inspector=__import__(
            "mcp_phone_controll.domain.usecases.dev_session", fromlist=["ToggleInspector"]
        ).ToggleInspector(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeDebugSessionRepository"]).FakeDebugSessionRepository()
        ),
        # IDE
        open_project_in_ide=__import__(
            "mcp_phone_controll.domain.usecases.ide", fromlist=["OpenProjectInIde"]
        ).OpenProjectInIde(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeIdeRepository"]).FakeIdeRepository()
        ),
        list_ide_windows=__import__(
            "mcp_phone_controll.domain.usecases.ide", fromlist=["ListIdeWindows"]
        ).ListIdeWindows(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeIdeRepository"]).FakeIdeRepository()
        ),
        close_ide_window=__import__(
            "mcp_phone_controll.domain.usecases.ide", fromlist=["CloseIdeWindow"]
        ).CloseIdeWindow(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeIdeRepository"]).FakeIdeRepository()
        ),
        focus_ide_window=__import__(
            "mcp_phone_controll.domain.usecases.ide", fromlist=["FocusIdeWindow"]
        ).FocusIdeWindow(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeIdeRepository"]).FakeIdeRepository()
        ),
        is_ide_available=__import__(
            "mcp_phone_controll.domain.usecases.ide", fromlist=["IsIdeAvailable"]
        ).IsIdeAvailable(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeIdeRepository"]).FakeIdeRepository()
        ),
        # WDA setup
        setup_webdriveragent=__import__(
            "mcp_phone_controll.domain.usecases.wda_setup", fromlist=["SetupWebDriverAgent"]
        ).SetupWebDriverAgent(
            __import__("tests.fakes.fake_dev_session", fromlist=["FakeWdaSetupCli"]).FakeWdaSetupCli()
        ),
        new_session=NewSession(artifacts),
        get_artifacts_dir=GetArtifactsDir(artifacts),
    )
    return ToolDispatcher(build_registry(use_cases))


@pytest.mark.asyncio
async def test_full_smoke_loop(tmp_path: Path):
    dispatcher = _build_fake_dispatcher(tmp_path)

    # 1. list_devices
    res = await dispatcher.dispatch("list_devices", {})
    assert res["ok"] is True
    assert res["data"][0]["serial"] == "EMU01"

    # 2. select_device
    res = await dispatcher.dispatch("select_device", {"serial": "EMU01"})
    assert res["ok"] is True

    # 3. install via project_path (uses fake build)
    res = await dispatcher.dispatch(
        "install_app", {"project_path": str(tmp_path), "mode": "debug"}
    )
    assert res["ok"] is True
    assert res["data"]["mode"] == "debug"

    # 4. launch
    res = await dispatcher.dispatch("launch_app", {"package_id": "com.example"})
    assert res["ok"] is True

    # 5. tap_text
    res = await dispatcher.dispatch("tap_text", {"text": "Sign in"})
    assert res["ok"] is True

    # 6. screenshot
    res = await dispatcher.dispatch("take_screenshot", {"label": "after-sign-in"})
    assert res["ok"] is True
    assert Path(res["data"]).exists()

    # 7. read_logs
    res = await dispatcher.dispatch("read_logs", {"since_s": 5})
    assert res["ok"] is True
    assert isinstance(res["data"], list)

    # 8. run_integration_tests
    res = await dispatcher.dispatch(
        "run_integration_tests", {"project_path": str(tmp_path)}
    )
    assert res["ok"] is True
    assert res["data"]["passed"] == 1


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(tmp_path: Path):
    dispatcher = _build_fake_dispatcher(tmp_path)
    res = await dispatcher.dispatch("nonexistent", {})
    assert res["ok"] is False
    assert res["error"]["code"] == "UnknownTool"


@pytest.mark.asyncio
async def test_missing_required_arg_returns_invalid_argument(tmp_path: Path):
    dispatcher = _build_fake_dispatcher(tmp_path)
    res = await dispatcher.dispatch("select_device", {})
    assert res["ok"] is False
    assert res["error"]["code"] == "InvalidArgumentFailure"


@pytest.mark.asyncio
async def test_no_device_selected_failure_propagates(tmp_path: Path):
    dispatcher = _build_fake_dispatcher(tmp_path)
    res = await dispatcher.dispatch("launch_app", {"package_id": "com.x"})
    assert res["ok"] is False
    assert res["error"]["code"] == "NoDeviceSelectedFailure"


@pytest.mark.asyncio
async def test_registry_covers_all_use_case_fields(tmp_path: Path):
    dispatcher = _build_fake_dispatcher(tmp_path)
    names = {d.name for d in dispatcher.descriptors}
    expected = {
        "check_environment",
        "describe_capabilities",
        "session_summary",
        "inspect_project",
        "prepare_for_test",
        "run_test_plan",
        "validate_test_plan",
        "list_devices",
        "select_device",
        "get_selected_device",
        "release_device",
        "list_locks",
        "force_release_lock",
        "build_app",
        "install_app",
        "uninstall_app",
        "launch_app",
        "stop_app",
        "clear_app_data",
        "grant_permission",
        "tap",
        "tap_text",
        "swipe",
        "type_text",
        "press_key",
        "find_element",
        "wait_for_element",
        "dump_ui",
        "assert_visible",
        "take_screenshot",
        "start_recording",
        "stop_recording",
        "read_logs",
        "tail_logs",
        "run_unit_tests",
        "run_integration_tests",
        "list_patrol_tests",
        "run_patrol_test",
        "run_patrol_suite",
        "compare_screenshot",
        "detect_markers",
        "infer_camera_pose",
        "wait_for_marker",
        "list_avds",
        "start_emulator",
        "stop_virtual_device",
        "list_simulators",
        "boot_simulator",
        "start_debug_session",
        "stop_debug_session",
        "restart_debug_session",
        "list_debug_sessions",
        "attach_debug_session",
        "read_debug_log",
        "tail_debug_log",
        "call_service_extension",
        "dump_widget_tree",
        "dump_render_tree",
        "toggle_inspector",
        "open_project_in_ide",
        "list_ide_windows",
        "close_ide_window",
        "focus_ide_window",
        "is_ide_available",
        "setup_webdriveragent",
        "new_session",
        "get_artifacts_dir",
    }
    assert names == expected
