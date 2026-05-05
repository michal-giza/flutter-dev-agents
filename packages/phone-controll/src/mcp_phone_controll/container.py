"""Composition root. Wires every concrete repo into every use case.

Layers wired here:
  - Per-platform repos (Android, iOS)
  - Composites (platform routing, framework routing)
  - Patrol + project inspector
  - Doctor (environment) + Capabilities provider
  - Session trace recorder
  - YAML plan loader + executor
"""

from __future__ import annotations

import atexit
import os
import uuid
from pathlib import Path

from .data.repositories.adb_device_repository import AdbDeviceRepository
from .data.repositories.adb_lifecycle_repository import AdbLifecycleRepository
from .data.repositories.adb_observation_repository import AdbObservationRepository
from .data.repositories.composite.composite_repositories import (
    CompositeBuildRepository,
    CompositeDeviceRepository,
    CompositeLifecycleRepository,
    CompositeObservationRepository,
    CompositeTestRepository,
    CompositeUiRepository,
)
from .data.repositories.composite.platform_resolver import CachingPlatformResolver
from .data.repositories.composite_project_inspector import CompositeProjectInspector
from .data.repositories.filesystem_artifact_repository import FilesystemArtifactRepository
from .data.repositories.filesystem_device_lock_repository import (
    FilesystemDeviceLockRepository,
)
from .data.repositories.flutter_build_repository import FlutterBuildRepository
from .data.repositories.flutter_project_inspector import FlutterProjectInspector
from .data.repositories.flutter_test_repository import FlutterTestRepository
from .data.repositories.in_memory_session_state_repository import (
    InMemorySessionStateRepository,
)
from .data.repositories.ios_multi_source import (
    MultiSourceIosDeviceRepository,
    MultiSourceIosLifecycleRepository,
    MultiSourceIosObservationRepository,
)
from .data.repositories.opencv_vision_repository import OpenCvVisionRepository
from .data.repositories.simctl_simulator_device_repository import (
    SimctlSimulatorDeviceRepository,
)
from .data.repositories.simctl_simulator_lifecycle_repository import (
    SimctlSimulatorLifecycleRepository,
)
from .data.repositories.simctl_simulator_observation_repository import (
    SimctlSimulatorObservationRepository,
)
from .data.repositories.virtual_device_manager import CompositeVirtualDeviceManager
from .data.repositories.in_memory_session_trace_repository import (
    InMemorySessionTraceRepository,
)
from .data.repositories.ios_device_repository import IosDeviceRepository
from .data.repositories.ios_lifecycle_repository import IosLifecycleRepository
from .data.repositories.ios_observation_repository import IosObservationRepository
from .data.repositories.patrol_repository import PatrolTestRepository
from .data.repositories.static_capabilities_provider import StaticCapabilitiesProvider
from .data.repositories.system_environment_repository import SystemEnvironmentRepository
from .data.repositories.uiautomator2_ui_repository import UiAutomator2UiRepository
from .data.repositories.wda_ui_repository import WdaUiRepository
from .data.repositories.yaml_plan_executor import YamlPlanExecutor
from .domain.entities import TestFramework
from .domain.usecases.artifacts import GetArtifactsDir, NewSession
from .domain.usecases.build_install import BuildApp, InstallApp, UninstallApp
from .domain.usecases.devices import (
    ForceReleaseLock,
    GetSelectedDevice,
    ListDevices,
    ListLocks,
    ReleaseDevice,
    SelectDevice,
)
from .domain.usecases.discovery import DescribeCapabilities, SessionSummary
from .domain.usecases.doctor import CheckEnvironment
from .domain.usecases.lifecycle import (
    ClearAppData,
    GrantPermission,
    LaunchApp,
    StopApp,
)
from .domain.usecases.observation import (
    ReadLogs,
    StartRecording,
    StopRecording,
    TailLogs,
    TakeScreenshot,
)
from .domain.usecases.patrol import (
    ListPatrolTests,
    RunPatrolSuite,
    RunPatrolTest,
)
from .domain.usecases.plan import RunTestPlan, ValidateTestPlan
from .domain.usecases.preparation import PrepareForTest
from .domain.usecases.projects import InspectProject
from .domain.usecases.testing import RunIntegrationTests, RunUnitTests
from .domain.usecases.ui_input import PressKey, Swipe, Tap, TapText, TypeText
from .domain.usecases.ui_query import AssertVisible, DumpUi, FindElement, WaitForElement
from .domain.usecases.virtual_devices import (
    BootSimulator,
    ListAvds,
    ListSimulators,
    StartEmulator,
    StopVirtualDevice,
)
from .domain.usecases.vision import (
    CompareScreenshot,
    DetectMarkers,
    InferCameraPose,
    WaitForMarker,
)
from .infrastructure.android_emulator_cli import AndroidEmulatorCli
from .infrastructure.simctl_client import SimctlClient
from .infrastructure.adb_client import AdbClient
from .infrastructure.flutter_cli import FlutterCli
from .infrastructure.patrol_cli import PatrolCli
from .infrastructure.process_runner import AsyncProcessRunner
from .infrastructure.pymobiledevice3_cli import PyMobileDevice3Cli
from .infrastructure.uiautomator2_factory import CachingUiAutomator2Factory
from .infrastructure.wda_factory import CachingWdaFactory
from .infrastructure.yaml_plan_loader import YamlPlanLoader
from .infrastructure.ide_cli import IdeCli
from .infrastructure.wda_setup_cli import WdaSetupCli
from .data.repositories.flutter_debug_session_repository import (
    FlutterDebugSessionRepository,
)
from .data.repositories.vscode_ide_repository import VsCodeIdeRepository
from .domain.usecases.dev_session import (
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
from .domain.usecases.ide import (
    CloseIdeWindow,
    FocusIdeWindow,
    IsIdeAvailable,
    ListIdeWindows,
    OpenProjectInIde,
)
from .domain.usecases.wda_setup import SetupWebDriverAgent
from .presentation.tool_registry import ToolDispatcher, UseCases, build_registry


def _stop_debug_sessions_atexit(debug_repo) -> None:
    """Best-effort sync stop of every active debug session at process exit.

    Avoids leaving an orphan `flutter run --machine` daemon attached to a
    device, which would block the next session's start_debug_session.
    """
    try:
        import asyncio as _asyncio

        # Run the async stop_all on a fresh loop.
        loop = _asyncio.new_event_loop()
        try:
            loop.run_until_complete(debug_repo.stop_all())
        finally:
            loop.close()
    except Exception:  # noqa: BLE001 — atexit must never raise
        return


def _release_session_locks_atexit(lock_repo, session_id: str) -> None:
    """Best-effort sync release of any lock this session holds. Called at process
    shutdown — cannot await, so we read the lock dir directly via the repo's
    internal API. Safe even if the loop is gone."""
    try:
        # FilesystemDeviceLockRepository: directly walk the lock dir.
        root = getattr(lock_repo, "_root", None)
        if root is None:
            return
        from pathlib import Path

        if not isinstance(root, Path):
            return
        for path in root.glob("*.lock"):
            try:
                import json

                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if data.get("session_id") == session_id:
                try:
                    path.unlink()
                except OSError:
                    pass
    except Exception:  # noqa: BLE001 — atexit must never raise
        return


def build_runtime(
    artifacts_root: Path | None = None,
    session_id: str | None = None,
    lock_root: Path | None = None,
):
    """Build (UseCases, dispatcher) — exposes both so callers can plug in
    a plan-executor that needs a back-reference to the dispatcher.

    `session_id` uniquely identifies this MCP process across concurrent sessions
    (each Claude Code conversation spawns its own MCP). Generated if not given.
    """

    session_id = session_id or f"mcp-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    runner = AsyncProcessRunner()

    # Infrastructure clients
    adb = AdbClient(runner)
    flutter = FlutterCli(runner)
    patrol = PatrolCli(runner)
    pmd3 = PyMobileDevice3Cli(runner)
    simctl = SimctlClient(runner)
    emulator_cli = AndroidEmulatorCli(runner)
    u2_factory = CachingUiAutomator2Factory()
    wda_factory = CachingWdaFactory()
    ide_cli = IdeCli(runner)
    wda_setup_cli = WdaSetupCli(runner)

    # Per-platform repositories
    android_devices = AdbDeviceRepository(adb)
    android_lifecycle = AdbLifecycleRepository(adb)
    android_ui = UiAutomator2UiRepository(u2_factory)
    android_observation = AdbObservationRepository(adb)

    # Physical iOS (pymobiledevice3) + simulator iOS (xcrun simctl), merged.
    ios_physical_devices = IosDeviceRepository(pmd3)
    ios_simulator_devices = SimctlSimulatorDeviceRepository(simctl, include_shutdown=False)
    ios_physical_lifecycle = IosLifecycleRepository(pmd3)
    ios_simulator_lifecycle = SimctlSimulatorLifecycleRepository(simctl)
    ios_physical_observation = IosObservationRepository(pmd3)
    ios_simulator_observation = SimctlSimulatorObservationRepository(simctl)
    ios_ui = WdaUiRepository(wda_factory)

    # Build & test (cross-platform Flutter)
    flutter_build = FlutterBuildRepository(flutter)
    flutter_tests = FlutterTestRepository(flutter)
    patrol_tests = PatrolTestRepository(patrol)

    # Project inspection (extension point for RN/native iOS/web)
    inspector = CompositeProjectInspector([FlutterProjectInspector()])

    # Routing
    resolver = CachingPlatformResolver()

    # iOS multi-source: physical + simulator merged behind the iOS surface.
    ios_devices = MultiSourceIosDeviceRepository(
        ios_physical_devices, ios_simulator_devices, resolver
    )
    ios_lifecycle = MultiSourceIosLifecycleRepository(
        ios_physical_lifecycle, ios_simulator_lifecycle, resolver
    )
    ios_observation = MultiSourceIosObservationRepository(
        ios_physical_observation, ios_simulator_observation, resolver
    )

    devices_repo = CompositeDeviceRepository(android_devices, ios_devices, resolver)
    lifecycle_repo = CompositeLifecycleRepository(android_lifecycle, ios_lifecycle, resolver)
    ui_repo = CompositeUiRepository(android_ui, ios_ui, resolver)
    observation_repo = CompositeObservationRepository(
        android_observation, ios_observation, resolver
    )
    build_repo = CompositeBuildRepository(flutter_build, flutter_build)
    test_repo = CompositeTestRepository(
        android=flutter_tests,
        ios=flutter_tests,
        resolver=resolver,
        framework_runners={TestFramework.PATROL: patrol_tests},
        inspector=inspector,
    )

    # Cross-cutting
    artifacts_repo = FilesystemArtifactRepository(
        artifacts_root or Path.home() / ".mcp_phone_controll" / "sessions"
    )
    state_repo = InMemorySessionStateRepository()
    env_repo = SystemEnvironmentRepository(adb, flutter, pmd3, patrol, ide_cli)
    capabilities = StaticCapabilitiesProvider()
    trace_repo = InMemorySessionTraceRepository()
    plan_loader = YamlPlanLoader()
    vision_repo = OpenCvVisionRepository()
    virtual_devices = CompositeVirtualDeviceManager(emulator_cli, simctl, adb)

    # Lock repo first; dev-session repo depends on it.
    lock_repo = FilesystemDeviceLockRepository(root=lock_root)
    debug_repo = FlutterDebugSessionRepository(flutter, lock_repo, session_id)
    ide_repo = VsCodeIdeRepository(ide_cli)
    atexit.register(_release_session_locks_atexit, lock_repo, session_id)
    atexit.register(_stop_debug_sessions_atexit, debug_repo)

    # Dispatcher needed by plan executor — created without it first, then re-built.
    placeholder_dispatcher: ToolDispatcher | None = None

    async def _dispatch(name: str, args):
        assert placeholder_dispatcher is not None
        return await placeholder_dispatcher.dispatch(name, args)

    plan_executor = YamlPlanExecutor(_dispatch)

    use_cases = UseCases(
        list_devices=ListDevices(devices_repo),
        select_device=SelectDevice(devices_repo, state_repo, lock_repo, session_id),
        get_selected_device=GetSelectedDevice(devices_repo, state_repo),
        release_device=ReleaseDevice(state_repo, lock_repo, session_id),
        list_locks=ListLocks(lock_repo),
        force_release_lock=ForceReleaseLock(lock_repo),
        check_environment=CheckEnvironment(env_repo),
        describe_capabilities=DescribeCapabilities(capabilities),
        session_summary=SessionSummary(trace_repo),
        inspect_project=InspectProject(inspector),
        prepare_for_test=PrepareForTest(
            lifecycle_repo, ui_repo, observation_repo, artifacts_repo, state_repo
        ),
        run_test_plan=RunTestPlan(plan_executor, plan_loader),
        validate_test_plan=ValidateTestPlan(plan_loader),
        build_app=BuildApp(build_repo),
        install_app=InstallApp(build_repo, lifecycle_repo, devices_repo, state_repo),
        uninstall_app=UninstallApp(lifecycle_repo, state_repo),
        launch_app=LaunchApp(lifecycle_repo, state_repo),
        stop_app=StopApp(lifecycle_repo, state_repo),
        clear_app_data=ClearAppData(lifecycle_repo, state_repo),
        grant_permission=GrantPermission(lifecycle_repo, state_repo),
        tap=Tap(ui_repo, state_repo),
        tap_text=TapText(ui_repo, state_repo),
        swipe=Swipe(ui_repo, state_repo),
        type_text=TypeText(ui_repo, state_repo),
        press_key=PressKey(ui_repo, state_repo),
        find_element=FindElement(ui_repo, state_repo),
        wait_for_element=WaitForElement(ui_repo, state_repo),
        dump_ui=DumpUi(ui_repo, state_repo),
        assert_visible=AssertVisible(ui_repo, state_repo),
        take_screenshot=TakeScreenshot(observation_repo, artifacts_repo, state_repo),
        start_recording=StartRecording(observation_repo, artifacts_repo, state_repo),
        stop_recording=StopRecording(observation_repo, artifacts_repo, state_repo),
        read_logs=ReadLogs(observation_repo, state_repo),
        tail_logs=TailLogs(observation_repo, state_repo),
        run_unit_tests=RunUnitTests(test_repo),
        run_integration_tests=RunIntegrationTests(test_repo, state_repo),
        list_patrol_tests=ListPatrolTests(patrol_tests),
        run_patrol_test=RunPatrolTest(patrol_tests, state_repo),
        run_patrol_suite=RunPatrolSuite(patrol_tests, state_repo),
        compare_screenshot=CompareScreenshot(vision_repo),
        detect_markers=DetectMarkers(vision_repo),
        infer_camera_pose=InferCameraPose(vision_repo),
        wait_for_marker=WaitForMarker(
            vision_repo, observation_repo, artifacts_repo, state_repo
        ),
        list_avds=ListAvds(virtual_devices),
        start_emulator=StartEmulator(virtual_devices),
        stop_virtual_device=StopVirtualDevice(virtual_devices),
        list_simulators=ListSimulators(virtual_devices),
        boot_simulator=BootSimulator(virtual_devices),
        # dev-session
        start_debug_session=StartDebugSession(debug_repo, state_repo),
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
        # IDE
        open_project_in_ide=OpenProjectInIde(ide_repo),
        list_ide_windows=ListIdeWindows(ide_repo),
        close_ide_window=CloseIdeWindow(ide_repo),
        focus_ide_window=FocusIdeWindow(ide_repo),
        is_ide_available=IsIdeAvailable(ide_repo),
        # WDA setup
        setup_webdriveragent=SetupWebDriverAgent(wda_setup_cli),
        new_session=NewSession(artifacts_repo),
        get_artifacts_dir=GetArtifactsDir(artifacts_repo),
    )

    descriptors = build_registry(use_cases)
    dispatcher = ToolDispatcher(descriptors, trace_repo=trace_repo)
    placeholder_dispatcher = dispatcher  # closes over the late-bound reference
    return use_cases, dispatcher


def build_use_cases(artifacts_root: Path | None = None) -> UseCases:
    use_cases, _ = build_runtime(artifacts_root)
    return use_cases


def build_descriptors(artifacts_root: Path | None = None):
    _, dispatcher = build_runtime(artifacts_root)
    return dispatcher.descriptors
