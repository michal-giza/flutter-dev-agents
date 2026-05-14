"""Declarative MCP tool registry. Maps tool name → (schema, params builder, use case).

Adding a new tool means adding one ToolDescriptor — the dispatcher and MCP server are generic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.result import Err, Result
from ..domain.usecases.artifact_retention import (
    DiskUsage,
    PruneOriginals,
)
from ..domain.usecases.artifacts import (
    FetchArtifact,
    GetArtifactsDir,
    NewSession,
)
from ..domain.usecases.build_install import (
    BuildApp,
    InstallApp,
    UninstallApp,
)
from ..domain.usecases.code_quality import (
    DartAnalyze,
    DartFix,
    DartFormat,
    FlutterPubGet,
    FlutterPubOutdated,
    QualityGate,
)
from ..domain.usecases.crag import (
    CorrectiveRecall,
)
from ..domain.usecases.debug_inspect import (
    VmEvaluate,
    VmListIsolates,
)
from ..domain.usecases.dev_session import (
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
from ..domain.usecases.devices import (
    ForceReleaseLock,
    GetSelectedDevice,
    ListDevices,
    ListLocks,
    ReleaseDevice,
    SelectDevice,
)
from ..domain.usecases.discovery import (
    DescribeCapabilities,
    DescribeTool,
    SessionSummary,
    ToolUsageReportUseCase,
)
from ..domain.usecases.doctor import CheckEnvironment
from ..domain.usecases.ide import (
    CloseIdeWindow,
    FocusIdeWindow,
    IsIdeAvailable,
    ListIdeWindows,
    OpenProjectInIde,
    WriteVscodeLaunchConfig,
)
from ..domain.usecases.lifecycle import (
    ClearAppData,
    GrantPermission,
    LaunchApp,
    StopApp,
)
from ..domain.usecases.mcp_ping import McpPing
from ..domain.usecases.narrate import Narrate
from ..domain.usecases.notify_webhook import (
    NotifyWebhook,
)
from ..domain.usecases.observation import (
    ReadLogs,
    StartRecording,
    StopRecording,
    TailLogs,
    TakeScreenshot,
)
from ..domain.usecases.ocr import (
    OcrScreenshot,
)
from ..domain.usecases.patch_safe import (
    PatchApplySafe,
)
from ..domain.usecases.patrol import (
    ListPatrolTests,
    RunPatrolSuite,
    RunPatrolTest,
)
from ..domain.usecases.plan import (
    RunTestPlan,
    ValidateTestPlan,
)
from ..domain.usecases.preparation import PrepareForTest
from ..domain.usecases.productivity import (
    FindFlutterWidget,
    GrepLogs,
    RunQuickCheck,
    ScaffoldFeature,
    SummarizeSession,
)
from ..domain.usecases.projects import InspectProject
from ..domain.usecases.recall import (
    IndexProject,
    Recall,
)
from ..domain.usecases.release_screenshot import (
    CaptureReleaseScreenshot,
)
from ..domain.usecases.set_agent_profile import (
    PROFILES as _AGENT_PROFILES,
)
from ..domain.usecases.set_agent_profile import (
    SetAgentProfile,
)
from ..domain.usecases.skill_library import (
    ListSkills,
    PromoteSequence,
    ReplaySkill,
)
from ..domain.usecases.testing import (
    RunIntegrationTests,
    RunUnitTests,
)
from ..domain.usecases.ui_graph import (
    ExtractUiGraph,
)
from ..domain.usecases.ui_input import (
    PressKey,
    Swipe,
    Tap,
    TapText,
    TypeText,
)
from ..domain.usecases.ui_query import (
    AssertVisible,
    DumpUi,
    FindElement,
    WaitForElement,
)
from ..domain.usecases.ui_verify import (
    AssertNoErrorsSince,
    TapAndVerify,
)
from ..domain.usecases.virtual_devices import (
    BootSimulator,
    ListAvds,
    ListSimulators,
    StartEmulator,
    StopVirtualDevice,
)
from ..domain.usecases.vision import (
    CompareScreenshot,
    DetectMarkers,
    InferCameraPose,
    WaitForMarker,
)
from ..domain.usecases.vision_advanced import (
    AssertPoseStable,
    CalibrateCamera,
    SaveGoldenImage,
    WaitForArSessionReady,
)
from ..domain.usecases.wda_setup import (
    SetupWebDriverAgent,
)

# ToolDescriptor + schema helpers + all param-builders were extracted to
# `presentation/descriptors/` so this file is the registration logic, not a
# 2900-LOC god module. `ToolDescriptor`, `JsonDict`, and the helpers are
# re-exported here for backward compatibility — many tests + other modules
# import them from `tool_registry`.
from .descriptors._param_builders import (
    _params_assert_no_errors,
    _params_assert_pose_stable,
    _params_assert_visible,
    _params_attach_debug_session,
    _params_boot_simulator,
    _params_build_app,
    _params_calibrate_camera,
    _params_call_service_extension,
    _params_capture_release_screenshot,
    _params_clear,
    _params_close_ide_window,
    _params_compare_screenshot,
    _params_dart_analyze,
    _params_dart_fix,
    _params_dart_format,
    _params_describe_capabilities,
    _params_describe_tool,
    _params_detect_markers,
    _params_dump_ui,
    _params_dump_widget_tree,
    _params_extract_ui_graph,
    _params_fetch_artifact,
    _params_find,
    _params_find_flutter_widget,
    _params_flutter_pub_get,
    _params_flutter_pub_outdated,
    _params_focus_ide_window,
    _params_force_release_lock,
    _params_grant,
    _params_grep_logs,
    _params_index_project,
    _params_infer_pose,
    _params_inspect_project,
    _params_install_app,
    _params_is_ide_available,
    _params_launch,
    _params_list_patrol,
    _params_list_simulators,
    _params_narrate,
    _params_new_session,
    _params_notify_webhook,
    _params_ocr_screenshot,
    _params_open_project_in_ide,
    _params_patch_apply_safe,
    _params_prepare_for_test,
    _params_press_key,
    _params_promote_sequence,
    _params_prune_originals,
    _params_quality_gate,
    _params_read_debug_log,
    _params_read_logs,
    _params_recall,
    _params_recall_corrective,
    _params_release_device,
    _params_replay_skill,
    _params_restart_debug_session,
    _params_run_integration,
    _params_run_patrol_suite,
    _params_run_patrol_test,
    _params_run_quick_check,
    _params_run_test_plan,
    _params_run_unit,
    _params_save_golden_image,
    _params_scaffold_feature,
    _params_screenshot,
    _params_select_device,
    _params_session_summary,
    _params_set_agent_profile,
    _params_setup_wda,
    _params_start_debug_session,
    _params_start_emulator,
    _params_start_recording,
    _params_stop,
    _params_stop_debug_session,
    _params_stop_recording,
    _params_stop_virtual_device,
    _params_summarize_session,
    _params_swipe,
    _params_tail_debug_log,
    _params_tail_logs,
    _params_tap,
    _params_tap_and_verify,
    _params_tap_text,
    _params_toggle_inspector,
    _params_tool_usage_report,
    _params_type_text,
    _params_uninstall,
    _params_validate_test_plan,
    _params_vm_evaluate,
    _params_vm_list_isolates,
    _params_wait_for,
    _params_wait_for_ar_session_ready,
    _params_wait_for_marker,
    _params_write_vscode_launch_config,
)
from .descriptors._shared import (
    JsonDict,
    ToolDescriptor,
    _bool,
    _enum,
    _int,
    _number,
    _params_no,
    _schema,
    _string,
)
from .serialization import to_jsonable


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
    describe_tool: DescribeTool
    session_summary: SessionSummary
    tool_usage_report: ToolUsageReportUseCase
    mcp_ping: McpPing
    set_agent_profile: SetAgentProfile
    notify_webhook: NotifyWebhook
    disk_usage: DiskUsage
    prune_originals: PruneOriginals
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
    tap_and_verify: TapAndVerify
    assert_no_errors_since: AssertNoErrorsSince
    extract_ui_graph: ExtractUiGraph
    ocr_screenshot: OcrScreenshot
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
    write_vscode_launch_config: WriteVscodeLaunchConfig
    # WDA setup
    setup_webdriveragent: SetupWebDriverAgent
    # Code quality
    dart_analyze: DartAnalyze
    dart_format: DartFormat
    dart_fix: DartFix
    flutter_pub_get: FlutterPubGet
    flutter_pub_outdated: FlutterPubOutdated
    quality_gate: QualityGate
    patch_apply_safe: PatchApplySafe
    narrate: Narrate
    scaffold_feature: ScaffoldFeature
    run_quick_check: RunQuickCheck
    grep_logs: GrepLogs
    summarize_session: SummarizeSession
    find_flutter_widget: FindFlutterWidget
    recall: Recall
    recall_corrective: CorrectiveRecall
    index_project: IndexProject
    capture_release_screenshot: CaptureReleaseScreenshot
    promote_sequence: PromoteSequence
    list_skills: ListSkills
    replay_skill: ReplaySkill
    # Advanced AR / Vision
    calibrate_camera: CalibrateCamera
    assert_pose_stable: AssertPoseStable
    wait_for_ar_session_ready: WaitForArSessionReady
    save_golden_image: SaveGoldenImage
    # DAP-lite
    vm_list_isolates: VmListIsolates
    vm_evaluate: VmEvaluate
    new_session: NewSession
    get_artifacts_dir: GetArtifactsDir
    fetch_artifact: FetchArtifact


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
                "Return platforms, frameworks, gates, vision ops, plan_schema, and "
                "the tool subset for the given level (basic/intermediate/expert). "
                "Call first before planning. 4B models should pass level='basic'."
            ),
            input_schema=_schema(
                {
                    "level": _enum(["basic", "intermediate", "expert"]),
                }
            ),
            build_params=_params_describe_capabilities,
            invoke=_bind(uc.describe_capabilities, _params_describe_capabilities),
        ),
        ToolDescriptor(
            name="describe_tool",
            description=(
                "Full description, JSONSchema, and a copy-pasteable example for "
                "ONE tool. Fetch this only for the tool you're about to call to "
                "save context for small LLMs."
            ),
            input_schema=_schema(
                {"name": _string("Tool name (e.g. 'select_device').")},
                ["name"],
            ),
            build_params=_params_describe_tool,
            invoke=_bind(uc.describe_tool, _params_describe_tool),
        ),
        ToolDescriptor(
            name="mcp_ping",
            description=(
                "Identify the running MCP: version, git sha, uptime, "
                "image backends, tool count. Call first if a feature "
                "seems missing — a stale subprocess is usually the cause."
            ),
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.mcp_ping, _params_no),
        ),
        ToolDescriptor(
            name="set_agent_profile",
            description=(
                "Apply a known agent profile (claude / haiku / qwen2.5-7b "
                "/ qwen2.5-14b / llava / default). Flips image cap, "
                "auto-narrate, strict schemas, Reflexion retries at once."
            ),
            input_schema=_schema(
                {
                    "name": _enum(
                        sorted(_AGENT_PROFILES.keys()),
                        "Profile name. Default for Claude is 'claude'.",
                    ),
                },
                ["name"],
            ),
            build_params=_params_set_agent_profile,
            invoke=_bind(uc.set_agent_profile, _params_set_agent_profile),
        ),
        ToolDescriptor(
            name="notify_webhook",
            description=(
                "POST a structured event to an n8n / Slack / generic "
                "webhook. Use for outbound notifications (build green, "
                "release ready). Lock down hosts via MCP_WEBHOOK_ALLOWLIST."
            ),
            input_schema=_schema(
                {
                    "url": _string("Webhook URL (https, or http on localhost)."),
                    "event": _string("Snake_case event identifier."),
                    "payload": {
                        "type": "object",
                        "description": "JSON payload sent under `payload`.",
                    },
                    "auth_bearer": _string("Optional Bearer token."),
                    "auth_header_name": _string("Optional custom auth header."),
                    "auth_header_value": _string(""),
                    "timeout_s": _number("HTTP timeout (default 10)."),
                },
                ["url", "event"],
            ),
            build_params=_params_notify_webhook,
            invoke=_bind(uc.notify_webhook, _params_notify_webhook),
        ),
        ToolDescriptor(
            name="disk_usage",
            description=(
                "Report bytes used in the artifacts root, bucketed: "
                "screenshots, originals (.orig.png companions), goldens, "
                "release, logs, recordings, other. Useful before pruning."
            ),
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.disk_usage, _params_no),
        ),
        ToolDescriptor(
            name="prune_originals",
            description=(
                "Delete `.orig.png` companions older than older_than_days "
                "(defaults to MCP_ORIG_RETENTION_DAYS or 14). Conservative: "
                "never touches capped screenshots, goldens, or release. "
                "Run with dry_run=true first to see what would be removed."
            ),
            input_schema=_schema(
                {
                    "older_than_days": _int(
                        "Retention window in days. Defaults to env or 14."
                    ),
                    "dry_run": _bool(
                        "Report candidates without deleting (default false)."
                    ),
                }
            ),
            build_params=_params_prune_originals,
            invoke=_bind(uc.prune_originals, _params_prune_originals),
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
            name="tool_usage_report",
            description=(
                "Aggregate the session trace into per-tool usage stats. "
                "Surfaces dead tools, top-N callers, and per-tool error rates."
            ),
            input_schema=_schema(
                {
                    "session_id": _string("Defaults to current."),
                    "top_n": _int("Top-N rows to include (default 10)."),
                }
            ),
            build_params=_params_tool_usage_report,
            invoke=_bind(uc.tool_usage_report, _params_tool_usage_report),
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
            name="tap_and_verify",
            description=(
                "Tap text then assert an expected element appears within "
                "timeout_s. Use for any tap that should produce visible state."
            ),
            input_schema=_schema(
                {
                    "text": _string("Text to tap."),
                    "expect_text": _string("Text that must appear after tap."),
                    "expect_resource_id": _string("Resource id alternative."),
                    "timeout_s": _number("Verification timeout (default 5)."),
                    "exact": _bool(""),
                    **serial_prop,
                },
                required=["text"],
            ),
            build_params=_params_tap_and_verify,
            invoke=_bind(uc.tap_and_verify, _params_tap_and_verify),
        ),
        ToolDescriptor(
            name="assert_no_errors_since",
            description=(
                "Fail if any ERROR-level log entries appeared in the last "
                "since_s seconds. Use as a checkpoint after each test step."
            ),
            input_schema=_schema(
                {
                    "since_s": _int("Lookback window in seconds (default 30)."),
                    "tag": _string("Optional log tag filter."),
                    **serial_prop,
                }
            ),
            build_params=_params_assert_no_errors,
            invoke=_bind(uc.assert_no_errors_since, _params_assert_no_errors),
        ),
        ToolDescriptor(
            name="extract_ui_graph",
            description=(
                "Parse the device UI into a typed graph: clickables, "
                "inputs, texts, images. Cheaper than vision-model calls. "
                "Aligned with CogAgent / ShowUI / OS-Atlas pattern."
            ),
            input_schema=_schema(
                {
                    "max_nodes": _int("Cap on returned nodes (default 200)."),
                    **serial_prop,
                }
            ),
            build_params=_params_extract_ui_graph,
            invoke=_bind(uc.extract_ui_graph, _params_extract_ui_graph),
        ),
        ToolDescriptor(
            name="ocr_screenshot",
            description=(
                "Extract text from a PNG via Vision / Tesseract / easyocr "
                "(tried in order). Use to 'read' a screen without a "
                "vision model. Reads full-res original when present."
            ),
            input_schema=_schema(
                {
                    "path": _string("Path to a PNG."),
                    "languages": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Languages, e.g. ['eng','pol']. Default ['eng'].",
                    },
                    "min_confidence": _number("0..1; easyocr only."),
                },
                ["path"],
            ),
            build_params=_params_ocr_screenshot,
            invoke=_bind(uc.ocr_screenshot, _params_ocr_screenshot),
        ),
        ToolDescriptor(
            name="take_screenshot",
            description=(
                "Capture a PNG screenshot to the artifacts dir. Call only at "
                "phase boundaries; label as <PHASE>-<outcome>. Don't shoot "
                "speculatively or after a failed tool call."
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
            name="capture_release_screenshot",
            description=(
                "Full-res PNG for app-store listings. Returns metadata + "
                "256px thumbnail; full-res file is NOT inlined. Open "
                "release_dir in Finder to drag into Play/App Store."
            ),
            input_schema=_schema(
                {
                    "label": _string(
                        "Filename (no slashes). Conventionally '01-home', "
                        "'02-feed', etc., one per store-listing slot."
                    ),
                    "thumbnail_long_edge": _int(
                        "Thumbnail dimension cap (default 256, min 64)."
                    ),
                    **serial_prop,
                },
                ["label"],
            ),
            build_params=_params_capture_release_screenshot,
            invoke=_bind(
                uc.capture_release_screenshot, _params_capture_release_screenshot
            ),
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
            name="write_vscode_launch_config",
            description=(
                "Write `.vscode/launch.json` for a Flutter project so F5 in "
                "VS Code mirrors the agent's debug session. Idempotent unless "
                "overwrite=true."
            ),
            input_schema=_schema(
                {
                    "project_path": _string("Flutter project root."),
                    "flavor": _string("Optional Flutter flavor."),
                    "target": _string("Entry-point Dart file (default lib/main.dart)."),
                    "debug_mode": _enum(
                        ["debug", "profile", "release"],
                        "Default mode reflected in the active configuration.",
                    ),
                    "overwrite": _bool("Replace an existing file if true."),
                },
                ["project_path"],
            ),
            build_params=_params_write_vscode_launch_config,
            invoke=_bind(
                uc.write_vscode_launch_config, _params_write_vscode_launch_config
            ),
        ),
        ToolDescriptor(
            name="setup_webdriveragent",
            description=(
                "Build WebDriverAgent for an iOS device (one-time per device). "
                "Clones the repo if needed, runs `xcodebuild build-for-testing`. "
                "Short-circuits if a previous successful build is recorded "
                "(unless skip_if_built=false)."
            ),
            input_schema=_schema(
                {
                    "udid": _string(""),
                    "wda_dir": _string("Existing WDA checkout (skip clone)."),
                    "repo_url": _string(""),
                    "scheme": _string("Default WebDriverAgentRunner."),
                    "skip_if_built": _bool("Default true; set false to force rebuild."),
                },
                ["udid"],
            ),
            build_params=_params_setup_wda,
            invoke=_bind(uc.setup_webdriveragent, _params_setup_wda),
        ),
        # ---- code quality ---------------------------------------------
        ToolDescriptor(
            name="dart_analyze",
            description=(
                "Run `dart analyze --format=json` and return structured issues "
                "(severity, code, message, file, line, column). Optional "
                "min_severity filter."
            ),
            input_schema=_schema(
                {
                    "project_path": _string(""),
                    "min_severity": _enum(["info", "warning", "error"]),
                },
                ["project_path"],
            ),
            build_params=_params_dart_analyze,
            invoke=_bind(uc.dart_analyze, _params_dart_analyze),
        ),
        ToolDescriptor(
            name="dart_format",
            description=(
                "Run `dart format` on a file or directory. dry_run=true reports "
                "what would change without rewriting."
            ),
            input_schema=_schema(
                {
                    "target_path": _string(""),
                    "dry_run": _bool("Default false."),
                },
                ["target_path"],
            ),
            build_params=_params_dart_format,
            invoke=_bind(uc.dart_format, _params_dart_format),
        ),
        ToolDescriptor(
            name="dart_fix",
            description=(
                "Run `dart fix`. apply=false (default) is a dry-run; apply=true "
                "modifies files. Returns count of fixes + files changed."
            ),
            input_schema=_schema(
                {
                    "project_path": _string(""),
                    "apply": _bool("Default false (dry-run)."),
                },
                ["project_path"],
            ),
            build_params=_params_dart_fix,
            invoke=_bind(uc.dart_fix, _params_dart_fix),
        ),
        ToolDescriptor(
            name="flutter_pub_get",
            description="Run `flutter pub get` to refresh dependencies.",
            input_schema=_schema(
                {"project_path": _string("")}, ["project_path"]
            ),
            build_params=_params_flutter_pub_get,
            invoke=_bind(uc.flutter_pub_get, _params_flutter_pub_get),
        ),
        ToolDescriptor(
            name="flutter_pub_outdated",
            description="Run `flutter pub outdated` to see stale dependencies.",
            input_schema=_schema(
                {"project_path": _string("")}, ["project_path"]
            ),
            build_params=_params_flutter_pub_outdated,
            invoke=_bind(uc.flutter_pub_outdated, _params_flutter_pub_outdated),
        ),
        ToolDescriptor(
            name="quality_gate",
            description=(
                "Composite check before claiming 'done': dart analyze + dart "
                "format check + flutter unit tests. Returns overall_ok=true only "
                "when zero analyzer errors, format-clean (if required), and "
                "passing tests."
            ),
            input_schema=_schema(
                {
                    "project_path": _string(""),
                    "require_format_clean": _bool("Default true."),
                    "run_unit_tests": _bool("Default true."),
                },
                ["project_path"],
            ),
            build_params=_params_quality_gate,
            invoke=_bind(uc.quality_gate, _params_quality_gate),
        ),
        ToolDescriptor(
            name="patch_apply_safe",
            description=(
                "Apply a unified diff to a git project; auto-rollback if "
                "quality_gate fails. Requires a clean working tree (or "
                "force=true). Leaves changes uncommitted for human review."
            ),
            input_schema=_schema(
                {
                    "project_path": _string("Git project root."),
                    "diff": _string("Unified diff content."),
                    "skip_gate": _bool("Skip quality_gate (default false)."),
                    "force": _bool("Apply even if working tree is dirty."),
                },
                ["project_path", "diff"],
            ),
            build_params=_params_patch_apply_safe,
            invoke=_bind(uc.patch_apply_safe, _params_patch_apply_safe),
        ),
        ToolDescriptor(
            name="narrate",
            description=(
                "Turn an MCP envelope into a one-line prose summary. "
                "Useful for small models that need to echo results back to "
                "the user without re-parsing JSON."
            ),
            input_schema=_schema(
                {
                    "envelope": {"type": "object", "description": "MCP envelope."},
                    "tool": _string("Optional tool name for richer phrasing."),
                },
                ["envelope"],
            ),
            build_params=_params_narrate,
            invoke=_bind(uc.narrate, _params_narrate),
        ),
        ToolDescriptor(
            name="scaffold_feature",
            description=(
                "Generate a Clean-Architecture skeleton (entity, failure, "
                "repo, use case, BLoC, page, tests) for a feature_name in "
                "snake_case. Idempotent unless overwrite=true."
            ),
            input_schema=_schema(
                {
                    "project_path": _string("Flutter project root."),
                    "feature_name": _string("snake_case feature id."),
                    "overwrite": _bool(""),
                },
                ["project_path", "feature_name"],
            ),
            build_params=_params_scaffold_feature,
            invoke=_bind(uc.scaffold_feature, _params_scaffold_feature),
        ),
        ToolDescriptor(
            name="run_quick_check",
            description=(
                "Fast health check: dart analyze + format check + git "
                "status. Skips unit tests; use quality_gate for the full bar."
            ),
            input_schema=_schema(
                {"project_path": _string("Flutter project root.")},
                ["project_path"],
            ),
            build_params=_params_run_quick_check,
            invoke=_bind(uc.run_quick_check, _params_run_quick_check),
        ),
        ToolDescriptor(
            name="grep_logs",
            description=(
                "Grep a saved log artifact for a regex with line context. "
                "Returns line numbers + before/after context for each match."
            ),
            input_schema=_schema(
                {
                    "path": _string("Path to log artifact."),
                    "pattern": _string("Regex."),
                    "context_lines": _int(""),
                    "max_matches": _int(""),
                },
                ["path", "pattern"],
            ),
            build_params=_params_grep_logs,
            invoke=_bind(uc.grep_logs, _params_grep_logs),
        ),
        ToolDescriptor(
            name="summarize_session",
            description=(
                "Boil the session trace down to a 3-line elevator pitch: "
                "headline, recent successes, recent errors."
            ),
            input_schema=_schema(
                {
                    "session_id": _string("Defaults to current."),
                    "top_facts": _int(""),
                }
            ),
            build_params=_params_summarize_session,
            invoke=_bind(uc.summarize_session, _params_summarize_session),
        ),
        ToolDescriptor(
            name="find_flutter_widget",
            description=(
                "Scan lib/ for widget classes whose name matches a regex. "
                "Returns file paths + line numbers."
            ),
            input_schema=_schema(
                {
                    "project_path": _string(""),
                    "name_pattern": _string("Regex on class name."),
                    "max_results": _int(""),
                },
                ["project_path", "name_pattern"],
            ),
            build_params=_params_find_flutter_widget,
            invoke=_bind(uc.find_flutter_widget, _params_find_flutter_widget),
        ),
        ToolDescriptor(
            name="recall",
            description=(
                "Retrieve top-k chunks matching a query (skill, docs, code, "
                "or trace). Use instead of loading the whole SKILL — saves "
                "context for 4B agents."
            ),
            input_schema=_schema(
                {
                    "query": _string("Natural-language query."),
                    "k": _int("Top-k chunks (default 3, max 20)."),
                    "scope": _enum(
                        ["skill", "docs", "code", "trace", "all"],
                        "Filter chunks by scope (default 'all').",
                    ),
                },
                ["query"],
            ),
            build_params=_params_recall,
            invoke=_bind(uc.recall, _params_recall),
        ),
        ToolDescriptor(
            name="recall_corrective",
            description=(
                "Recall + relevance grading + scope fallback. Use when the "
                "agent needs an answer it can trust; returns confidence "
                "and a diagnosis."
            ),
            input_schema=_schema(
                {
                    "query": _string("Natural-language query."),
                    "k": _int("Top-k chunks (default 3)."),
                    "scope": _enum(
                        ["skill", "docs", "code", "trace", "all"],
                        "Initial scope (default 'all').",
                    ),
                    "confidence_threshold": _number(
                        "Mean lexical-overlap floor (default 0.15)."
                    ),
                    "max_retries": _int(
                        "Scope-fallback retries (default 1, max 4)."
                    ),
                },
                ["query"],
            ),
            build_params=_params_recall_corrective,
            invoke=_bind(uc.recall_corrective, _params_recall_corrective),
        ),
        ToolDescriptor(
            name="index_project",
            description=(
                "Walk a project, chunk md/dart/py files, push into Qdrant. "
                "Idempotent on (collection, source). Run once per project, "
                "or on a watcher."
            ),
            input_schema=_schema(
                {
                    "project_path": _string("Project root."),
                    "collection": _string("Qdrant collection name."),
                    "include_globs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Glob patterns to include.",
                    },
                    "exclude_globs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Glob patterns to exclude.",
                    },
                },
                ["project_path"],
            ),
            build_params=_params_index_project,
            invoke=_bind(uc.index_project, _params_index_project),
        ),
        ToolDescriptor(
            name="promote_sequence",
            description=(
                "Tag a slice of the current session trace as a named, "
                "reusable skill. Skill names are snake_case, no spaces. "
                "Voyager-style skill library."
            ),
            input_schema=_schema(
                {
                    "name": _string("Skill identifier (snake_case)."),
                    "description": _string("Human-readable summary."),
                    "from_sequence": _int("Earliest trace seq to include."),
                    "to_sequence": _int("Latest trace seq to include."),
                    "only_ok": _bool("Only include ok=True steps (default true)."),
                },
                ["name", "description"],
            ),
            build_params=_params_promote_sequence,
            invoke=_bind(uc.promote_sequence, _params_promote_sequence),
        ),
        ToolDescriptor(
            name="list_skills",
            description=(
                "Return every named skill in the library, ordered by "
                "use count. Use to discover what the agent has learned."
            ),
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.list_skills, _params_no),
        ),
        ToolDescriptor(
            name="replay_skill",
            description=(
                "Re-execute a stored skill through the dispatcher. "
                "Records success/failure on the library so high-success "
                "skills get prioritised over time."
            ),
            input_schema=_schema(
                {
                    "name": _string("Skill name."),
                    "overrides": {
                        "type": "object",
                        "description": "Placeholder substitutions for $-prefixed args.",
                    },
                },
                ["name"],
            ),
            build_params=_params_replay_skill,
            invoke=_bind(uc.replay_skill, _params_replay_skill),
        ),
        # ---- AR / Vision (advanced) -----------------------------------
        ToolDescriptor(
            name="calibrate_camera",
            description=(
                "Calibrate camera intrinsics from chessboard images. Needs ≥3 "
                "images with a detected (cols x rows) inner-corner pattern. "
                "Returns fx/fy/cx/cy + distortion + reprojection error."
            ),
            input_schema=_schema(
                {
                    "image_paths": {"type": "array", "items": {"type": "string"}},
                    "board_cols": _int("Inner corner columns. Default 9."),
                    "board_rows": _int("Inner corner rows. Default 6."),
                    "square_size_m": _number("Square size in meters. Default 0.025."),
                },
                ["image_paths"],
            ),
            build_params=_params_calibrate_camera,
            invoke=_bind(uc.calibrate_camera, _params_calibrate_camera),
        ),
        ToolDescriptor(
            name="assert_pose_stable",
            description=(
                "Capture N pose samples of one ArUco marker and assert "
                "frame-to-frame stability under translation + rotation thresholds. "
                "Use to filter single-frame outliers before AR placement assertions."
            ),
            input_schema=_schema(
                {
                    "marker_id": _int(""),
                    "samples": _int("Default 10."),
                    "sample_interval_s": _number("Default 0.2."),
                    "max_translation_m": _number("Default 0.005."),
                    "max_rotation_deg": _number("Default 2.0."),
                    "marker_size_m": _number("Default 0.05."),
                    "serial": _string("Defaults to selected device."),
                },
                ["marker_id"],
            ),
            build_params=_params_assert_pose_stable,
            invoke=_bind(uc.assert_pose_stable, _params_assert_pose_stable),
        ),
        ToolDescriptor(
            name="wait_for_ar_session_ready",
            description=(
                "Tail device logs until ARKit/ARCore reports normal tracking. "
                "Use as a gate before AR placement assertions."
            ),
            input_schema=_schema(
                {
                    "timeout_s": _number("Default 30."),
                    "serial": _string("Defaults to selected device."),
                }
            ),
            build_params=_params_wait_for_ar_session_ready,
            invoke=_bind(uc.wait_for_ar_session_ready, _params_wait_for_ar_session_ready),
        ),
        ToolDescriptor(
            name="vm_list_isolates",
            description=(
                "List Dart isolates in the active debug session via the VM "
                "service WebSocket. Requires the [debug] extra (websockets)."
            ),
            input_schema=_schema({"session_id": _string("")}),
            build_params=_params_vm_list_isolates,
            invoke=_bind(uc.vm_list_isolates, _params_vm_list_isolates),
        ),
        ToolDescriptor(
            name="vm_evaluate",
            description=(
                "Evaluate a Dart expression at a frame in an isolate of the "
                "active debug session. Defaults to the first runnable isolate "
                "and frame 0. Requires the [debug] extra."
            ),
            input_schema=_schema(
                {
                    "expression": _string("Dart expression."),
                    "isolate_id": _string("Optional; defaults to first runnable."),
                    "frame_index": _int("Default 0."),
                    "session_id": _string(""),
                },
                ["expression"],
            ),
            build_params=_params_vm_evaluate,
            invoke=_bind(uc.vm_evaluate, _params_vm_evaluate),
        ),
        ToolDescriptor(
            name="save_golden_image",
            description=(
                "Capture a screenshot and save it under "
                "<project>/tests/fixtures/golden/<label>.png (or under the "
                "session artifacts if no project_path). Bootstraps goldens "
                "for compare_screenshot regression tests."
            ),
            input_schema=_schema(
                {
                    "label": _string(""),
                    "project_path": _string("Optional; defaults to artifacts dir."),
                    "serial": _string("Defaults to selected device."),
                },
                ["label"],
            ),
            build_params=_params_save_golden_image,
            invoke=_bind(uc.save_golden_image, _params_save_golden_image),
        ),
        ToolDescriptor(
            name="new_session",
            description="Create a new artifacts session directory.",
            input_schema=_schema({"label": _string("")}),
            build_params=_params_new_session,
            invoke=_bind(uc.new_session, _params_new_session),
        ),
        ToolDescriptor(
            name="fetch_artifact",
            description=(
                "Read a previously emitted artifact by path. Returns text "
                "content or, for binary files, metadata + sha256. Use after "
                "a tool returned data_truncated=true."
            ),
            input_schema=_schema(
                {
                    "path": _string("Absolute path returned by an earlier tool."),
                    "max_bytes": _int("Cap on text content (default 64000)."),
                    "encoding": _string("Text encoding (default utf-8)."),
                },
                ["path"],
            ),
            build_params=_params_fetch_artifact,
            invoke=_bind(uc.fetch_artifact, _params_fetch_artifact),
        ),
        ToolDescriptor(
            name="get_artifacts_dir",
            description="Return the current artifacts directory.",
            input_schema=_schema({}),
            build_params=_params_no,
            invoke=_bind(uc.get_artifacts_dir, _params_no),
        ),
    ]


def _maybe_coerce_args(
    args: JsonDict | None, schema: JsonDict | None
) -> JsonDict:
    """Wrap argument_coercion.coerce_args with safe defaults."""
    from .argument_coercion import coerce_args

    return coerce_args(args or {}, schema or {})


def _example_for(descriptor: ToolDescriptor) -> dict:
    from .argument_coercion import corrected_example

    return corrected_example(descriptor.input_schema or {})


def _missing_arg_envelope(descriptor: ToolDescriptor, missing_key: str) -> JsonDict:
    """Build an InvalidArgumentFailure envelope with a corrected_example so
    a small LLM can copy a known-good shape into its next call."""
    return {
        "ok": False,
        "error": {
            "code": "InvalidArgumentFailure",
            "message": f"Missing required argument: {missing_key}",
            "next_action": "fix_arguments",
            "details": {
                "missing_key": missing_key,
                "tool_name": descriptor.name,
                "corrected_example": _example_for(descriptor),
            },
        },
    }


class ToolDispatcher:
    """Generic dispatcher: name → ToolDescriptor → uniform JSON envelope.

    Cross-cutting concerns (rate limit, image cap, trace recording,
    auto-narrate, Patrol guard, output truncation) live in
    `presentation/middleware.py` as a chain. The dispatcher itself is a
    thin orchestrator: walk pre-dispatch hooks, invoke the use case,
    walk post-dispatch hooks in reverse order. Each middleware is
    independently unit-testable.

    Pass `middlewares=` for full control; if omitted,
    `build_default_chain` provides the canonical order.
    """

    def __init__(
        self,
        descriptors: list[ToolDescriptor],
        trace_repo=None,
        truncate_outputs: bool = True,
        rate_limiter=None,
        auto_narrate_every: int = 0,
        middlewares: list | None = None,
    ) -> None:
        self._by_name = {d.name: d for d in descriptors}
        self._trace_repo = trace_repo

        if middlewares is None:
            if rate_limiter is None:
                from .rate_limiter import RateLimiter

                rate_limiter = RateLimiter()
            from .middleware import build_default_chain

            middlewares = build_default_chain(
                rate_limiter=rate_limiter,
                trace_repo=trace_repo,
                recorder=self._record,
                truncate_outputs=truncate_outputs,
                auto_narrate_every=auto_narrate_every,
            )
        self._middlewares = middlewares

    @property
    def descriptors(self) -> list[ToolDescriptor]:
        return list(self._by_name.values())

    @property
    def middlewares(self) -> list:
        """Exposed read-only so tests + tooling can introspect / replace."""
        return list(self._middlewares)

    def has(self, name: str) -> bool:
        return name in self._by_name

    async def dispatch(self, name: str, args: JsonDict | None) -> JsonDict:
        # 1. Pre-dispatch hooks in order. Any may short-circuit.
        for idx, mw in enumerate(self._middlewares):
            guard = await mw.pre_dispatch(name, args)
            if guard is not None:
                envelope = guard
                # Short-circuit still walks the post-dispatch hooks of
                # the middlewares we already pre-traversed, in reverse,
                # so trace + seatbelt see the rejection envelope too.
                for prev in reversed(self._middlewares[: idx + 1]):
                    envelope = await prev.post_dispatch(name, args, envelope)
                return envelope

        # 2. Invoke the use case.
        envelope = await self._dispatch_unrecorded(name, args)

        # 3. Post-dispatch in reverse order (LIFO so wrappers compose).
        for mw in reversed(self._middlewares):
            envelope = await mw.post_dispatch(name, args, envelope)
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
                    "details": {
                        "hint": "call describe_capabilities to see all available tools",
                    },
                },
            }
        # Small-LLM resilience: coerce loose argument types BEFORE invoking,
        # so '"true"' / '"5"' / single-string-where-array-expected don't fail.
        coerced_args = _maybe_coerce_args(args, descriptor.input_schema)
        try:
            result = await descriptor.invoke(coerced_args)
        except KeyError as e:
            return _missing_arg_envelope(descriptor, str(e.args[0]))
        except (TypeError, ValueError) as e:
            return {
                "ok": False,
                "error": {
                    "code": "InvalidArgumentFailure",
                    "message": str(e),
                    "next_action": "fix_arguments",
                    "details": {"corrected_example": _example_for(descriptor)},
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
