"""Per-tool param builders: arguments dict → typed Params dataclass.

Keep these dumb. They do three things only:
1. Pull values out of the args dict (`args["x"]` for required, `.get()` for
   optional).
2. Coerce primitive types (`int(...)`, `float(...)`, `Path(...).expanduser()`).
3. Map enum strings to typed Enums (`BuildMode(...)`, `Platform(...)`, ...).

Validation lives at the schema layer (`input_schema` on each descriptor) and
at the use-case boundary. If you find yourself adding business logic here,
move it into the use case instead.

These were originally inline in `tool_registry.py` — extracted so the
registry file stops being a 2900-LOC god-module.
"""

from __future__ import annotations

from pathlib import Path

from ...domain.entities import AnalyzerSeverity as _AnalyzerSeverity
from ...domain.entities import BuildMode, LogLevel, Platform
from ...domain.entities import IdeKind as _IdeKind
from ...domain.usecases.artifact_retention import PruneOriginalsParams
from ...domain.usecases.artifacts import FetchArtifactParams, NewSessionParams
from ...domain.usecases.build_install import (
    BuildAppParams,
    InstallAppParams,
    UninstallAppParams,
)
from ...domain.usecases.code_quality import (
    DartAnalyzeParams,
    DartFixParams,
    DartFormatParams,
    FlutterPubGetParams,
    FlutterPubOutdatedParams,
    QualityGateParams,
)
from ...domain.usecases.crag import CorrectiveRecallParams
from ...domain.usecases.debug_inspect import (
    VmEvaluateParams,
    VmListIsolatesParams,
)
from ...domain.usecases.dev_session import (
    AttachDebugSessionParams,
    CallServiceExtensionParams,
    DumpWidgetTreeParams,
    ReadDebugLogParams,
    RestartDebugSessionParams,
    StartDebugSessionParams,
    StopDebugSessionParams,
    TailDebugLogParams,
    ToggleInspectorParams,
)
from ...domain.usecases.devices import (
    ForceReleaseLockParams,
    ReleaseDeviceParams,
    SelectDeviceParams,
)
from ...domain.usecases.discovery import (
    DescribeCapabilitiesParams,
    DescribeToolParams,
    SessionSummaryParams,
    ToolUsageReportParams,
)
from ...domain.usecases.ide import (
    CloseIdeWindowParams,
    FocusIdeWindowParams,
    IsIdeAvailableParams,
    OpenProjectInIdeParams,
    WriteVscodeLaunchConfigParams,
)
from ...domain.usecases.lifecycle import (
    ClearAppDataParams,
    GrantPermissionParams,
    LaunchAppParams,
    StopAppParams,
)
from ...domain.usecases.narrate import NarrateParams
from ...domain.usecases.notify_webhook import NotifyWebhookParams
from ...domain.usecases.observation import (
    ReadLogsParams,
    StartRecordingParams,
    StopRecordingParams,
    TailLogsParams,
    TakeScreenshotParams,
)
from ...domain.usecases.ocr import OcrScreenshotParams
from ...domain.usecases.patch_safe import PatchApplySafeParams
from ...domain.usecases.patrol import (
    ListPatrolTestsParams,
    RunPatrolSuiteParams,
    RunPatrolTestParams,
)
from ...domain.usecases.plan import (
    RunTestPlanParams,
    ValidateTestPlanParams,
)
from ...domain.usecases.preparation import PrepareForTestParams
from ...domain.usecases.productivity import (
    FindFlutterWidgetParams,
    GrepLogsParams,
    RunQuickCheckParams,
    ScaffoldFeatureParams,
    SummarizeSessionParams,
)
from ...domain.usecases.projects import InspectProjectParams
from ...domain.usecases.recall import IndexProjectParams, RecallParams
from ...domain.usecases.release_screenshot import CaptureReleaseScreenshotParams
from ...domain.usecases.set_agent_profile import SetAgentProfileParams
from ...domain.usecases.skill_library import (
    PromoteSequenceParams,
    ReplaySkillParams,
)
from ...domain.usecases.testing import (
    RunIntegrationTestsParams,
    RunUnitTestsParams,
)
from ...domain.usecases.ui_graph import ExtractUiGraphParams
from ...domain.usecases.ui_input import (
    PressKeyParams,
    SwipeParams,
    TapParams,
    TapTextParams,
    TypeTextParams,
)
from ...domain.usecases.ui_query import (
    AssertVisibleParams,
    DumpUiParams,
    FindElementParams,
    WaitForElementParams,
)
from ...domain.usecases.ui_verify import (
    AssertNoErrorsSinceParams,
    TapAndVerifyParams,
)
from ...domain.usecases.virtual_devices import (
    BootSimulatorParams,
    ListSimulatorsParams,
    StartEmulatorParams,
    StopVirtualDeviceParams,
)
from ...domain.usecases.vision import (
    CompareScreenshotParams,
    DetectMarkersParams,
    InferCameraPoseParams,
    WaitForMarkerParams,
)
from ...domain.usecases.vision_advanced import (
    AssertPoseStableParams,
    CalibrateCameraParams,
    SaveGoldenImageParams,
    WaitForArSessionReadyParams,
)
from ...domain.usecases.wda_setup import SetupWebDriverAgentParams
from ._shared import JsonDict, _path

# ---- devices ------------------------------------------------------------


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


# ---- apps ---------------------------------------------------------------


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


# ---- UI input / verification -------------------------------------------


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


def _params_tap_and_verify(args: JsonDict) -> TapAndVerifyParams:
    return TapAndVerifyParams(
        text=args["text"],
        expect_text=args.get("expect_text"),
        expect_resource_id=args.get("expect_resource_id"),
        timeout_s=float(args.get("timeout_s", 5.0)),
        exact=bool(args.get("exact", False)),
        serial=args.get("serial"),
    )


def _params_extract_ui_graph(args: JsonDict) -> ExtractUiGraphParams:
    return ExtractUiGraphParams(
        serial=args.get("serial"),
        max_nodes=int(args.get("max_nodes", 200)),
    )


def _params_ocr_screenshot(args: JsonDict) -> OcrScreenshotParams:
    return OcrScreenshotParams(
        path=Path(args["path"]).expanduser(),
        languages=tuple(args.get("languages") or ("eng",)),
        min_confidence=float(args.get("min_confidence", 0.0)),
    )


def _params_assert_no_errors(args: JsonDict) -> AssertNoErrorsSinceParams:
    return AssertNoErrorsSinceParams(
        since_s=int(args.get("since_s", 30)),
        tag=args.get("tag"),
        serial=args.get("serial"),
    )


# ---- screenshots + recordings + logs -----------------------------------


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


# ---- tests -------------------------------------------------------------


def _params_run_unit(args: JsonDict) -> RunUnitTestsParams:
    return RunUnitTestsParams(project_path=Path(args["project_path"]).expanduser())


def _params_run_integration(args: JsonDict) -> RunIntegrationTestsParams:
    return RunIntegrationTestsParams(
        project_path=Path(args["project_path"]).expanduser(),
        test_path=args.get("test_path", "integration_test/"),
        serial=args.get("serial"),
    )


# ---- sessions + artifacts ----------------------------------------------


def _params_new_session(args: JsonDict) -> NewSessionParams:
    return NewSessionParams(label=args.get("label"))


def _params_fetch_artifact(args: JsonDict) -> FetchArtifactParams:
    return FetchArtifactParams(
        path=Path(args["path"]).expanduser(),
        max_bytes=int(args.get("max_bytes", 64_000)),
        encoding=args.get("encoding", "utf-8"),
    )


# ---- productivity ------------------------------------------------------


def _params_scaffold_feature(args: JsonDict) -> ScaffoldFeatureParams:
    return ScaffoldFeatureParams(
        project_path=Path(args["project_path"]).expanduser(),
        feature_name=args["feature_name"],
        overwrite=bool(args.get("overwrite", False)),
    )


def _params_run_quick_check(args: JsonDict) -> RunQuickCheckParams:
    return RunQuickCheckParams(
        project_path=Path(args["project_path"]).expanduser()
    )


def _params_grep_logs(args: JsonDict) -> GrepLogsParams:
    return GrepLogsParams(
        path=Path(args["path"]).expanduser(),
        pattern=args["pattern"],
        context_lines=int(args.get("context_lines", 2)),
        max_matches=int(args.get("max_matches", 50)),
    )


def _params_summarize_session(args: JsonDict) -> SummarizeSessionParams:
    return SummarizeSessionParams(
        session_id=args.get("session_id"),
        top_facts=int(args.get("top_facts", 5)),
    )


def _params_find_flutter_widget(args: JsonDict) -> FindFlutterWidgetParams:
    return FindFlutterWidgetParams(
        project_path=Path(args["project_path"]).expanduser(),
        name_pattern=args.get("name_pattern", ".*"),
        max_results=int(args.get("max_results", 50)),
    )


# ---- RAG + skills ------------------------------------------------------


def _params_recall(args: JsonDict) -> RecallParams:
    return RecallParams(
        query=args["query"],
        k=int(args.get("k", 3)),
        scope=args.get("scope", "all"),
    )


def _params_capture_release_screenshot(
    args: JsonDict,
) -> CaptureReleaseScreenshotParams:
    return CaptureReleaseScreenshotParams(
        label=args["label"],
        serial=args.get("serial"),
        thumbnail_long_edge=int(args.get("thumbnail_long_edge", 256)),
    )


def _params_recall_corrective(args: JsonDict) -> CorrectiveRecallParams:
    return CorrectiveRecallParams(
        query=args["query"],
        k=int(args.get("k", 3)),
        scope=args.get("scope", "all"),
        confidence_threshold=float(args.get("confidence_threshold", 0.15)),
        max_retries=int(args.get("max_retries", 1)),
    )


def _params_promote_sequence(args: JsonDict) -> PromoteSequenceParams:
    return PromoteSequenceParams(
        name=args["name"],
        description=args.get("description", ""),
        from_sequence=args.get("from_sequence"),
        to_sequence=args.get("to_sequence"),
        only_ok=bool(args.get("only_ok", True)),
    )


def _params_replay_skill(args: JsonDict) -> ReplaySkillParams:
    return ReplaySkillParams(
        name=args["name"],
        overrides=args.get("overrides"),
    )


def _params_index_project(args: JsonDict) -> IndexProjectParams:
    return IndexProjectParams(
        project_path=Path(args["project_path"]).expanduser(),
        collection=args.get("collection", "phone-controll-default"),
        include_globs=tuple(args.get("include_globs") or ("**/*.md", "**/*.dart", "**/*.py")),
        exclude_globs=tuple(
            args.get("exclude_globs")
            or (
                "**/.git/**",
                "**/build/**",
                "**/.dart_tool/**",
                "**/node_modules/**",
                "**/.venv/**",
            )
        ),
    )


# ---- narrate + patch + projects ----------------------------------------


def _params_narrate(args: JsonDict) -> NarrateParams:
    return NarrateParams(
        envelope=dict(args.get("envelope") or {}),
        tool=args.get("tool"),
    )


def _params_patch_apply_safe(args: JsonDict) -> PatchApplySafeParams:
    return PatchApplySafeParams(
        project_path=Path(args["project_path"]).expanduser(),
        diff=args["diff"],
        skip_gate=bool(args.get("skip_gate", False)),
        force=bool(args.get("force", False)),
    )


def _params_inspect_project(args: JsonDict) -> InspectProjectParams:
    return InspectProjectParams(project_path=Path(args["project_path"]).expanduser())


# ---- patrol + plans ----------------------------------------------------


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


def _params_run_patrol_suite(args: JsonDict) -> RunPatrolSuiteParams:
    return RunPatrolSuiteParams(
        project_path=Path(args["project_path"]).expanduser(),
        test_dir=Path(args.get("test_dir", "integration_test")),
        serial=args.get("serial"),
        flavor=args.get("flavor"),
        build_mode=BuildMode(args.get("build_mode", "debug")),
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


# ---- discovery + profile + meta ----------------------------------------


def _params_describe_capabilities(args: JsonDict) -> DescribeCapabilitiesParams:
    return DescribeCapabilitiesParams(level=args.get("level", "expert"))


def _params_describe_tool(args: JsonDict) -> DescribeToolParams:
    return DescribeToolParams(name=args["name"])


def _params_session_summary(args: JsonDict) -> SessionSummaryParams:
    return SessionSummaryParams(session_id=args.get("session_id"))


def _params_set_agent_profile(args: JsonDict) -> SetAgentProfileParams:
    return SetAgentProfileParams(name=args["name"])


def _params_notify_webhook(args: JsonDict) -> NotifyWebhookParams:
    return NotifyWebhookParams(
        url=args["url"],
        event=args["event"],
        payload=dict(args.get("payload") or {}),
        auth_bearer=args.get("auth_bearer"),
        auth_header_name=args.get("auth_header_name"),
        auth_header_value=args.get("auth_header_value"),
        timeout_s=float(args.get("timeout_s", 10.0)),
    )


def _params_prune_originals(args: JsonDict) -> PruneOriginalsParams:
    return PruneOriginalsParams(
        older_than_days=(
            int(args["older_than_days"]) if "older_than_days" in args else None
        ),
        dry_run=bool(args.get("dry_run", False)),
    )


def _params_tool_usage_report(args: JsonDict) -> ToolUsageReportParams:
    return ToolUsageReportParams(
        session_id=args.get("session_id"),
        top_n=int(args.get("top_n", 10)),
    )


def _params_prepare_for_test(args: JsonDict) -> PrepareForTestParams:
    return PrepareForTestParams(
        package_id=args["package_id"],
        serial=args.get("serial"),
        skip_clear=bool(args.get("skip_clear", False)),
        capture_evidence=bool(args.get("capture_evidence", True)),
    )


# ---- virtual devices ---------------------------------------------------


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


# ---- dev-session -------------------------------------------------------


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


# ---- IDE ---------------------------------------------------------------


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


def _params_write_vscode_launch_config(
    args: JsonDict,
) -> WriteVscodeLaunchConfigParams:
    return WriteVscodeLaunchConfigParams(
        project_path=Path(args["project_path"]).expanduser(),
        flavor=args.get("flavor"),
        target=args.get("target", "lib/main.dart"),
        debug_mode=args.get("debug_mode", "debug"),
        overwrite=bool(args.get("overwrite", False)),
    )


# ---- VM debug inspect --------------------------------------------------


def _params_vm_list_isolates(args: JsonDict) -> VmListIsolatesParams:
    return VmListIsolatesParams(session_id=args.get("session_id"))


def _params_vm_evaluate(args: JsonDict) -> VmEvaluateParams:
    return VmEvaluateParams(
        expression=args["expression"],
        isolate_id=args.get("isolate_id"),
        frame_index=int(args.get("frame_index", 0)),
        session_id=args.get("session_id"),
    )


# ---- AR / vision -------------------------------------------------------


def _params_calibrate_camera(args: JsonDict) -> CalibrateCameraParams:
    return CalibrateCameraParams(
        image_paths=[Path(p).expanduser() for p in (args.get("image_paths") or [])],
        board_cols=int(args.get("board_cols", 9)),
        board_rows=int(args.get("board_rows", 6)),
        square_size_m=float(args.get("square_size_m", 0.025)),
    )


def _params_assert_pose_stable(args: JsonDict) -> AssertPoseStableParams:
    return AssertPoseStableParams(
        marker_id=int(args["marker_id"]),
        samples=int(args.get("samples", 10)),
        sample_interval_s=float(args.get("sample_interval_s", 0.2)),
        max_translation_m=float(args.get("max_translation_m", 0.005)),
        max_rotation_deg=float(args.get("max_rotation_deg", 2.0)),
        marker_size_m=float(args.get("marker_size_m", 0.05)),
        serial=args.get("serial"),
    )


def _params_wait_for_ar_session_ready(args: JsonDict) -> WaitForArSessionReadyParams:
    return WaitForArSessionReadyParams(
        timeout_s=float(args.get("timeout_s", 30.0)),
        serial=args.get("serial"),
    )


def _params_save_golden_image(args: JsonDict) -> SaveGoldenImageParams:
    return SaveGoldenImageParams(
        label=args["label"],
        project_path=Path(args["project_path"]).expanduser()
        if args.get("project_path")
        else None,
        serial=args.get("serial"),
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


# ---- code quality ------------------------------------------------------


def _params_dart_analyze(args: JsonDict) -> DartAnalyzeParams:
    sev = args.get("min_severity")
    return DartAnalyzeParams(
        project_path=Path(args["project_path"]).expanduser(),
        min_severity=_AnalyzerSeverity(sev) if sev else None,
    )


def _params_dart_format(args: JsonDict) -> DartFormatParams:
    return DartFormatParams(
        target_path=Path(args["target_path"]).expanduser(),
        dry_run=bool(args.get("dry_run", False)),
    )


def _params_dart_fix(args: JsonDict) -> DartFixParams:
    return DartFixParams(
        project_path=Path(args["project_path"]).expanduser(),
        apply=bool(args.get("apply", False)),
    )


def _params_flutter_pub_get(args: JsonDict) -> FlutterPubGetParams:
    return FlutterPubGetParams(
        project_path=Path(args["project_path"]).expanduser()
    )


def _params_flutter_pub_outdated(args: JsonDict) -> FlutterPubOutdatedParams:
    return FlutterPubOutdatedParams(
        project_path=Path(args["project_path"]).expanduser()
    )


def _params_quality_gate(args: JsonDict) -> QualityGateParams:
    return QualityGateParams(
        project_path=Path(args["project_path"]).expanduser(),
        require_format_clean=bool(args.get("require_format_clean", True)),
        run_unit_tests=bool(args.get("run_unit_tests", True)),
    )


def _params_setup_wda(args: JsonDict) -> SetupWebDriverAgentParams:
    return SetupWebDriverAgentParams(
        udid=args["udid"],
        wda_dir=Path(args["wda_dir"]).expanduser() if args.get("wda_dir") else None,
        repo_url=args.get("repo_url", "https://github.com/appium/WebDriverAgent.git"),
        scheme=args.get("scheme", "WebDriverAgentRunner"),
        skip_if_built=bool(args.get("skip_if_built", True)),
    )
