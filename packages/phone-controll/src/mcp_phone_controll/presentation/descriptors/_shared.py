"""Shared primitives for tool descriptors: ToolDescriptor + schema helpers.

Kept tiny on purpose. Any change here ripples to every descriptor file —
treat additions like changes to a public API.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...domain.result import Result
from ...domain.usecases.base import NoParams

JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    """One MCP tool: name, JSON-schema, params builder, async invoker.

    Optional **MCP 2025-06-18 annotations** surfaced verbatim by the
    stdio adapter so hosts can gate destructive ops at the UX layer
    (e.g. always-confirm on `tap`, never-confirm on `take_screenshot`).
    Defaults are deliberately *safe*: unknown destructive behaviour
    rather than unknown read-only behaviour. Override per descriptor.

    - `read_only`: tool does not modify host or world state. Always
      safe to call. Examples: `take_screenshot`, `list_devices`,
      `describe_capabilities`.
    - `destructive`: tool modifies state in a way that matters (taps
      a button, installs an app, deletes a file). Hosts SHOULD
      surface a confirmation. Examples: `tap`, `swipe`, `install_app`,
      `boot_simulator`, `patch_apply_safe`.
    - `idempotent`: repeated calls with the same args produce the
      same result. Hosts MAY auto-retry on transient failure.
      Examples: `take_screenshot`, `describe_*`, `list_*`.
    - `open_world`: tool interacts with state outside our control
      (real network, real device). Otherwise hermetic. Examples:
      `notify_webhook`, `tap` against a real phone, `run_*_tests`.
    """

    name: str
    description: str
    input_schema: JsonDict
    build_params: Callable[[JsonDict], Any]
    invoke: Callable[[JsonDict], Awaitable[Result[Any]]]
    # MCP 2025-06-18 annotations — None means "not advertised".
    read_only: bool | None = None
    destructive: bool | None = None
    idempotent: bool | None = None
    open_world: bool | None = None


# ---- schema helpers ----------------------------------------------------


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


def default_annotations(tool_name: str) -> dict[str, bool]:
    """Best-effort MCP 2025-06-18 annotations from the tool name alone.

    Centralised so we annotate all 108 tools without 108 inline edits.
    Per-tool overrides on `ToolDescriptor` always win — this is the
    fallback for tools that don't explicitly set their flags.

    Conservative defaults: when ambiguous, claim **destructive**, not
    read-only — the cost of a missing "are you sure?" prompt on a real
    `tap` is much worse than the cost of an extra prompt on something
    that turned out to be safe.

    Returns a dict of `{readOnlyHint, destructiveHint, idempotentHint,
    openWorldHint}` — only flags we can confidently assert are included.
    """
    # Read-only prefixes that always pass through unchanged. These never
    # write to disk, never touch a device's state, never call a remote.
    READ_ONLY_PREFIXES = (
        "list_", "describe_", "get_", "dump_", "read_", "inspect_",
        "session_summary", "summarize_session", "mcp_ping",
        "check_environment", "disk_usage",
        "find_", "is_", "tail_", "grep_", "extract_ui_graph",
        "ocr_screenshot", "compare_screenshot", "detect_markers",
        "infer_camera_pose", "assert_", "wait_for_", "validate_test_plan",
        "tool_usage_report", "recall", "narrate",
        "vm_list_isolates", "dart_analyze",
        "flutter_pub_outdated", "list_patrol_tests",
        "list_simulators", "list_avds", "list_locks", "list_devices",
        "list_debug_sessions", "list_ide_windows", "list_skills",
        "is_ide_available",
    )
    # Destructive tools — touch device state, install/launch/stop apps,
    # write files in arbitrary places, modify project source.
    DESTRUCTIVE_PREFIXES = (
        "tap", "swipe", "type_text", "press_key",
        "install_app", "uninstall_app", "launch_app", "stop_app",
        "clear_app_data", "grant_permission",
        "start_emulator", "stop_virtual_device", "boot_simulator",
        "start_recording", "stop_recording",
        "force_release_lock", "release_device", "select_device",
        "set_agent_profile", "prune_originals", "compress_png",
        "patch_apply_safe", "scaffold_feature", "dart_fix",
        "dart_format", "flutter_pub_get", "save_golden_image",
        "notify_webhook", "prepare_for_test",
        "start_debug_session", "stop_debug_session",
        "restart_debug_session", "attach_debug_session",
        "call_service_extension", "toggle_inspector", "vm_evaluate",
        "start_wda_on_simulator", "setup_webdriveragent",
        "open_project_in_ide", "close_ide_window", "focus_ide_window",
        "write_vscode_launch_config",
        "index_project", "promote_sequence", "replay_skill",
        "calibrate_camera", "wait_for_ar_session_ready",
        "assert_pose_stable",  # samples real sensor — affects state if app reacts
        "quality_gate", "run_quick_check",
        "run_test_plan", "run_patrol_test", "run_patrol_suite",
        "run_unit_tests", "run_integration_tests",
        "capture_release_screenshot",
        "take_screenshot",  # writes to disk; idempotent in effect though
        "new_session", "fetch_artifact",  # writes session metadata / reads disk
        "wait_for_marker",  # polling — open-world
    )
    # Open-world: interacts with real devices, real network, real
    # filesystem we don't control.
    OPEN_WORLD_PREFIXES = (
        "tap", "swipe", "type_text", "press_key", "take_screenshot",
        "start_recording", "stop_recording",
        "install_app", "uninstall_app", "launch_app", "stop_app",
        "clear_app_data", "grant_permission",
        "list_devices", "list_simulators", "list_avds",
        "start_emulator", "stop_virtual_device", "boot_simulator",
        "check_environment", "notify_webhook",
        "start_debug_session", "stop_debug_session",
        "restart_debug_session", "attach_debug_session",
        "call_service_extension", "toggle_inspector", "vm_evaluate",
        "vm_list_isolates", "read_debug_log", "tail_debug_log",
        "dump_widget_tree", "dump_render_tree",
        "start_wda_on_simulator", "setup_webdriveragent",
        "open_project_in_ide", "close_ide_window", "focus_ide_window",
        "is_ide_available",
        "run_test_plan", "run_patrol_test", "run_patrol_suite",
        "run_unit_tests", "run_integration_tests",
        "dart_analyze", "dart_fix", "dart_format",
        "flutter_pub_get", "flutter_pub_outdated",
        "quality_gate", "run_quick_check",
        "build_app", "patch_apply_safe",
        "assert_pose_stable", "wait_for_ar_session_ready",
        "wait_for_marker", "calibrate_camera",
        "tap_text", "tap_and_verify", "find_element", "wait_for_element",
        "dump_ui", "assert_visible", "assert_no_errors_since",
        "read_logs", "tail_logs", "grep_logs", "extract_ui_graph",
        "ocr_screenshot", "capture_release_screenshot",
        "save_golden_image", "compare_screenshot", "detect_markers",
        "infer_camera_pose",
        "prepare_for_test", "release_device", "select_device",
        "force_release_lock",
    )
    # Idempotent: repeated calls with the same args produce the same
    # result. Hosts MAY auto-retry on transient failure.
    IDEMPOTENT_PREFIXES = (
        "list_", "describe_", "get_", "dump_", "read_", "inspect_",
        "session_summary", "mcp_ping", "check_environment",
        "find_", "is_", "tail_", "grep_", "extract_ui_graph",
        "ocr_screenshot", "compare_screenshot", "detect_markers",
        "infer_camera_pose", "assert_visible", "wait_for_",
        "validate_test_plan", "tool_usage_report", "recall",
        "vm_list_isolates", "take_screenshot",  # second call overwrites; result equivalent
        "dump_widget_tree", "dump_render_tree", "read_debug_log",
        "tail_debug_log", "dump_ui", "extract_ui_graph",
        "assert_no_errors_since", "assert_pose_stable",
        "list_patrol_tests", "list_simulators", "list_avds",
        "list_locks", "list_devices", "list_debug_sessions",
        "list_ide_windows", "list_skills", "is_ide_available",
        "is_within", "focus_ide_window",
        "flutter_pub_outdated", "dart_analyze",
        # compress_png is idempotent on already-compressed files
        "compress_png",
        # prune_originals with the same older_than_days is idempotent
        "prune_originals",
    )

    def _matches(name: str, prefixes: tuple[str, ...]) -> bool:
        return any(name == p or name.startswith(p) for p in prefixes)

    flags: dict[str, bool] = {}
    is_ro = _matches(tool_name, READ_ONLY_PREFIXES)
    is_destr = _matches(tool_name, DESTRUCTIVE_PREFIXES)
    is_idem = _matches(tool_name, IDEMPOTENT_PREFIXES)
    is_open = _matches(tool_name, OPEN_WORLD_PREFIXES)

    # Read-only + destructive are mutually exclusive. If both classifiers
    # fire (e.g. `list_devices` is read-only AND interacts with adb),
    # read-only wins for the readOnlyHint flag, but openWorldHint stays.
    if is_ro:
        flags["readOnlyHint"] = True
        flags["destructiveHint"] = False
    elif is_destr:
        flags["readOnlyHint"] = False
        flags["destructiveHint"] = True
    if is_idem:
        flags["idempotentHint"] = True
    if is_open:
        flags["openWorldHint"] = True
    return flags


def _params_no(_: JsonDict) -> NoParams:
    """Builder for tools that take no arguments."""
    return NoParams()
