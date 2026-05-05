"""Declarative MCP tool registry. Maps tool name → (schema, params builder, use case).

Adding a new tool means adding one ToolDescriptor — the dispatcher and MCP server are generic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..domain.entities import BuildMode, LogLevel, Platform
from ..domain.result import Err, Result
from ..domain.usecases.artifacts import GetArtifactsDir, NewSession, NewSessionParams
from ..domain.usecases.base import NoParams
from ..domain.usecases.build_install import (
    BuildApp,
    BuildAppParams,
    InstallApp,
    InstallAppParams,
    UninstallApp,
    UninstallAppParams,
)
from ..domain.usecases.devices import (
    ForceReleaseLock,
    ForceReleaseLockParams,
    GetSelectedDevice,
    ListDevices,
    ListLocks,
    ReleaseDevice,
    ReleaseDeviceParams,
    SelectDevice,
    SelectDeviceParams,
)
from ..domain.usecases.lifecycle import (
    ClearAppData,
    ClearAppDataParams,
    GrantPermission,
    GrantPermissionParams,
    LaunchApp,
    LaunchAppParams,
    StopApp,
    StopAppParams,
)
from ..domain.usecases.observation import (
    ReadLogs,
    ReadLogsParams,
    StartRecording,
    StartRecordingParams,
    StopRecording,
    StopRecordingParams,
    TailLogs,
    TailLogsParams,
    TakeScreenshot,
    TakeScreenshotParams,
)
from ..domain.usecases.discovery import (
    DescribeCapabilities,
    SessionSummary,
    SessionSummaryParams,
)
from ..domain.usecases.doctor import CheckEnvironment
from ..domain.usecases.patrol import (
    ListPatrolTests,
    ListPatrolTestsParams,
    RunPatrolSuite,
    RunPatrolSuiteParams,
    RunPatrolTest,
    RunPatrolTestParams,
)
from ..domain.usecases.plan import (
    RunTestPlan,
    RunTestPlanParams,
    ValidateTestPlan,
    ValidateTestPlanParams,
)
from ..domain.usecases.preparation import PrepareForTest, PrepareForTestParams
from ..domain.usecases.projects import InspectProject, InspectProjectParams
from ..domain.usecases.testing import (
    RunIntegrationTests,
    RunIntegrationTestsParams,
    RunUnitTests,
    RunUnitTestsParams,
)
from ..domain.usecases.ui_input import (
    PressKey,
    PressKeyParams,
    Swipe,
    SwipeParams,
    Tap,
    TapParams,
    TapText,
    TapTextParams,
    TypeText,
    TypeTextParams,
)
from ..domain.usecases.vision import (
    CompareScreenshot,
    CompareScreenshotParams,
    DetectMarkers,
    DetectMarkersParams,
    InferCameraPose,
    InferCameraPoseParams,
    WaitForMarker,
    WaitForMarkerParams,
)
from ..domain.usecases.virtual_devices import (
    BootSimulator,
    BootSimulatorParams,
    ListAvds,
    ListSimulators,
    ListSimulatorsParams,
    StartEmulator,
    StartEmulatorParams,
    StopVirtualDevice,
    StopVirtualDeviceParams,
)
from ..domain.usecases.dev_session import (
    AttachDebugSession,
    AttachDebugSessionParams,
    CallServiceExtension,
    CallServiceExtensionParams,
    DumpRenderTree,
    DumpWidgetTree,
    DumpWidgetTreeParams,
    ListDebugSessions,
    ReadDebugLog,
    ReadDebugLogParams,
    RestartDebugSession,
    RestartDebugSessionParams,
    StartDebugSession,
    StartDebugSessionParams,
    StopDebugSession,
    StopDebugSessionParams,
    TailDebugLog,
    TailDebugLogParams,
    ToggleInspector,
    ToggleInspectorParams,
)
from ..domain.usecases.ide import (
    CloseIdeWindow,
    CloseIdeWindowParams,
    FocusIdeWindow,
    FocusIdeWindowParams,
    IsIdeAvailable,
    IsIdeAvailableParams,
    ListIdeWindows,
    OpenProjectInIde,
    OpenProjectInIdeParams,
)
from ..domain.usecases.wda_setup import (
    SetupWebDriverAgent,
    SetupWebDriverAgentParams,
)
from ..domain.entities import IdeKind as _IdeKind
from ..domain.usecases.ui_query import (
    AssertVisible,
    AssertVisibleParams,
    DumpUi,
    DumpUiParams,
    FindElement,
    FindElementParams,
    WaitForElement,
    WaitForElementParams,
)
from .serialization import to_jsonable

JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    description: str
    input_schema: JsonDict
    build_params: Callable[[JsonDict], Any]
    invoke: Callable[[JsonDict], Awaitable[Result[Any]]]


def _string(desc: str = "") -> JsonDict:
    return {"type": "string", "description": desc}


def _int(desc: str = "") -> JsonDict:
    return {"type": "integer", "description": desc}


def _number(desc: str = "") -> JsonDict:
    return {"type": "number", "description": desc}


def _bool(desc: str = "") -> JsonDict:
    return {"type": "boolean", "description": desc}


def _enum(values: list[str], desc: str = "") -> JsonDict:
    return {"type": "string", "enum": values, "description": desc}


def _schema(properties: JsonDict, required: list[str] | None = None) -> JsonDict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


# Per-tool param builders: dict (from MCP arguments) → typed Params dataclass.
# Keep these dumb — validation lives at the schema layer.


def _params_no(_: JsonDict) -> NoParams:
    return NoParams()


def _params_select_device(args: JsonDict) -> SelectDeviceParams:
    return SelectDeviceParams(
        serial=args["serial"],
        force=bool(args.get("force", False)),
        note=args.get("note"),
    )


def _params_release_device(args: JsonDict) -> ReleaseDeviceParams:
    return ReleaseDeviceParams(serial=args.get("serial"))


def _params_force_release_lock(args: JsonDict) -> ForceReleaseLockParams:
    return ForceReleaseLockParams(serial=args["serial"])


def _params_build_app(args: JsonDict) -> BuildAppParams:
    return BuildAppParams(
        project_path=Path(args["project_path"]).expanduser(),
        mode=BuildMode(args.get("mode", "debug")),
        platform=Platform(args.get("platform", "android")),
        flavor=args.get("flavor"),
    )


def _params_install_app(args: JsonDict) -> InstallAppParams:
    raw_platform = args.get("platform")
    return InstallAppParams(
        bundle_path=_path(args.get("bundle_path") or args.get("apk_path")),
        project_path=_path(args.get("project_path")),
        mode=BuildMode(args.get("mode", "debug")),
        platform=Platform(raw_platform) if raw_platform else None,
        flavor=args.get("flavor"),
        serial=args.get("serial"),
    )


def _params_uninstall(args: JsonDict) -> UninstallAppParams:
    return UninstallAppParams(package_id=args["package_id"], serial=args.get("serial"))


def _params_launch(args: JsonDict) -> LaunchAppParams:
    return LaunchAppParams(
        package_id=args["package_id"],
        activity=args.get("activity"),
        serial=args.get("serial"),
    )


def _params_stop(args: JsonDict) -> StopAppParams:
    return StopAppParams(package_id=args["package_id"], serial=args.get("serial"))


def _params_clear(args: JsonDict) -> ClearAppDataParams:
    return ClearAppDataParams(package_id=args["package_id"], serial=args.get("serial"))


def _params_grant(args: JsonDict) -> GrantPermissionParams:
    return GrantPermissionParams(
        package_id=args["package_id"],
        permission=args["permission"],
        serial=args.get("serial"),
    )


def _params_tap(args: JsonDict) -> TapParams:
    return TapParams(x=int(args["x"]), y=int(args["y"]), serial=args.get("serial"))


def _params_tap_text(args: JsonDict) -> TapTextParams:
    return TapTextParams(
        text=args["text"], exact=bool(args.get("exact", False)), serial=args.get("serial")
    )


def _params_swipe(args: JsonDict) -> SwipeParams:
    return SwipeParams(
        x1=int(args["x1"]),
        y1=int(args["y1"]),
        x2=int(args["x2"]),
        y2=int(args["y2"]),
        duration_ms=int(args.get("duration_ms", 300)),
        serial=args.get("serial"),
    )


def _params_type_text(args: JsonDict) -> TypeTextParams:
    return TypeTextParams(text=args["text"], serial=args.get("serial"))


def _params_press_key(args: JsonDict) -> PressKeyParams:
    return PressKeyParams(keycode=args["keycode"], serial=args.get("serial"))


def _params_find(args: JsonDict) -> FindElementParams:
    return FindElementParams(
        text=args.get("text"),
        resource_id=args.get("resource_id"),
        class_name=args.get("class_name"),
        timeout_s=float(args.get("timeout_s", 5.0)),
        serial=args.get("serial"),
    )


def _params_wait_for(args: JsonDict) -> WaitForElementParams:
    return WaitForElementParams(
        text=args.get("text"),
        resource_id=args.get("resource_id"),
        timeout_s=float(args.get("timeout_s", 10.0)),
        serial=args.get("serial"),
    )


def _params_dump_ui(args: JsonDict) -> DumpUiParams:
    return DumpUiParams(serial=args.get("serial"))


def _params_assert_visible(args: JsonDict) -> AssertVisibleParams:
    return AssertVisibleParams(
        text=args.get("text"),
        resource_id=args.get("resource_id"),
        timeout_s=float(args.get("timeout_s", 5.0)),
        serial=args.get("serial"),
    )


def _params_screenshot(args: JsonDict) -> TakeScreenshotParams:
    return TakeScreenshotParams(label=args.get("label"), serial=args.get("serial"))


def _params_start_recording(args: JsonDict) -> StartRecordingParams:
    return StartRecordingParams(label=args.get("label"), serial=args.get("serial"))


def _params_stop_recording(args: JsonDict) -> StopRecordingParams:
    return StopRecordingParams(serial=args.get("serial"))


def _params_read_logs(args: JsonDict) -> ReadLogsParams:
    return ReadLogsParams(
        since_s=int(args.get("since_s", 30)),
        tag=args.get("tag"),
        min_level=LogLevel(args.get("min_level", "W")),
        max_lines=int(args.get("max_lines", 500)),
        serial=args.get("serial"),
    )


def _params_tail_logs(args: JsonDict) -> TailLogsParams:
    return TailLogsParams(
        until_pattern=args["until_pattern"],
        tag=args.get("tag"),
        timeout_s=float(args.get("timeout_s", 30.0)),
        serial=args.get("serial"),
    )


def _params_run_unit(args: JsonDict) -> RunUnitTestsParams:
    return RunUnitTestsParams(project_path=Path(args["project_path"]).expanduser())


def _params_run_integration(args: JsonDict) -> RunIntegrationTestsParams:
    return RunIntegrationTestsParams(
        project_path=Path(args["project_path"]).expanduser(),
        test_path=args.get("test_path", "integration_test/"),
        serial=args.get("serial"),
    )


def _params_new_session(args: JsonDict) -> NewSessionParams:
    return NewSessionParams(label=args.get("label"))


def _params_inspect_project(args: JsonDict) -> InspectProjectParams:
    return InspectProjectParams(project_path=Path(args["project_path"]).expanduser())


def _params_list_patrol(args: JsonDict) -> ListPatrolTestsParams:
    return ListPatrolTestsParams(project_path=Path(args["project_path"]).expanduser())


def _params_run_patrol_test(args: JsonDict) -> RunPatrolTestParams:
    return RunPatrolTestParams(
        project_path=Path(args["project_path"]).expanduser(),
        test_path=Path(args["test_path"]),
        serial=args.get("serial"),
        flavor=args.get("flavor"),
        build_mode=BuildMode(args.get("build_mode", "debug")),
    )


def _params_session_summary(args: JsonDict) -> SessionSummaryParams:
    return SessionSummaryParams(session_id=args.get("session_id"))


def _params_prepare_for_test(args: JsonDict) -> PrepareForTestParams:
    return PrepareForTestParams(
        package_id=args["package_id"],
        serial=args.get("serial"),
        skip_clear=bool(args.get("skip_clear", False)),
        capture_evidence=bool(args.get("capture_evidence", True)),
    )


def _params_start_emulator(args: JsonDict) -> StartEmulatorParams:
    return StartEmulatorParams(
        avd_name=args["avd_name"], headless=bool(args.get("headless", False))
    )


def _params_stop_virtual_device(args: JsonDict) -> StopVirtualDeviceParams:
    return StopVirtualDeviceParams(serial=args["serial"])


def _params_list_simulators(args: JsonDict) -> ListSimulatorsParams:
    return ListSimulatorsParams(
        include_shutdown=bool(args.get("include_shutdown", True))
    )


def _params_boot_simulator(args: JsonDict) -> BootSimulatorParams:
    return BootSimulatorParams(name_or_udid=args["name_or_udid"])


# --- dev-session param builders ----------------------------------------


def _params_start_debug_session(args: JsonDict) -> StartDebugSessionParams:
    return StartDebugSessionParams(
        project_path=Path(args["project_path"]).expanduser(),
        mode=BuildMode(args.get("mode", "debug")),
        flavor=args.get("flavor"),
        target=args.get("target"),
        serial=args.get("serial"),
    )


def _params_stop_debug_session(args: JsonDict) -> StopDebugSessionParams:
    return StopDebugSessionParams(session_id=args.get("session_id"))


def _params_restart_debug_session(args: JsonDict) -> RestartDebugSessionParams:
    return RestartDebugSessionParams(
        session_id=args.get("session_id"),
        full_restart=bool(args.get("full_restart", False)),
    )


def _params_attach_debug_session(args: JsonDict) -> AttachDebugSessionParams:
    return AttachDebugSessionParams(
        vm_service_uri=args["vm_service_uri"],
        project_path=Path(args["project_path"]).expanduser(),
    )


def _params_read_debug_log(args: JsonDict) -> ReadDebugLogParams:
    return ReadDebugLogParams(
        session_id=args.get("session_id"),
        since_s=int(args.get("since_s", 30)),
        level=str(args.get("level", "all")),
        max_lines=int(args.get("max_lines", 500)),
    )


def _params_tail_debug_log(args: JsonDict) -> TailDebugLogParams:
    return TailDebugLogParams(
        until_pattern=args["until_pattern"],
        session_id=args.get("session_id"),
        timeout_s=float(args.get("timeout_s", 30.0)),
    )


def _params_call_service_extension(args: JsonDict) -> CallServiceExtensionParams:
    return CallServiceExtensionParams(
        method=args["method"],
        args=args.get("args"),
        session_id=args.get("session_id"),
    )


def _params_dump_widget_tree(args: JsonDict) -> DumpWidgetTreeParams:
    return DumpWidgetTreeParams(session_id=args.get("session_id"))


def _params_toggle_inspector(args: JsonDict) -> ToggleInspectorParams:
    return ToggleInspectorParams(
        enabled=bool(args["enabled"]),
        session_id=args.get("session_id"),
    )


# --- IDE param builders ------------------------------------------------


def _params_open_project_in_ide(args: JsonDict) -> OpenProjectInIdeParams:
    return OpenProjectInIdeParams(
        project_path=Path(args["project_path"]).expanduser(),
        ide=_IdeKind(args.get("ide", "vscode")),
        new_window=bool(args.get("new_window", True)),
    )


def _params_close_ide_window(args: JsonDict) -> CloseIdeWindowParams:
    return CloseIdeWindowParams(
        project_path=Path(args["project_path"]).expanduser()
        if args.get("project_path")
        else None,
        window_id=args.get("window_id"),
    )


def _params_focus_ide_window(args: JsonDict) -> FocusIdeWindowParams:
    return FocusIdeWindowParams(
        project_path=Path(args["project_path"]).expanduser()
    )


def _params_is_ide_available(args: JsonDict) -> IsIdeAvailableParams:
    return IsIdeAvailableParams(ide=_IdeKind(args.get("ide", "vscode")))


def _params_setup_wda(args: JsonDict) -> SetupWebDriverAgentParams:
    return SetupWebDriverAgentParams(
        udid=args["udid"],
        wda_dir=Path(args["wda_dir"]).expanduser() if args.get("wda_dir") else None,
        repo_url=args.get("repo_url", "https://github.com/appium/WebDriverAgent.git"),
        scheme=args.get("scheme", "WebDriverAgentRunner"),
    )


def _params_compare_screenshot(args: JsonDict) -> CompareScreenshotParams:
    return CompareScreenshotParams(
        actual_path=Path(args["actual_path"]).expanduser(),
        golden_path=Path(args["golden_path"]).expanduser(),
        tolerance=float(args.get("tolerance", 0.98)),
        diff_output_path=Path(args["diff_output_path"]).expanduser()
        if args.get("diff_output_path")
        else None,
    )


def _params_detect_markers(args: JsonDict) -> DetectMarkersParams:
    return DetectMarkersParams(
        image_path=Path(args["image_path"]).expanduser(),
        dictionary=args.get("dictionary", "DICT_4X4_50"),
    )


def _params_infer_pose(args: JsonDict) -> InferCameraPoseParams:
    return InferCameraPoseParams(
        image_path=Path(args["image_path"]).expanduser(),
        marker_id=int(args["marker_id"]),
        marker_size_m=float(args["marker_size_m"]),
    )


def _params_wait_for_marker(args: JsonDict) -> WaitForMarkerParams:
    return WaitForMarkerParams(
        marker_id=int(args["marker_id"]),
        timeout_s=float(args.get("timeout_s", 30.0)),
        poll_interval_s=float(args.get("poll_interval_s", 1.0)),
        dictionary=args.get("dictionary", "DICT_4X4_50"),
        serial=args.get("serial"),
    )


def _params_run_test_plan(args: JsonDict) -> RunTestPlanParams:
    return RunTestPlanParams(
        plan_path=Path(args["plan_path"]).expanduser() if args.get("plan_path") else None,
        plan_yaml=args.get("plan_yaml"),
    )


def _params_validate_test_plan(args: JsonDict) -> ValidateTestPlanParams:
    return ValidateTestPlanParams(
        plan_path=Path(args["plan_path"]).expanduser() if args.get("plan_path") else None,
        plan_yaml=args.get("plan_yaml"),
    )


def _params_run_patrol_suite(args: JsonDict) -> RunPatrolSuiteParams:
    return RunPatrolSuiteParams(
        project_path=Path(args["project_path"]).expanduser(),
        test_dir=Path(args.get("test_dir", "integration_test")),
        serial=args.get("serial"),
        flavor=args.get("flavor"),
        build_mode=BuildMode(args.get("build_mode", "debug")),
    )


@dataclass(frozen=True, slots=True)
class UseCases:
    list_devices: ListDevices
    select_device: SelectDevice
    get_selected_device: GetSelectedDevice
    release_device: ReleaseDevice
    list_locks: ListLocks
    force_release_lock: ForceReleaseLock
    check_environment: CheckEnvironment
    describe_capabilities: DescribeCapabilities
    session_summary: SessionSummary
    inspect_project: InspectProject
    prepare_for_test: PrepareForTest
    run_test_plan: RunTestPlan
    validate_test_plan: ValidateTestPlan
    build_app: BuildApp
    install_app: InstallApp
    uninstall_app: UninstallApp
    launch_app: LaunchApp
    stop_app: StopApp
    clear_app_data: ClearAppData
    grant_permission: GrantPermission
    tap: Tap
    tap_text: TapText
    swipe: Swipe
    type_text: TypeText
    press_key: PressKey
    find_element: FindElement
    wait_for_element: WaitForElement
    dump_ui: DumpUi
    assert_visible: AssertVisible
    take_screenshot: TakeScreenshot
    start_recording: StartRecording
    stop_recording: StopRecording
    read_logs: ReadLogs
    tail_logs: TailLogs
    run_unit_tests: RunUnitTests
    run_integration_tests: RunIntegrationTests
    list_patrol_tests: ListPatrolTests
    run_patrol_test: RunPatrolTest
    run_patrol_suite: RunPatrolSuite
    compare_screenshot: CompareScreenshot
    detect_markers: DetectMarkers
    infer_camera_pose: InferCameraPose
    wait_for_marker: WaitForMarker
    list_avds: ListAvds
    start_emulator: StartEmulator
    stop_virtual_device: StopVirtualDevice
    list_simulators: ListSimulators
    boot_simulator: BootSimulator
    # dev-session
    start_debug_session: StartDebugSession
    stop_debug_session: StopDebugSession
    restart_debug_session: RestartDebugSession
    list_debug_sessions: ListDebugSessions
    attach_debug_session: AttachDebugSession
    read_debug_log: ReadDebugLog
    tail_debug_log: TailDebugLog
    call_service_extension: CallServiceExtension
    dump_widget_tree: DumpWidgetTree
    dump_render_tree: DumpRenderTree
    toggle_inspector: ToggleInspector
    # IDE
    open_project_in_ide: OpenProjectInIde
    list_ide_windows: ListIdeWindows
    close_ide_window: CloseIdeWindow
    focus_ide_window: FocusIdeWindow
    is_ide_available: IsIdeAvailable
    # WDA setup
    setup_webdriveragent: SetupWebDriverAgent
    new_session: NewSession
    get_artifacts_dir: GetArtifactsDir


def _bind(uc, params_builder):
    async def invoke(args: JsonDict) -> Result[Any]:
        return await uc(params_builder(args))

    return invoke


def build_registry(uc: UseCases) -> list[ToolDescriptor]:
    serial_prop = {"serial": _string("Device serial. Defaults to the selected device.")}
    package_prop = {"package_id": _string("Android application id, e.g. com.example.app")}

    return [
        ToolDescriptor(
            name="check_environment",
            description=(
                "DOCTOR. Run this FIRST in any session. Reports the status of every "
                "external dependency (adb, flutter, patrol, pymobiledevice3) with "
                "concrete fix commands for any red items."
            ),
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.check_environment, _params_no),
        ),
        ToolDescriptor(
            name="describe_capabilities",
            description=(
                "Return a structured roll-up of platforms, frameworks, gates, and "
                "vision ops this server supports. Autonomous agents call this first "
                "before planning."
            ),
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.describe_capabilities, _params_no),
        ),
        ToolDescriptor(
            name="session_summary",
            description=(
                "Return the audit trail of every tool call in the current session. "
                "Useful for agent self-reflection and report generation."
            ),
            input_schema=_schema({"session_id": _string("Defaults to current.")}),
            build_params=_params_session_summary,
            invoke=_bind(uc.session_summary, _params_session_summary),
        ),
        ToolDescriptor(
            name="prepare_for_test",
            description=(
                "Atomic CLEAN handoff: stop_app + clear_app_data + press home + "
                "evidence screenshot. Returns proof the device is in clean state."
            ),
            input_schema=_schema(
                {
                    "package_id": _string("Application id to clean."),
                    "skip_clear": _bool("Skip clear_app_data (iOS-style flow)."),
                    "capture_evidence": _bool("Default true; takes a PRE_FLIGHT screenshot."),
                    **{"serial": _string("Defaults to selected device.")},
                },
                ["package_id"],
            ),
            build_params=_params_prepare_for_test,
            invoke=_bind(uc.prepare_for_test, _params_prepare_for_test),
        ),
        ToolDescriptor(
            name="run_test_plan",
            description=(
                "Execute a declarative YAML test plan (apiVersion phone-controll/v1). "
                "Walks phases, enforces entry/exit assertions, captures artifacts. "
                "Provide plan_path (file) OR plan_yaml (inline). Call validate_test_plan first if unsure of schema."
            ),
            input_schema=_schema(
                {
                    "plan_path": _string("Path to a v1 YAML plan."),
                    "plan_yaml": _string("Inline YAML plan."),
                }
            ),
            build_params=_params_run_test_plan,
            invoke=_bind(uc.run_test_plan, _params_run_test_plan),
        ),
        ToolDescriptor(
            name="validate_test_plan",
            description=(
                "Lint a YAML plan against the v1 schema WITHOUT running it. "
                "Returns the parsed plan on success or a precise InvalidArgumentFailure. "
                "Cheap iteration loop for agents authoring plans."
            ),
            input_schema=_schema(
                {
                    "plan_path": _string("Path to a v1 YAML plan."),
                    "plan_yaml": _string("Inline YAML plan."),
                }
            ),
            build_params=_params_validate_test_plan,
            invoke=_bind(uc.validate_test_plan, _params_validate_test_plan),
        ),
        ToolDescriptor(
            name="inspect_project",
            description=(
                "Detect what kind of project lives at a path (Flutter, native, RN, web) "
                "and which test frameworks apply. Call this before run_patrol_* / "
                "run_integration_tests so you know which framework will execute."
            ),
            input_schema=_schema(
                {"project_path": _string("Absolute or ~-relative path.")},
                ["project_path"],
            ),
            build_params=_params_inspect_project,
            invoke=_bind(uc.inspect_project, _params_inspect_project),
        ),
        ToolDescriptor(
            name="list_devices",
            description="List all attached Android and iOS devices.",
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.list_devices, _params_no),
        ),
        ToolDescriptor(
            name="select_device",
            description=(
                "Pick a device for this session AND acquire its cross-session lock. "
                "Returns DeviceBusyFailure if another session holds it — set force=true "
                "to break the lock, or call release_device when you're done."
            ),
            input_schema=_schema(
                {
                    "serial": _string("Device serial."),
                    "force": _bool("Override an existing lock held by another session."),
                    "note": _string("Optional human-readable note recorded with the lock."),
                },
                ["serial"],
            ),
            build_params=_params_select_device,
            invoke=_bind(uc.select_device, _params_select_device),
        ),
        ToolDescriptor(
            name="get_selected_device",
            description="Return the currently selected device, or null.",
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.get_selected_device, _params_no),
        ),
        ToolDescriptor(
            name="release_device",
            description=(
                "Release this session's lock on a device. With no serial, releases "
                "the currently selected device. Always call this at end of session."
            ),
            input_schema=_schema(
                {"serial": _string("Defaults to the currently selected device.")}
            ),
            build_params=_params_release_device,
            invoke=_bind(uc.release_device, _params_release_device),
        ),
        ToolDescriptor(
            name="list_locks",
            description=(
                "List active device locks across all MCP sessions. Stale locks "
                "(holder process gone) are auto-cleaned and not returned."
            ),
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.list_locks, _params_no),
        ),
        ToolDescriptor(
            name="force_release_lock",
            description=(
                "ADMIN. Break a lock without holding it — use only when another "
                "session has crashed and the lock is stuck."
            ),
            input_schema=_schema(
                {"serial": _string("Device serial whose lock should be released.")},
                ["serial"],
            ),
            build_params=_params_force_release_lock,
            invoke=_bind(uc.force_release_lock, _params_force_release_lock),
        ),
        ToolDescriptor(
            name="build_app",
            description="Build an app bundle. Android: `flutter build apk`. iOS: `flutter build ipa`.",
            input_schema=_schema(
                {
                    "project_path": _string("Path to the Flutter project root."),
                    "mode": _enum(["debug", "profile", "release"]),
                    "platform": _enum(["android", "ios"]),
                    "flavor": _string(""),
                },
                ["project_path"],
            ),
            build_params=_params_build_app,
            invoke=_bind(uc.build_app, _params_build_app),
        ),
        ToolDescriptor(
            name="install_app",
            description=(
                "Install an app bundle. Provide bundle_path (.apk/.ipa/.app) or project_path. "
                "platform defaults to the selected device's platform."
            ),
            input_schema=_schema(
                {
                    "bundle_path": _string(""),
                    "apk_path": _string("(deprecated) alias for bundle_path"),
                    "project_path": _string(""),
                    "mode": _enum(["debug", "profile", "release"]),
                    "platform": _enum(["android", "ios"]),
                    "flavor": _string(""),
                    **serial_prop,
                }
            ),
            build_params=_params_install_app,
            invoke=_bind(uc.install_app, _params_install_app),
        ),
        ToolDescriptor(
            name="uninstall_app",
            description="Uninstall an app by package id.",
            input_schema=_schema({**package_prop, **serial_prop}, ["package_id"]),
            build_params=_params_uninstall,
            invoke=_bind(uc.uninstall_app, _params_uninstall),
        ),
        ToolDescriptor(
            name="launch_app",
            description="Launch an app. If activity is omitted, uses the LAUNCHER intent.",
            input_schema=_schema(
                {**package_prop, "activity": _string(""), **serial_prop}, ["package_id"]
            ),
            build_params=_params_launch,
            invoke=_bind(uc.launch_app, _params_launch),
        ),
        ToolDescriptor(
            name="stop_app",
            description="Force-stop an app.",
            input_schema=_schema({**package_prop, **serial_prop}, ["package_id"]),
            build_params=_params_stop,
            invoke=_bind(uc.stop_app, _params_stop),
        ),
        ToolDescriptor(
            name="clear_app_data",
            description="Clear an app's data (`pm clear`).",
            input_schema=_schema({**package_prop, **serial_prop}, ["package_id"]),
            build_params=_params_clear,
            invoke=_bind(uc.clear_app_data, _params_clear),
        ),
        ToolDescriptor(
            name="grant_permission",
            description="Grant a runtime permission to an app.",
            input_schema=_schema(
                {**package_prop, "permission": _string(""), **serial_prop},
                ["package_id", "permission"],
            ),
            build_params=_params_grant,
            invoke=_bind(uc.grant_permission, _params_grant),
        ),
        ToolDescriptor(
            name="tap",
            description="Tap at absolute screen coordinates.",
            input_schema=_schema(
                {"x": _int(""), "y": _int(""), **serial_prop}, ["x", "y"]
            ),
            build_params=_params_tap,
            invoke=_bind(uc.tap, _params_tap),
        ),
        ToolDescriptor(
            name="tap_text",
            description=(
                "Tap an on-screen element matched by visible text. "
                "USE FOR SYSTEM UI ONLY (Settings, permission dialogs, ATT prompts). "
                "For your own app's UI prefer Patrol via run_patrol_test — locale-independent."
            ),
            input_schema=_schema(
                {"text": _string(""), "exact": _bool(""), **serial_prop}, ["text"]
            ),
            build_params=_params_tap_text,
            invoke=_bind(uc.tap_text, _params_tap_text),
        ),
        ToolDescriptor(
            name="swipe",
            description="Swipe between two points.",
            input_schema=_schema(
                {
                    "x1": _int(""),
                    "y1": _int(""),
                    "x2": _int(""),
                    "y2": _int(""),
                    "duration_ms": _int(""),
                    **serial_prop,
                },
                ["x1", "y1", "x2", "y2"],
            ),
            build_params=_params_swipe,
            invoke=_bind(uc.swipe, _params_swipe),
        ),
        ToolDescriptor(
            name="type_text",
            description="Type text into the focused field.",
            input_schema=_schema({"text": _string(""), **serial_prop}, ["text"]),
            build_params=_params_type_text,
            invoke=_bind(uc.type_text, _params_type_text),
        ),
        ToolDescriptor(
            name="press_key",
            description="Press a hardware/system key (back, home, enter, ...).",
            input_schema=_schema({"keycode": _string(""), **serial_prop}, ["keycode"]),
            build_params=_params_press_key,
            invoke=_bind(uc.press_key, _params_press_key),
        ),
        ToolDescriptor(
            name="find_element",
            description="Find a UI element by text, resource id or class. Returns null if not found.",
            input_schema=_schema(
                {
                    "text": _string(""),
                    "resource_id": _string(""),
                    "class_name": _string(""),
                    "timeout_s": _number(""),
                    **serial_prop,
                }
            ),
            build_params=_params_find,
            invoke=_bind(uc.find_element, _params_find),
        ),
        ToolDescriptor(
            name="wait_for_element",
            description="Wait until an element is visible. Errors on timeout.",
            input_schema=_schema(
                {
                    "text": _string(""),
                    "resource_id": _string(""),
                    "timeout_s": _number(""),
                    **serial_prop,
                }
            ),
            build_params=_params_wait_for,
            invoke=_bind(uc.wait_for_element, _params_wait_for),
        ),
        ToolDescriptor(
            name="dump_ui",
            description="Return the current UI hierarchy as XML.",
            input_schema=_schema(serial_prop),
            build_params=_params_dump_ui,
            invoke=_bind(uc.dump_ui, _params_dump_ui),
        ),
        ToolDescriptor(
            name="assert_visible",
            description="Assert an element is visible. Returns the element or errors.",
            input_schema=_schema(
                {
                    "text": _string(""),
                    "resource_id": _string(""),
                    "timeout_s": _number(""),
                    **serial_prop,
                }
            ),
            build_params=_params_assert_visible,
            invoke=_bind(uc.assert_visible, _params_assert_visible),
        ),
        ToolDescriptor(
            name="take_screenshot",
            description=(
                "Capture a PNG screenshot to the artifacts dir. "
                "DISCIPLINE: only call at phase boundaries (PRE_FLIGHT, gate-exit, "
                "UNDER_TEST assertion, VERDICT). Label MUST follow "
                "<session>-<PHASE>-<outcome> (e.g. 'UMP_GATE-declined', "
                "'UNDER_TEST-anchor-placed'). Do NOT screenshot speculatively, "
                "after a tool returned ok:false, or after a decline branch."
            ),
            input_schema=_schema(
                {
                    "label": _string(
                        "Required by convention: <PHASE>-<outcome>. "
                        "Examples: 'PRE_FLIGHT-home', 'UMP_GATE-declined', "
                        "'UNDER_TEST-ac1-pass', 'VERDICT_BLOCKED'."
                    ),
                    **serial_prop,
                }
            ),
            build_params=_params_screenshot,
            invoke=_bind(uc.take_screenshot, _params_screenshot),
        ),
        ToolDescriptor(
            name="start_recording",
            description="Start a screen recording. Stop with stop_recording.",
            input_schema=_schema({"label": _string(""), **serial_prop}),
            build_params=_params_start_recording,
            invoke=_bind(uc.start_recording, _params_start_recording),
        ),
        ToolDescriptor(
            name="stop_recording",
            description="Stop the active screen recording and pull the file.",
            input_schema=_schema(serial_prop),
            build_params=_params_stop_recording,
            invoke=_bind(uc.stop_recording, _params_stop_recording),
        ),
        ToolDescriptor(
            name="read_logs",
            description=(
                "Read recent logcat lines. DISCIPLINE: call once per phase end, "
                "with a tag filter when possible. Use as evidence for the report — "
                "not as a polling primitive. For 'wait until X happens' use tail_logs."
            ),
            input_schema=_schema(
                {
                    "since_s": _int(""),
                    "tag": _string(""),
                    "min_level": _enum(["V", "D", "I", "W", "E", "F"]),
                    "max_lines": _int(""),
                    **serial_prop,
                }
            ),
            build_params=_params_read_logs,
            invoke=_bind(uc.read_logs, _params_read_logs),
        ),
        ToolDescriptor(
            name="tail_logs",
            description="Stream logcat until a regex matches a line, or timeout.",
            input_schema=_schema(
                {
                    "until_pattern": _string(""),
                    "tag": _string(""),
                    "timeout_s": _number(""),
                    **serial_prop,
                },
                ["until_pattern"],
            ),
            build_params=_params_tail_logs,
            invoke=_bind(uc.tail_logs, _params_tail_logs),
        ),
        ToolDescriptor(
            name="run_unit_tests",
            description="Run `flutter test` (unit / widget tests, no device).",
            input_schema=_schema({"project_path": _string("")}, ["project_path"]),
            build_params=_params_run_unit,
            invoke=_bind(uc.run_unit_tests, _params_run_unit),
        ),
        ToolDescriptor(
            name="run_integration_tests",
            description=(
                "Run integration tests on the selected device. Routes to Patrol if the "
                "project supports it, otherwise plain `flutter test integration_test/`."
            ),
            input_schema=_schema(
                {
                    "project_path": _string(""),
                    "test_path": _string(""),
                    **serial_prop,
                },
                ["project_path"],
            ),
            build_params=_params_run_integration,
            invoke=_bind(uc.run_integration_tests, _params_run_integration),
        ),
        ToolDescriptor(
            name="list_patrol_tests",
            description=(
                "PREFERRED for Flutter. Discover Patrol-style integration test files "
                "under `integration_test/` (any *_test.dart). Returns paths Claude can "
                "feed into run_patrol_test."
            ),
            input_schema=_schema({"project_path": _string("")}, ["project_path"]),
            build_params=_params_list_patrol,
            invoke=_bind(uc.list_patrol_tests, _params_list_patrol),
        ),
        ToolDescriptor(
            name="run_patrol_test",
            description=(
                "PREFERRED for Flutter. Run a single Patrol test file on the selected "
                "device. Locale-independent (drives by widget Keys), works for AR / "
                "Vision / native plugin code paths via patrol_finders + native automator."
            ),
            input_schema=_schema(
                {
                    "project_path": _string("Flutter project root."),
                    "test_path": _string("Path to a *_test.dart file."),
                    "flavor": _string(""),
                    "build_mode": _enum(["debug", "profile", "release"]),
                    **serial_prop,
                },
                ["project_path", "test_path"],
            ),
            build_params=_params_run_patrol_test,
            invoke=_bind(uc.run_patrol_test, _params_run_patrol_test),
        ),
        ToolDescriptor(
            name="run_patrol_suite",
            description=(
                "PREFERRED for Flutter. Run an entire Patrol test directory (default "
                "`integration_test/`) on the selected device."
            ),
            input_schema=_schema(
                {
                    "project_path": _string("Flutter project root."),
                    "test_dir": _string("Defaults to integration_test/"),
                    "flavor": _string(""),
                    "build_mode": _enum(["debug", "profile", "release"]),
                    **serial_prop,
                },
                ["project_path"],
            ),
            build_params=_params_run_patrol_suite,
            invoke=_bind(uc.run_patrol_suite, _params_run_patrol_suite),
        ),
        ToolDescriptor(
            name="compare_screenshot",
            description=(
                "Pixel-diff an actual screenshot against a golden image. Returns a "
                "similarity score and a diff image highlighting changed regions. "
                "For AR/UI regression testing on a fixed camera stand."
            ),
            input_schema=_schema(
                {
                    "actual_path": _string("Path to the captured screenshot."),
                    "golden_path": _string("Path to the golden image."),
                    "tolerance": _number("Similarity threshold 0..1 (default 0.98)."),
                    "diff_output_path": _string("Optional path to write the diff overlay."),
                },
                ["actual_path", "golden_path"],
            ),
            build_params=_params_compare_screenshot,
            invoke=_bind(uc.compare_screenshot, _params_compare_screenshot),
        ),
        ToolDescriptor(
            name="detect_markers",
            description=(
                "Detect ArUco fiducial markers in an image. Returns id, corners, "
                "and center for each. Default dictionary DICT_4X4_50."
            ),
            input_schema=_schema(
                {
                    "image_path": _string("Path to a PNG or JPG image."),
                    "dictionary": _enum(
                        ["DICT_4X4_50", "DICT_5X5_50", "DICT_6X6_250", "DICT_ARUCO_ORIGINAL"]
                    ),
                },
                ["image_path"],
            ),
            build_params=_params_detect_markers,
            invoke=_bind(uc.detect_markers, _params_detect_markers),
        ),
        ToolDescriptor(
            name="infer_camera_pose",
            description=(
                "Estimate camera pose from a single ArUco marker of known physical "
                "size. Returns rvec/tvec. Default intrinsics are coarse — supply "
                "your stand's camera matrix for accurate results."
            ),
            input_schema=_schema(
                {
                    "image_path": _string(""),
                    "marker_id": _int("ArUco marker ID."),
                    "marker_size_m": _number("Marker side length in meters."),
                },
                ["image_path", "marker_id", "marker_size_m"],
            ),
            build_params=_params_infer_pose,
            invoke=_bind(uc.infer_camera_pose, _params_infer_pose),
        ),
        ToolDescriptor(
            name="wait_for_marker",
            description=(
                "Poll screenshots until an ArUco marker appears or timeout. Useful "
                "for gating AR test phases on physical-scene readiness."
            ),
            input_schema=_schema(
                {
                    "marker_id": _int(""),
                    "timeout_s": _number("Default 30s."),
                    "poll_interval_s": _number("Default 1s."),
                    "dictionary": _enum(
                        ["DICT_4X4_50", "DICT_5X5_50", "DICT_6X6_250", "DICT_ARUCO_ORIGINAL"]
                    ),
                    **serial_prop,
                },
                ["marker_id"],
            ),
            build_params=_params_wait_for_marker,
            invoke=_bind(uc.wait_for_marker, _params_wait_for_marker),
        ),
        ToolDescriptor(
            name="list_avds",
            description="List available Android Virtual Devices (emulator -list-avds).",
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.list_avds, _params_no),
        ),
        ToolDescriptor(
            name="start_emulator",
            description=(
                "Boot an Android emulator and wait until it registers with adb "
                "(up to 90s). Returns the emulator's serial."
            ),
            input_schema=_schema(
                {
                    "avd_name": _string("Name of the AVD."),
                    "headless": _bool("Run with -no-window. Default false."),
                },
                ["avd_name"],
            ),
            build_params=_params_start_emulator,
            invoke=_bind(uc.start_emulator, _params_start_emulator),
        ),
        ToolDescriptor(
            name="list_simulators",
            description=(
                "List iOS Simulators via xcrun simctl. By default includes "
                "shutdown ones so they can be booted."
            ),
            input_schema=_schema(
                {
                    "include_shutdown": _bool(
                        "Default true; set false for booted-only listing."
                    )
                }
            ),
            build_params=_params_list_simulators,
            invoke=_bind(uc.list_simulators, _params_list_simulators),
        ),
        ToolDescriptor(
            name="boot_simulator",
            description=(
                "Boot an iOS simulator by name (e.g. \"iPhone 15\") or UDID. "
                "Returns the booted Device — use its serial in select_device."
            ),
            input_schema=_schema(
                {"name_or_udid": _string("Simulator name or UDID.")},
                ["name_or_udid"],
            ),
            build_params=_params_boot_simulator,
            invoke=_bind(uc.boot_simulator, _params_boot_simulator),
        ),
        ToolDescriptor(
            name="stop_virtual_device",
            description=(
                "Shut down an Android emulator (emulator-XXXX) or iOS simulator "
                "(UDID). Auto-detects by serial format."
            ),
            input_schema=_schema(
                {"serial": _string("Emulator serial or simulator UDID.")},
                ["serial"],
            ),
            build_params=_params_stop_virtual_device,
            invoke=_bind(uc.stop_virtual_device, _params_stop_virtual_device),
        ),
        # ---- dev session lifecycle ------------------------------------
        ToolDescriptor(
            name="start_debug_session",
            description=(
                "Boot `flutter run --machine` against the selected device and wait "
                "for app.started. Requires this session to hold the device lock."
            ),
            input_schema=_schema(
                {
                    "project_path": _string("Flutter project root."),
                    "mode": _enum(["debug", "profile", "release"]),
                    "flavor": _string(""),
                    "target": _string("Optional entry-point dart file."),
                    "serial": _string("Defaults to selected device."),
                },
                ["project_path"],
            ),
            build_params=_params_start_debug_session,
            invoke=_bind(uc.start_debug_session, _params_start_debug_session),
        ),
        ToolDescriptor(
            name="stop_debug_session",
            description="Stop a debug session. Defaults to the most-recently-started.",
            input_schema=_schema({"session_id": _string("")}),
            build_params=_params_stop_debug_session,
            invoke=_bind(uc.stop_debug_session, _params_stop_debug_session),
        ),
        ToolDescriptor(
            name="restart_debug_session",
            description="Hot reload (default) or hot restart (full_restart=true).",
            input_schema=_schema(
                {
                    "session_id": _string(""),
                    "full_restart": _bool("Default false (hot reload)."),
                }
            ),
            build_params=_params_restart_debug_session,
            invoke=_bind(uc.restart_debug_session, _params_restart_debug_session),
        ),
        ToolDescriptor(
            name="list_debug_sessions",
            description="List all debug sessions owned by this MCP process.",
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.list_debug_sessions, _params_no),
        ),
        ToolDescriptor(
            name="attach_debug_session",
            description=(
                "Attach to a `flutter run` started outside this MCP via its VM "
                "service URI. Advanced; not implemented in v1."
            ),
            input_schema=_schema(
                {
                    "vm_service_uri": _string(""),
                    "project_path": _string(""),
                },
                ["vm_service_uri", "project_path"],
            ),
            build_params=_params_attach_debug_session,
            invoke=_bind(uc.attach_debug_session, _params_attach_debug_session),
        ),
        ToolDescriptor(
            name="read_debug_log",
            description=(
                "Recent log slice from a debug session (app + daemon events). "
                "Filters by level and a window in seconds."
            ),
            input_schema=_schema(
                {
                    "session_id": _string(""),
                    "since_s": _int(""),
                    "level": _enum(["all", "info", "warning", "error", "progress"]),
                    "max_lines": _int(""),
                }
            ),
            build_params=_params_read_debug_log,
            invoke=_bind(uc.read_debug_log, _params_read_debug_log),
        ),
        ToolDescriptor(
            name="tail_debug_log",
            description="Wait until a regex matches a log line, or timeout.",
            input_schema=_schema(
                {
                    "until_pattern": _string(""),
                    "session_id": _string(""),
                    "timeout_s": _number(""),
                },
                ["until_pattern"],
            ),
            build_params=_params_tail_debug_log,
            invoke=_bind(uc.tail_debug_log, _params_tail_debug_log),
        ),
        ToolDescriptor(
            name="call_service_extension",
            description=(
                "Call a registered VM service extension (ext.flutter.*). Returns "
                "the result and elapsed_ms."
            ),
            input_schema=_schema(
                {
                    "method": _string("e.g. ext.flutter.debugDumpApp"),
                    "args": {"type": "object", "additionalProperties": True},
                    "session_id": _string(""),
                },
                ["method"],
            ),
            build_params=_params_call_service_extension,
            invoke=_bind(uc.call_service_extension, _params_call_service_extension),
        ),
        ToolDescriptor(
            name="dump_widget_tree",
            description="Convenience for ext.flutter.debugDumpApp.",
            input_schema=_schema({"session_id": _string("")}),
            build_params=_params_dump_widget_tree,
            invoke=_bind(uc.dump_widget_tree, _params_dump_widget_tree),
        ),
        ToolDescriptor(
            name="dump_render_tree",
            description="Convenience for ext.flutter.debugDumpRenderTree.",
            input_schema=_schema({"session_id": _string("")}),
            build_params=_params_dump_widget_tree,
            invoke=_bind(uc.dump_render_tree, _params_dump_widget_tree),
        ),
        ToolDescriptor(
            name="toggle_inspector",
            description="Toggle the Flutter widget inspector overlay (ext.flutter.inspector.show).",
            input_schema=_schema(
                {
                    "enabled": _bool(""),
                    "session_id": _string(""),
                },
                ["enabled"],
            ),
            build_params=_params_toggle_inspector,
            invoke=_bind(uc.toggle_inspector, _params_toggle_inspector),
        ),
        # ---- IDE windows ---------------------------------------------
        ToolDescriptor(
            name="open_project_in_ide",
            description=(
                "Open a project in a NEW VS Code window (`code -n <path>` by "
                "default). Tracks the spawned PID for later close."
            ),
            input_schema=_schema(
                {
                    "project_path": _string(""),
                    "ide": _enum(["vscode"]),
                    "new_window": _bool("Default true."),
                },
                ["project_path"],
            ),
            build_params=_params_open_project_in_ide,
            invoke=_bind(uc.open_project_in_ide, _params_open_project_in_ide),
        ),
        ToolDescriptor(
            name="list_ide_windows",
            description="List IDE windows opened by this MCP process.",
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.list_ide_windows, _params_no),
        ),
        ToolDescriptor(
            name="close_ide_window",
            description="Close an IDE window by project_path or window_id.",
            input_schema=_schema(
                {
                    "project_path": _string(""),
                    "window_id": _string(""),
                }
            ),
            build_params=_params_close_ide_window,
            invoke=_bind(uc.close_ide_window, _params_close_ide_window),
        ),
        ToolDescriptor(
            name="focus_ide_window",
            description="Bring the IDE window to the foreground (macOS osascript).",
            input_schema=_schema(
                {"project_path": _string("")},
                ["project_path"],
            ),
            build_params=_params_focus_ide_window,
            invoke=_bind(uc.focus_ide_window, _params_focus_ide_window),
        ),
        ToolDescriptor(
            name="is_ide_available",
            description="Returns the IDE version string if installed; else error.",
            input_schema=_schema({"ide": _enum(["vscode"])}),
            build_params=_params_is_ide_available,
            invoke=_bind(uc.is_ide_available, _params_is_ide_available),
        ),
        ToolDescriptor(
            name="setup_webdriveragent",
            description=(
                "Build WebDriverAgent for an iOS device (one-time per device, "
                "long-running). Clones the Appium WDA repo if `wda_dir` not "
                "given, then `xcodebuild build-for-testing`."
            ),
            input_schema=_schema(
                {
                    "udid": _string(""),
                    "wda_dir": _string("Existing WDA checkout (skip clone)."),
                    "repo_url": _string(""),
                    "scheme": _string("Default WebDriverAgentRunner."),
                },
                ["udid"],
            ),
            build_params=_params_setup_wda,
            invoke=_bind(uc.setup_webdriveragent, _params_setup_wda),
        ),
        ToolDescriptor(
            name="new_session",
            description="Create a new artifacts session directory.",
            input_schema=_schema({"label": _string("")}),
            build_params=_params_new_session,
            invoke=_bind(uc.new_session, _params_new_session),
        ),
        ToolDescriptor(
            name="get_artifacts_dir",
            description="Return the current artifacts directory.",
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.get_artifacts_dir, _params_no),
        ),
    ]


class ToolDispatcher:
    """Generic dispatcher: name → ToolDescriptor → uniform JSON envelope.

    Records every call into an optional SessionTraceRepository for autonomy.
    """

    def __init__(
        self,
        descriptors: list[ToolDescriptor],
        trace_repo=None,
    ) -> None:
        self._by_name = {d.name: d for d in descriptors}
        self._trace_repo = trace_repo

    @property
    def descriptors(self) -> list[ToolDescriptor]:
        return list(self._by_name.values())

    def has(self, name: str) -> bool:
        return name in self._by_name

    async def dispatch(self, name: str, args: JsonDict | None) -> JsonDict:
        envelope = await self._dispatch_unrecorded(name, args)
        if self._trace_repo is not None:
            await self._record(name, args, envelope)
        return envelope

    async def _dispatch_unrecorded(
        self, name: str, args: JsonDict | None
    ) -> JsonDict:
        descriptor = self._by_name.get(name)
        if descriptor is None:
            return {
                "ok": False,
                "error": {
                    "code": "UnknownTool",
                    "message": name,
                    "next_action": "describe_capabilities",
                },
            }
        try:
            result = await descriptor.invoke(args or {})
        except KeyError as e:
            return {
                "ok": False,
                "error": {
                    "code": "InvalidArgumentFailure",
                    "message": f"Missing required argument: {e.args[0]}",
                    "next_action": "fix_arguments",
                },
            }
        except (TypeError, ValueError) as e:
            return {
                "ok": False,
                "error": {
                    "code": "InvalidArgumentFailure",
                    "message": str(e),
                    "next_action": "fix_arguments",
                },
            }
        if isinstance(result, Err):
            error: JsonDict = {
                "code": result.failure.code,
                "message": result.failure.message,
                "details": to_jsonable(result.failure.details),
            }
            if result.failure.next_action is not None:
                error["next_action"] = result.failure.next_action
            return {"ok": False, "error": error}
        return {"ok": True, "data": to_jsonable(result.value)}

    async def _record(
        self, name: str, args: JsonDict | None, envelope: JsonDict
    ) -> None:
        from ..domain.entities import TraceEntry  # local: avoid cycles

        seq_fn = getattr(self._trace_repo, "next_sequence", lambda: 0)
        seq = seq_fn() if callable(seq_fn) else 0
        artifacts: tuple[str, ...] = ()
        data = envelope.get("data") if envelope.get("ok") else None
        if isinstance(data, str) and data.endswith((".png", ".mp4", ".xml")):
            artifacts = (data,)
        elif isinstance(data, dict) and isinstance(data.get("evidence_screenshot"), str):
            artifacts = (data["evidence_screenshot"],)
        summary = (
            "ok" if envelope.get("ok")
            else (envelope.get("error") or {}).get("code", "error")
        )
        await self._trace_repo.record(
            TraceEntry(
                sequence=seq,
                tool_name=name,
                args=dict(args or {}),
                ok=bool(envelope.get("ok")),
                error_code=(envelope.get("error") or {}).get("code") if not envelope.get("ok") else None,
                summary=str(summary)[:200],
                artifact_paths=artifacts,
            )
        )
