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
from .domain.usecases.artifacts import FetchArtifact, GetArtifactsDir, NewSession
from .domain.usecases.patch_safe import PatchApplySafe
from .domain.usecases.narrate import Narrate
from .domain.usecases.productivity import (
    FindFlutterWidget,
    GrepLogs,
    RunQuickCheck,
    ScaffoldFeature,
    SummarizeSession,
)
from .domain.usecases.recall import IndexProject, Recall
from .domain.usecases.crag import CorrectiveRecall
from .domain.usecases.release_screenshot import CaptureReleaseScreenshot
from .domain.usecases.skill_library import (
    ListSkills,
    PromoteSequence,
    ReplaySkill,
)
from .domain.usecases.build_install import BuildApp, InstallApp, UninstallApp
from .domain.usecases.devices import (
    ForceReleaseLock,
    GetSelectedDevice,
    ListDevices,
    ListLocks,
    ReleaseDevice,
    SelectDevice,
)
from .domain.usecases.discovery import (
    DescribeCapabilities,
    DescribeTool,
    SessionSummary,
    ToolUsageReportUseCase,
)
from .domain.usecases.mcp_ping import McpPing
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
from .domain.usecases.ui_verify import AssertNoErrorsSince, TapAndVerify
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
    WriteVscodeLaunchConfig,
)
from .domain.usecases.wda_setup import SetupWebDriverAgent
from .domain.usecases.code_quality import (
    DartAnalyze,
    DartFix,
    DartFormat,
    FlutterPubGet,
    FlutterPubOutdated,
    QualityGate,
)
from .domain.usecases.vision_advanced import (
    AssertPoseStable,
    CalibrateCamera,
    SaveGoldenImage,
    WaitForArSessionReady,
)
from .domain.usecases.debug_inspect import VmEvaluate, VmListIsolates
from .data.repositories.dart_code_quality_repository import (
    DartCodeQualityRepository,
)
from .infrastructure.dart_cli import DartCli, FlutterPubCli
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


def _build_chunker():
    from .data.chunker import LanguageAwareChunker

    return LanguageAwareChunker()


def _make_gate_runner(gate: "QualityGate"):
    """Adapter: PatchApplySafe expects `(project_path) -> Awaitable[Result[dict]]`.

    QualityGate returns a dataclass; we map it into a small dict the patch
    use case can read.
    """
    from .domain.usecases.code_quality import QualityGateParams
    from .domain.result import ok as _ok, Err as _Err

    async def _run(project_path):
        res = await gate.execute(QualityGateParams(project_path=project_path))
        if isinstance(res, _Err):
            return res
        report = res.value
        return _ok(
            {
                "ok": getattr(report, "overall_ok", True),
                "summary": (
                    f"errors={getattr(report, 'analyzer_errors', '?')} "
                    f"warnings={getattr(report, 'analyzer_warnings', '?')} "
                    f"tests_passed={getattr(report, 'tests_passed', '?')} "
                    f"tests_failed={getattr(report, 'tests_failed', '?')}"
                ),
            }
        )

    return _run


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
    dart_cli = DartCli(runner)
    flutter_pub_cli = FlutterPubCli(runner)

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
    artifacts_root = artifacts_root or Path.home() / ".mcp_phone_controll" / "sessions"
    artifacts_repo = FilesystemArtifactRepository(artifacts_root)
    state_repo = InMemorySessionStateRepository()
    env_repo = SystemEnvironmentRepository(adb, flutter, pmd3, patrol, ide_cli)
    capabilities = StaticCapabilitiesProvider()
    # Persistent trace if MCP_TRACE_DB is set (path to a sqlite file); else
    # in-memory ring. Persistence survives MCP-process restarts and can feed
    # post-mortem analysis through tool_usage_report.
    _trace_db = os.environ.get("MCP_TRACE_DB")
    if _trace_db:
        from .data.repositories.sqlite_session_trace_repository import (
            SqliteSessionTraceRepository,
        )

        trace_repo = SqliteSessionTraceRepository(
            db_path=Path(_trace_db).expanduser(), session_id=session_id
        )
    else:
        trace_repo = InMemorySessionTraceRepository()
    plan_loader = YamlPlanLoader()
    vision_repo = OpenCvVisionRepository()

    # RAG: optional. Use Qdrant if `[rag]` extras importable; else a Null
    # repo that returns informative `next_action: "install_rag_extra"`.
    from .data.repositories.qdrant_rag_repository import (
        QdrantRagRepository,
        rag_extras_available,
    )
    from .data.repositories.null_rag_repository import NullRagRepository

    rag_repo = (
        QdrantRagRepository()
        if rag_extras_available()
        else NullRagRepository()
    )

    # Skill library — SQLite-persistent. Path defaults to artifacts root;
    # MCP_SKILL_LIBRARY_DB lets the user override (e.g. share across machines).
    from .data.repositories.sqlite_skill_library_repository import (
        SqliteSkillLibraryRepository,
    )

    _skill_db = os.environ.get("MCP_SKILL_LIBRARY_DB")
    skill_library_repo = SqliteSkillLibraryRepository(
        Path(_skill_db).expanduser()
        if _skill_db
        else (artifacts_root / "skill-library.db")
    )
    virtual_devices = CompositeVirtualDeviceManager(emulator_cli, simctl, adb)

    # Lock repo first; dev-session repo depends on it.
    lock_repo = FilesystemDeviceLockRepository(root=lock_root)
    debug_repo = FlutterDebugSessionRepository(flutter, lock_repo, session_id)
    ide_repo = VsCodeIdeRepository(ide_cli)
    quality_repo = DartCodeQualityRepository(dart_cli, flutter_pub_cli)
    atexit.register(_release_session_locks_atexit, lock_repo, session_id)
    atexit.register(_stop_debug_sessions_atexit, debug_repo)

    # Dispatcher needed by plan executor — created without it first, then re-built.
    placeholder_dispatcher: ToolDispatcher | None = None

    async def _dispatch(name: str, args):
        assert placeholder_dispatcher is not None
        return await placeholder_dispatcher.dispatch(name, args)

    try:
        _reflexion_retries = int(os.environ.get("MCP_REFLEXION_RETRIES", "0"))
    except ValueError:
        _reflexion_retries = 0
    plan_executor = YamlPlanExecutor(
        _dispatch, reflexion_retries=_reflexion_retries
    )

    # Late-binding lookups so DescribeCapabilities/DescribeTool see the
    # dispatcher's full registry (which doesn't exist yet at this point).
    def _all_tool_names():
        assert placeholder_dispatcher is not None
        return [d.name for d in placeholder_dispatcher.descriptors]

    def _all_tool_names_count() -> int:
        assert placeholder_dispatcher is not None
        return len(placeholder_dispatcher.descriptors)

    def _descriptor_lookup(name: str):
        assert placeholder_dispatcher is not None
        for d in placeholder_dispatcher.descriptors:
            if d.name == name:
                return {
                    "name": d.name,
                    "description": d.description,
                    "input_schema": d.input_schema,
                }
        return None

    use_cases = UseCases(
        list_devices=ListDevices(devices_repo),
        select_device=SelectDevice(devices_repo, state_repo, lock_repo, session_id),
        get_selected_device=GetSelectedDevice(devices_repo, state_repo),
        release_device=ReleaseDevice(state_repo, lock_repo, session_id),
        list_locks=ListLocks(lock_repo),
        force_release_lock=ForceReleaseLock(lock_repo),
        check_environment=CheckEnvironment(env_repo),
        describe_capabilities=DescribeCapabilities(capabilities, _all_tool_names),
        describe_tool=DescribeTool(_descriptor_lookup, traces=trace_repo),
        session_summary=SessionSummary(trace_repo),
        tool_usage_report=ToolUsageReportUseCase(trace_repo, _all_tool_names),
        mcp_ping=McpPing(_all_tool_names_count),
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
        tap_and_verify=TapAndVerify(ui_repo, state_repo),
        assert_no_errors_since=AssertNoErrorsSince(observation_repo, state_repo),
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
        write_vscode_launch_config=WriteVscodeLaunchConfig(),
        # WDA setup
        setup_webdriveragent=SetupWebDriverAgent(wda_setup_cli),
        # Code quality
        dart_analyze=DartAnalyze(quality_repo),
        dart_format=DartFormat(quality_repo),
        dart_fix=DartFix(quality_repo),
        flutter_pub_get=FlutterPubGet(quality_repo),
        flutter_pub_outdated=FlutterPubOutdated(quality_repo),
        quality_gate=QualityGate(quality_repo, test_repo),
        patch_apply_safe=PatchApplySafe(
            gate_runner=_make_gate_runner(QualityGate(quality_repo, test_repo))
        ),
        narrate=Narrate(),
        scaffold_feature=ScaffoldFeature(),
        run_quick_check=RunQuickCheck(quality_repo),
        grep_logs=GrepLogs(),
        summarize_session=SummarizeSession(trace_repo),
        find_flutter_widget=FindFlutterWidget(),
        # RAG retrieval (Tier G — optional, gated by [rag] extras)
        recall=Recall(rag_repo),
        recall_corrective=CorrectiveRecall(Recall(rag_repo)),
        index_project=IndexProject(rag_repo, _build_chunker()),
        capture_release_screenshot=CaptureReleaseScreenshot(
            observation_repo, artifacts_repo, state_repo
        ),
        promote_sequence=PromoteSequence(trace_repo, skill_library_repo),
        list_skills=ListSkills(skill_library_repo),
        replay_skill=ReplaySkill(skill_library_repo, _dispatch),
        # Advanced AR / Vision
        calibrate_camera=CalibrateCamera(vision_repo),
        assert_pose_stable=AssertPoseStable(
            vision_repo, observation_repo, artifacts_repo, state_repo
        ),
        wait_for_ar_session_ready=WaitForArSessionReady(observation_repo, state_repo),
        save_golden_image=SaveGoldenImage(observation_repo, artifacts_repo, state_repo),
        # DAP-lite
        vm_list_isolates=VmListIsolates(debug_repo),
        vm_evaluate=VmEvaluate(debug_repo),
        new_session=NewSession(artifacts_repo),
        get_artifacts_dir=GetArtifactsDir(artifacts_repo),
        fetch_artifact=FetchArtifact(),
    )

    descriptors = build_registry(use_cases)
    # Auto-narrate every Nth call when MCP_AUTO_NARRATE_EVERY is set.
    # Recommended: 5 for 4B agents (Reflexion-style periodic self-summary),
    # 0 (off) for Claude.
    try:
        _auto_narrate = int(os.environ.get("MCP_AUTO_NARRATE_EVERY", "0"))
    except ValueError:
        _auto_narrate = 0
    dispatcher = ToolDispatcher(
        descriptors, trace_repo=trace_repo, auto_narrate_every=_auto_narrate
    )
    placeholder_dispatcher = dispatcher  # closes over the late-bound reference

    # Boot-time self-check — one line to stderr so anyone tailing the
    # MCP subprocess logs sees the running version, the git SHA, and
    # which image-cap backends are available. Closes the diagnostic gap
    # that caused the recurring stale-subprocess pain.
    if os.environ.get("MCP_QUIET") != "1":
        import sys
        from .version_info import boot_self_check_log

        print(boot_self_check_log(), file=sys.stderr)

    return use_cases, dispatcher


def build_use_cases(artifacts_root: Path | None = None) -> UseCases:
    use_cases, _ = build_runtime(artifacts_root)
    return use_cases


def build_descriptors(artifacts_root: Path | None = None):
    _, dispatcher = build_runtime(artifacts_root)
    return dispatcher.descriptors
