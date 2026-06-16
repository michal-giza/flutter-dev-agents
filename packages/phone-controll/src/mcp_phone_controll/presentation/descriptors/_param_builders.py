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
from ...domain.usecases.app_size import AnalyzeAppSizeParams
from ...domain.usecases.artifact_retention import (
    CompressPngParams,
    PruneOriginalsParams,
)
from ...domain.usecases.artifacts import FetchArtifactParams, NewSessionParams
from ...domain.usecases.audit_accessibility import AuditAccessibilityParams
from ...domain.usecases.audit_code_seniority import (
    AuditCodeSeniorityParams,
)
from ...domain.usecases.audit_dependencies import (
    AuditDependenciesParams,
)
from ...domain.usecases.audit_localization import (
    AuditLocalizationParams,
)
from ...domain.usecases.audit_maestro_flow import (
    AuditMaestroFlowParams,
)
from ...domain.usecases.audit_performance import (
    AuditPerformanceParams,
)
from ...domain.usecases.audit_release_readiness import (
    AuditReleaseReadinessParams,
)
from ...domain.usecases.audit_security import (
    AuditSecurityParams,
)
from ...domain.usecases.audit_test_quality import (
    AuditTestQualityParams,
)
from ...domain.usecases.audit_web_app import (
    AuditWebAppParams,
)
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
from ...domain.usecases.deep_link import TestDeepLinkParams
from ...domain.usecases.design_test_plan import (
    DesignTestPlanParams,
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
from ...domain.usecases.estimate_tokens import EstimateTokensParams
from ...domain.usecases.frame_profile import (
    StartFrameProfileParams,
    StopFrameProfileParams,
)
from ...domain.usecases.ide import (
    CloseIdeWindowParams,
    FocusIdeWindowParams,
    IsIdeAvailableParams,
    OpenProjectInIdeParams,
    WriteVscodeLaunchConfigParams,
)
from ...domain.usecases.ingest_frame_timeline import (
    IngestFrameTimelineParams,
)
from ...domain.usecases.ingest_har import (
    IngestHarParams,
)
from ...domain.usecases.ingest_lighthouse_report import (
    IngestLighthouseReportParams,
)
from ...domain.usecases.ingest_maestro_report import (
    IngestMaestroReportParams,
)
from ...domain.usecases.inspect_image_safety import InspectImageSafetyParams
from ...domain.usecases.lifecycle import (
    ClearAppDataParams,
    GrantPermissionParams,
    LaunchAppParams,
    StopAppParams,
)
from ...domain.usecases.memory_inspect import (
    AllocationProfileParams,
    DetectUndisposedControllersParams,
    FindRetainingPathParams,
    MemorySummaryParams,
    TakeHeapSnapshotParams,
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
    ListMissingWidgetKeysParams,
    RunQuickCheckParams,
    ScaffoldFeatureParams,
    SummarizeSessionParams,
)
from ...domain.usecases.projects import InspectProjectParams
from ...domain.usecases.propose_test_scenarios import (
    ProposeTestScenariosParams,
)
from ...domain.usecases.recall import IndexProjectParams, RecallParams
from ...domain.usecases.recommend_test_path import (
    RecommendTestPathParams,
)
from ...domain.usecases.release_screenshot import CaptureReleaseScreenshotParams
from ...domain.usecases.run_lighthouse import RunLighthouseParams
from ...domain.usecases.set_agent_profile import SetAgentProfileParams
from ...domain.usecases.skill_library import (
    PromoteSequenceParams,
    ReplaySkillParams,
)
from ...domain.usecases.testing import (
    RunIntegrationTestsParams,
    RunUnitTestsParams,
)
from ...domain.usecases.ui_automation_pause import (
    PauseUiAutomationParams,
    ResumeUiAutomationParams,
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
from ...domain.usecases.wda_setup import (
    SetupWebDriverAgentParams,
    StartWdaOnSimulatorParams,
)
from ...domain.usecases.widget_testing import (
    ListWidgetTestsParams,
    RunWidgetTestParams,
    TestCoverageReportParams,
    UpdateGoldensParams,
)
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
    return RunUnitTestsParams(
        project_path=Path(args["project_path"]).expanduser(),
        platform=args.get("platform", "auto"),
    )


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


def _params_list_missing_widget_keys(
    args: JsonDict,
) -> ListMissingWidgetKeysParams:
    target = args.get("target_widgets")
    return ListMissingWidgetKeysParams(
        project_path=Path(args["project_path"]).expanduser(),
        target_widgets=tuple(target) if target else (
            "ElevatedButton",
            "TextButton",
            "OutlinedButton",
            "IconButton",
            "FilledButton",
            "FloatingActionButton",
            "GestureDetector",
            "InkWell",
            "Switch",
            "Checkbox",
        ),
        max_results=int(args.get("max_results", 200)),
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


def _params_compress_png(args: JsonDict) -> CompressPngParams:
    max_dim = args.get("max_dim")
    return CompressPngParams(
        path=Path(args["path"]).expanduser(),
        max_dim=int(max_dim) if max_dim is not None else None,
    )


def _params_inspect_image_safety(args: JsonDict) -> InspectImageSafetyParams:
    return InspectImageSafetyParams(path=Path(args["path"]).expanduser())


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


# ---- v0.3.0 memory introspection ---------------------------------------


def _params_memory_summary(args: JsonDict) -> MemorySummaryParams:
    return MemorySummaryParams(session_id=args.get("session_id"))


def _params_allocation_profile(args: JsonDict) -> AllocationProfileParams:
    return AllocationProfileParams(
        isolate_id=args.get("isolate_id"),
        session_id=args.get("session_id"),
        reset_accumulator=bool(args.get("reset_accumulator", False)),
        top_n=int(args.get("top_n", 20)),
    )


def _params_detect_undisposed_controllers(
    args: JsonDict,
) -> DetectUndisposedControllersParams:
    return DetectUndisposedControllersParams(
        isolate_id=args.get("isolate_id"),
        session_id=args.get("session_id"),
        extra_classes=tuple(args.get("extra_classes") or ()),
    )


def _params_find_retaining_path(
    args: JsonDict,
) -> FindRetainingPathParams:
    return FindRetainingPathParams(
        class_name=args["class_name"],
        isolate_id=args.get("isolate_id"),
        session_id=args.get("session_id"),
        max_depth=int(args.get("max_depth", 30)),
    )


def _params_take_heap_snapshot(
    args: JsonDict,
) -> TakeHeapSnapshotParams:
    return TakeHeapSnapshotParams(
        isolate_id=args.get("isolate_id"),
        session_id=args.get("session_id"),
        label=args.get("label"),
    )


# ---- v0.3.0 app size analyzer ------------------------------------------


def _params_analyze_app_size(args: JsonDict) -> AnalyzeAppSizeParams:
    baseline = args.get("baseline_json_path")
    return AnalyzeAppSizeParams(
        project_path=Path(args["project_path"]).expanduser(),
        platform=args.get("platform", "apk"),
        mode=args.get("mode", "release"),
        flavor=args.get("flavor"),
        top_n=int(args.get("top_n", 15)),
        baseline_json_path=Path(baseline).expanduser() if baseline else None,
    )


# ---- v0.3.0 widget testing ---------------------------------------------


def _params_run_widget_test(args: JsonDict) -> RunWidgetTestParams:
    return RunWidgetTestParams(
        project_path=Path(args["project_path"]).expanduser(),
        test_path=args.get("test_path"),
        name_pattern=args.get("name_pattern"),
        plain_name=bool(args.get("plain_name", False)),
        tags=args.get("tags"),
        coverage=bool(args.get("coverage", False)),
        update_goldens=bool(args.get("update_goldens", False)),
        platform=args.get("platform", "auto"),
    )


def _params_list_widget_tests(args: JsonDict) -> ListWidgetTestsParams:
    return ListWidgetTestsParams(
        project_path=Path(args["project_path"]).expanduser(),
        test_root=args.get("test_root", "test"),
    )


def _params_update_goldens(args: JsonDict) -> UpdateGoldensParams:
    return UpdateGoldensParams(
        project_path=Path(args["project_path"]).expanduser(),
        test_path=args.get("test_path"),
        name_pattern=args.get("name_pattern"),
        plain_name=bool(args.get("plain_name", False)),
        tags=args.get("tags"),
    )


def _params_test_coverage_report(args: JsonDict) -> TestCoverageReportParams:
    fail_under = args.get("fail_under")
    return TestCoverageReportParams(
        project_path=Path(args["project_path"]).expanduser(),
        test_path=args.get("test_path"),
        coverage_filter_prefix=args.get("coverage_filter_prefix"),
        fail_under=float(fail_under) if fail_under is not None else None,
    )


# ---- v0.3.0 phase 3 — frame profiling ---------------------------------


def _params_start_frame_profile(args: JsonDict) -> StartFrameProfileParams:
    return StartFrameProfileParams(session_id=args.get("session_id"))


def _params_stop_frame_profile(args: JsonDict) -> StopFrameProfileParams:
    return StopFrameProfileParams(
        session_id=args.get("session_id"),
        target_fps=int(args.get("target_fps", 60)),
        tolerance_pct=float(args.get("tolerance_pct", 0.10)),
    )


# ---- v0.3.0 phase 4 — test scenario designer ---------------------------


def _params_propose_test_scenarios(
    args: JsonDict,
) -> ProposeTestScenariosParams:
    return ProposeTestScenariosParams(
        project_path=Path(args["project_path"]).expanduser(),
        app_description=args.get("app_description"),
        focus_areas=tuple(args.get("focus_areas") or ()),
        top_n=int(args.get("top_n", 25)),
    )


# ---- v0.3.0 phase 5 — deep link + accessibility audit ------------------


def _params_test_deep_link(args: JsonDict) -> TestDeepLinkParams:
    return TestDeepLinkParams(
        uri=args["uri"],
        expect_screen_text=args.get("expect_screen_text"),
        serial=args.get("serial"),
        cold_start=bool(args.get("cold_start", False)),
        timeout_s=float(args.get("timeout_s", 15.0)),
    )


# ---- v0.3.0 phase 8.5 — pause / resume openatx uiautomator2 helper ----


def _params_pause_ui_automation(args: JsonDict) -> PauseUiAutomationParams:
    return PauseUiAutomationParams(serial=args.get("serial"))


def _params_resume_ui_automation(args: JsonDict) -> ResumeUiAutomationParams:
    return ResumeUiAutomationParams(
        serial=args.get("serial"),
        settle_ms=int(args.get("settle_ms", 800)),
    )


def _params_audit_accessibility(args: JsonDict) -> AuditAccessibilityParams:
    return AuditAccessibilityParams(
        serial=args.get("serial"),
        include_log_signals=bool(args.get("include_log_signals", True)),
        ignore_class_substrings=tuple(
            args.get("ignore_class_substrings")
            or ("Divider", "Padding", "SizedBox")
        ),
    )


# ---- v0.3.0 phase 6 — test path advisor --------------------------------


def _params_recommend_test_path(args: JsonDict) -> RecommendTestPathParams:
    baseline = args.get("size_baseline_path")
    return RecommendTestPathParams(
        project_path=Path(args["project_path"]).expanduser(),
        context=args["context"],
        device_serial=args.get("device_serial"),
        size_baseline_path=Path(baseline).expanduser() if baseline else None,
        coverage_fail_under=float(args.get("coverage_fail_under", 0.80)),
    )


# ---- v0.3.0 phase 7 — code-seniority audit -----------------------------


def _params_audit_code_seniority(args: JsonDict) -> AuditCodeSeniorityParams:
    paths = args.get("paths") or ()
    return AuditCodeSeniorityParams(
        project_path=Path(args["project_path"]).expanduser(),
        paths=tuple(str(p) for p in paths),
        min_level=str(args.get("min_level", "junior")),
        autofix=bool(args.get("autofix", False)),
        max_findings=int(args.get("max_findings", 200)),
    )


# ---- v0.3.0 phase 10 — dependencies / supply chain audit ---------------


def _params_audit_dependencies(args: JsonDict) -> AuditDependenciesParams:
    return AuditDependenciesParams(
        project_path=Path(args["project_path"]).expanduser(),
        min_level=str(args.get("min_level", "junior")),
        is_published=bool(args.get("is_published", True)),
        max_findings=int(args.get("max_findings", 200)),
    )


# ---- v0.5.0 phase 16 — Lighthouse report ingest ------------------------


def _params_ingest_har(args: JsonDict) -> IngestHarParams:
    return IngestHarParams(
        har_path=Path(args["har_path"]).expanduser(),
        backend_host=args.get("backend_host"),
        slow_ms=float(args.get("slow_ms", 1000.0)),
    )


def _params_ingest_frame_timeline(args: JsonDict) -> IngestFrameTimelineParams:
    return IngestFrameTimelineParams(
        timeline_path=Path(args["timeline_path"]).expanduser(),
        fps=int(args.get("fps", 60)),
        severe_factor=float(args.get("severe_factor", 2.0)),
    )


def _params_estimate_tokens(args: JsonDict) -> EstimateTokensParams:
    path = args.get("path")
    budget = args.get("budget_tokens")
    return EstimateTokensParams(
        text=args.get("text"),
        path=Path(path).expanduser() if path else None,
        budget_tokens=int(budget) if budget is not None else None,
        chars_per_token=float(args.get("chars_per_token", 4.0)),
    )


def _params_ingest_lighthouse_report(
    args: JsonDict,
) -> IngestLighthouseReportParams:
    return IngestLighthouseReportParams(
        report_path=Path(args["report_path"]).expanduser(),
        perf_good_threshold=float(args.get("perf_good_threshold", 70.0)),
    )


def _params_run_lighthouse(args: JsonDict) -> RunLighthouseParams:
    cats = args.get("categories")
    output = args.get("output_path")
    return RunLighthouseParams(
        url=str(args["url"]),
        output_path=Path(output).expanduser() if output else None,
        categories=tuple(cats) if isinstance(cats, list) and cats else None,
        preset=args.get("preset"),
        perf_good_threshold=float(args.get("perf_good_threshold", 70.0)),
        timeout_s=float(args.get("timeout_s", 180.0)),
    )


# ---- v0.5.0 phase 15 — Flutter web production-readiness audit -----------


def _params_audit_web_app(args: JsonDict) -> AuditWebAppParams:
    return AuditWebAppParams(
        project_path=Path(args["project_path"]).expanduser(),
        web_dir=args.get("web_dir"),
        min_level=str(args.get("min_level", "junior")),
        max_findings=int(args.get("max_findings", 200)),
    )


# ---- v0.4.0 phase 14 — Maestro execution report ingest -----------------


def _params_ingest_maestro_report(
    args: JsonDict,
) -> IngestMaestroReportParams:
    prior = args.get("prior_report_path")
    return IngestMaestroReportParams(
        report_path=Path(args["report_path"]).expanduser(),
        prior_report_path=Path(prior).expanduser() if prior else None,
    )


# ---- v0.4.0 phase 13 — Maestro flow audit ------------------------------


def _params_audit_maestro_flow(args: JsonDict) -> AuditMaestroFlowParams:
    paths = args.get("paths") or ()
    return AuditMaestroFlowParams(
        project_path=Path(args["project_path"]).expanduser(),
        paths=tuple(str(p) for p in paths),
        min_level=str(args.get("min_level", "junior")),
        max_findings=int(args.get("max_findings", 200)),
    )


# ---- v0.3.0 phase 12 — test-suite quality audit (post-write) -----------


def _params_audit_test_quality(args: JsonDict) -> AuditTestQualityParams:
    paths = args.get("paths") or ()
    return AuditTestQualityParams(
        project_path=Path(args["project_path"]).expanduser(),
        paths=tuple(str(p) for p in paths),
        min_level=str(args.get("min_level", "junior")),
        max_findings=int(args.get("max_findings", 200)),
    )


# ---- v0.3.0 phase 11.5 — senior-tester pre-write discipline ------------


def _params_design_test_plan(args: JsonDict) -> DesignTestPlanParams:
    project_path_arg = args.get("project_path")
    return DesignTestPlanParams(
        user_story=str(args.get("user_story", "")),
        acceptance_criteria=tuple(
            str(a) for a in (args.get("acceptance_criteria") or [])
        ),
        source_paths=tuple(
            str(p) for p in (args.get("source_paths") or [])
        ),
        project_path=(
            Path(project_path_arg).expanduser()
            if project_path_arg else None
        ),
        feature_kind=str(args.get("feature_kind", "generic")),
        team_style=str(args.get("team_style", "developer_heavy")),
        time_box_min=int(args.get("time_box_min", 60)),
    )


# ---- v0.3.0 phase 11 — release-readiness composite ---------------------


def _params_audit_release_readiness(
    args: JsonDict,
) -> AuditReleaseReadinessParams:
    return AuditReleaseReadinessParams(
        project_path=Path(args["project_path"]).expanduser(),
        min_level=str(args.get("min_level", "junior")),
        include_seniority=bool(args.get("include_seniority", True)),
        include_security=bool(args.get("include_security", True)),
        include_localization=bool(args.get("include_localization", True)),
        include_dependencies=bool(args.get("include_dependencies", True)),
        include_test_quality=bool(args.get("include_test_quality", True)),
        include_web_app=bool(args.get("include_web_app", True)),
        maestro_report_path=(
            Path(args["maestro_report_path"]).expanduser()
            if args.get("maestro_report_path") else None
        ),
        maestro_prior_report_path=(
            Path(args["maestro_prior_report_path"]).expanduser()
            if args.get("maestro_prior_report_path") else None
        ),
        lighthouse_report_path=(
            Path(args["lighthouse_report_path"]).expanduser()
            if args.get("lighthouse_report_path") else None
        ),
        is_published=bool(args.get("is_published", True)),
        weight_seniority=float(args.get("weight_seniority", 1.0)),
        weight_security=float(args.get("weight_security", 2.0)),
        weight_localization=float(args.get("weight_localization", 1.0)),
        weight_dependencies=float(args.get("weight_dependencies", 1.5)),
        weight_test_quality=float(args.get("weight_test_quality", 1.5)),
        weight_test_execution=float(args.get("weight_test_execution", 1.5)),
        weight_web_app=float(args.get("weight_web_app", 1.0)),
        weight_web_vitals=float(args.get("weight_web_vitals", 1.0)),
        max_top_actions=int(args.get("max_top_actions", 10)),
    )


# ---- v0.3.0 phase 9 — localization audit -------------------------------


def _params_audit_localization(args: JsonDict) -> AuditLocalizationParams:
    paths = args.get("paths") or ()
    return AuditLocalizationParams(
        project_path=Path(args["project_path"]).expanduser(),
        paths=tuple(str(p) for p in paths),
        arb_dir=args.get("arb_dir"),
        min_level=str(args.get("min_level", "junior")),
        max_findings=int(args.get("max_findings", 200)),
    )


# ---- v0.3.0 phase 8 — security audit -----------------------------------


def _params_audit_security(args: JsonDict) -> AuditSecurityParams:
    paths = args.get("paths") or ()
    return AuditSecurityParams(
        project_path=Path(args["project_path"]).expanduser(),
        paths=tuple(str(p) for p in paths),
        min_severity=str(args.get("min_severity", "medium")),
        max_findings=int(args.get("max_findings", 200)),
    )


def _params_audit_performance(args: JsonDict) -> AuditPerformanceParams:
    paths = args.get("paths") or ()
    return AuditPerformanceParams(
        project_path=Path(args["project_path"]).expanduser(),
        paths=tuple(str(p) for p in paths),
        min_severity=str(args.get("min_severity", "low")),
        max_findings=int(args.get("max_findings", 200)),
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
    team_id = args.get("team_id")
    return SetupWebDriverAgentParams(
        udid=args["udid"],
        wda_dir=Path(args["wda_dir"]).expanduser() if args.get("wda_dir") else None,
        repo_url=args.get("repo_url", "https://github.com/appium/WebDriverAgent.git"),
        scheme=args.get("scheme", "WebDriverAgentRunner"),
        skip_if_built=bool(args.get("skip_if_built", True)),
        team_id=str(team_id).strip() if team_id else None,
        is_simulator=args.get("is_simulator"),
    )


def _params_start_wda_on_simulator(
    args: JsonDict,
) -> StartWdaOnSimulatorParams:
    return StartWdaOnSimulatorParams(
        udid=args["udid"],
        port=int(args.get("port", 8100)),
        wda_dir=Path(args["wda_dir"]).expanduser() if args.get("wda_dir") else None,
        scheme=args.get("scheme", "WebDriverAgentRunner"),
        ready_timeout_s=float(args.get("ready_timeout_s", 60.0)),
    )
