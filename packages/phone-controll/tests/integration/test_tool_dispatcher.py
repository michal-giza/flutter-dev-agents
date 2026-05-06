"""End-to-end dispatcher tests using fake repositories all the way through."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.usecases.artifacts import (
    FetchArtifact,
    GetArtifactsDir,
    NewSession,
)
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
    DescribeTool,
    SessionSummary,
    ToolUsageReportUseCase,
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
from mcp_phone_controll.domain.usecases.dev_session import (
    AttachDebugSession,
    CallServiceExtension,
    DumpRenderTree,
    DumpWidgetTree,
    ListDebugSessions,
    ReadDebugLog,
    RestartDebugSession,
    StartDebugSession,
    StopDebugSession,
    TailDebugLog,
    ToggleInspector,
)
from mcp_phone_controll.domain.usecases.ide import (
    CloseIdeWindow,
    FocusIdeWindow,
    IsIdeAvailable,
    ListIdeWindows,
    OpenProjectInIde,
    WriteVscodeLaunchConfig,
)
from mcp_phone_controll.domain.usecases.wda_setup import SetupWebDriverAgent
from mcp_phone_controll.domain.usecases.patch_safe import PatchApplySafe
from mcp_phone_controll.domain.usecases.narrate import Narrate
from mcp_phone_controll.domain.usecases.productivity import (
    FindFlutterWidget,
    GrepLogs,
    RunQuickCheck,
    ScaffoldFeature,
    SummarizeSession,
)
from mcp_phone_controll.domain.usecases.code_quality import (
    DartAnalyze,
    DartFix,
    DartFormat,
    FlutterPubGet,
    FlutterPubOutdated,
    QualityGate,
)
from mcp_phone_controll.domain.usecases.vision_advanced import (
    AssertPoseStable,
    CalibrateCamera,
    SaveGoldenImage,
    WaitForArSessionReady,
)
from mcp_phone_controll.domain.usecases.debug_inspect import VmEvaluate, VmListIsolates
from tests.fakes.fake_dev_session import (
    FakeCodeQualityRepository,
    FakeDebugSessionRepository,
    FakeIdeRepository,
    FakeWdaSetupCli,
)
from mcp_phone_controll.domain.usecases.ui_query import (
    AssertVisible,
    DumpUi,
    FindElement,
    WaitForElement,
)
from mcp_phone_controll.domain.usecases.ui_verify import (
    AssertNoErrorsSince,
    TapAndVerify,
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

    debug_repo = FakeDebugSessionRepository()
    ide_repo = FakeIdeRepository()

    use_cases = UseCases(
        list_devices=ListDevices(devices),
        select_device=SelectDevice(devices, state, locks, session_id),
        get_selected_device=GetSelectedDevice(devices, state),
        release_device=ReleaseDevice(state, locks, session_id),
        list_locks=ListLocks(locks),
        force_release_lock=ForceReleaseLock(locks),
        check_environment=CheckEnvironment(environment),
        describe_capabilities=DescribeCapabilities(capabilities),
        describe_tool=DescribeTool(lambda name: None),
        session_summary=SessionSummary(trace),
        tool_usage_report=ToolUsageReportUseCase(trace, lambda: ()),
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
        tap_and_verify=TapAndVerify(ui, state),
        assert_no_errors_since=AssertNoErrorsSince(observation, state),
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
        # dev-session — shared fakes so list_debug_sessions reflects state
        # from the same instance start_debug_session populated.
        start_debug_session=StartDebugSession(debug_repo, state),
        stop_debug_session=StopDebugSession(debug_repo),
        restart_debug_session=RestartDebugSession(debug_repo),
        list_debug_sessions=ListDebugSessions(debug_repo),
        attach_debug_session=AttachDebugSession(debug_repo),
        read_debug_log=ReadDebugLog(debug_repo),
        tail_debug_log=TailDebugLog(debug_repo),
        call_service_extension=CallServiceExtension(debug_repo),
        dump_widget_tree=DumpWidgetTree(debug_repo),
        dump_render_tree=DumpRenderTree(debug_repo),
        toggle_inspector=ToggleInspector(debug_repo),
        # IDE — same instance shared so close finds what open created
        open_project_in_ide=OpenProjectInIde(ide_repo),
        list_ide_windows=ListIdeWindows(ide_repo),
        close_ide_window=CloseIdeWindow(ide_repo),
        focus_ide_window=FocusIdeWindow(ide_repo),
        is_ide_available=IsIdeAvailable(ide_repo),
        write_vscode_launch_config=WriteVscodeLaunchConfig(),
        # WDA setup
        setup_webdriveragent=SetupWebDriverAgent(FakeWdaSetupCli()),
        # Code quality
        dart_analyze=DartAnalyze(FakeCodeQualityRepository()),
        dart_format=DartFormat(FakeCodeQualityRepository()),
        dart_fix=DartFix(FakeCodeQualityRepository()),
        flutter_pub_get=FlutterPubGet(FakeCodeQualityRepository()),
        flutter_pub_outdated=FlutterPubOutdated(FakeCodeQualityRepository()),
        quality_gate=QualityGate(FakeCodeQualityRepository(), tests),
        patch_apply_safe=PatchApplySafe(),
        narrate=Narrate(),
        scaffold_feature=ScaffoldFeature(),
        run_quick_check=RunQuickCheck(FakeCodeQualityRepository()),
        grep_logs=GrepLogs(),
        summarize_session=SummarizeSession(trace),
        find_flutter_widget=FindFlutterWidget(),
        # Advanced AR / Vision
        calibrate_camera=CalibrateCamera(FakeVisionRepository()),
        assert_pose_stable=AssertPoseStable(
            FakeVisionRepository(), observation, artifacts, state
        ),
        wait_for_ar_session_ready=WaitForArSessionReady(observation, state),
        save_golden_image=SaveGoldenImage(observation, artifacts, state),
        # DAP-lite — point at fake debug repo (no VM service connection in tests)
        vm_list_isolates=VmListIsolates(debug_repo),
        vm_evaluate=VmEvaluate(debug_repo),
        new_session=NewSession(artifacts),
        get_artifacts_dir=GetArtifactsDir(artifacts),
        fetch_artifact=FetchArtifact(),
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
async def test_dispatcher_coerces_string_bool_for_small_llms(tmp_path: Path):
    """A 4B model passes 'force=\"true\"' instead of force=True; should still work."""
    dispatcher = _build_fake_dispatcher(tmp_path)
    res = await dispatcher.dispatch(
        "select_device", {"serial": "EMU01", "force": "true"}
    )
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_missing_arg_envelope_includes_corrected_example(tmp_path: Path):
    dispatcher = _build_fake_dispatcher(tmp_path)
    res = await dispatcher.dispatch("select_device", {})
    assert res["ok"] is False
    err = res["error"]
    assert err["code"] == "InvalidArgumentFailure"
    assert err["next_action"] == "fix_arguments"
    assert "corrected_example" in err["details"]
    # The example must contain the missing key with a valid placeholder value
    assert "serial" in err["details"]["corrected_example"]


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
        "describe_tool",
        "session_summary",
        "tool_usage_report",
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
        "tap_and_verify",
        "assert_no_errors_since",
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
        "write_vscode_launch_config",
        "setup_webdriveragent",
        "dart_analyze",
        "dart_format",
        "dart_fix",
        "flutter_pub_get",
        "flutter_pub_outdated",
        "quality_gate",
        "patch_apply_safe",
        "narrate",
        "scaffold_feature",
        "run_quick_check",
        "grep_logs",
        "summarize_session",
        "find_flutter_widget",
        "calibrate_camera",
        "assert_pose_stable",
        "wait_for_ar_session_ready",
        "save_golden_image",
        "vm_list_isolates",
        "vm_evaluate",
        "new_session",
        "get_artifacts_dir",
        "fetch_artifact",
    }
    assert names == expected
