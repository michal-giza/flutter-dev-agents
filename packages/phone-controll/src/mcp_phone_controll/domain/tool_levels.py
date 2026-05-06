"""Tool ladder for small-LLM agents.

Three levels — basic, intermediate, expert — curate the visible tool surface so
4B-class models aren't overwhelmed by 67+ tools. Each level is a strict subset
of the next.

The mapping is intentionally conservative: a tool earns its way up by being
*safely usable* by a small model. Tools that need careful reasoning (vision
calibration, low-level service-extension calls, force-release-lock) live at
expert.
"""

from __future__ import annotations


BASIC_TOOLS: tuple[str, ...] = (
    # Discover the world
    "describe_capabilities",
    "describe_tool",
    "check_environment",
    "inspect_project",
    # Devices
    "list_devices",
    "select_device",
    "get_selected_device",
    "release_device",
    # Sessions
    "new_session",
    "get_artifacts_dir",
    "session_summary",
    # Lifecycle (the obvious ones)
    "prepare_for_test",
    "launch_app",
    "stop_app",
    "take_screenshot",
    "read_logs",
    # Tests via plans (preferred path for small LLMs)
    "validate_test_plan",
    "run_test_plan",
)


INTERMEDIATE_TOOLS: tuple[str, ...] = BASIC_TOOLS + (
    # Patrol and Flutter test
    "list_patrol_tests",
    "run_patrol_test",
    "run_patrol_suite",
    "run_unit_tests",
    "run_integration_tests",
    # Build / install
    "build_app",
    "install_app",
    "uninstall_app",
    "clear_app_data",
    "grant_permission",
    # Dev session lifecycle
    "start_debug_session",
    "stop_debug_session",
    "restart_debug_session",
    "list_debug_sessions",
    "read_debug_log",
    "tail_debug_log",
    # IDE basic
    "open_project_in_ide",
    "list_ide_windows",
    "close_ide_window",
    # Code quality (essential)
    "dart_analyze",
    "dart_format",
    "quality_gate",
    # Virtual devices
    "list_avds",
    "list_simulators",
    "start_emulator",
    "boot_simulator",
    "stop_virtual_device",
    # Vision essentials (incl. advanced for the AR-heavy 4/6 apps)
    "compare_screenshot",
    "save_golden_image",
    "wait_for_ar_session_ready",
    "assert_pose_stable",
    # Locks (visibility)
    "list_locks",
    # Logs (advanced)
    "tail_logs",
)


# Expert is "all tools" — the function below derives this dynamically from
# the registered descriptors so adding a new tool doesn't require touching
# this file.

_BY_LEVEL = {
    "basic": BASIC_TOOLS,
    "intermediate": INTERMEDIATE_TOOLS,
}


# Per-level recommended starting sequence — the canonical "happy path" the
# agent should bias toward before exploring. Mirrors the autonomous-loop
# checklist in examples/agent_loop_small_llm.py and the ReAct prior.
_RECOMMENDED_SEQUENCE: dict[str, tuple[str, ...]] = {
    "basic": (
        "describe_capabilities",
        "check_environment",
        "inspect_project",
        "list_devices",
        "select_device",
        "new_session",
        "prepare_for_test",
        "run_test_plan",
        "summarize_session",
        "release_device",
    ),
    "intermediate": (
        "describe_capabilities",
        "check_environment",
        "inspect_project",
        "list_devices",
        "select_device",
        "new_session",
        "open_project_in_ide",
        "start_debug_session",
        "restart_debug_session",
        "tap_and_verify",
        "assert_no_errors_since",
        "summarize_session",
        "stop_debug_session",
        "release_device",
    ),
}


def recommended_sequence_for_level(level: str) -> tuple[str, ...]:
    """Return the canonical tool order for the given level.

    Empty tuple at expert level — Claude doesn't need a prescribed path; the
    constraint is harmful at that capability tier.
    """
    return _RECOMMENDED_SEQUENCE.get(level, ())


def tools_for_level(
    level: str, all_tool_names: tuple[str, ...]
) -> tuple[str, ...]:
    """Return the subset of `all_tool_names` exposed at the given level.

    'expert' (or any unrecognised level) returns the full list.
    """
    subset = _BY_LEVEL.get(level)
    if subset is None:
        return all_tool_names
    # Preserve the dispatcher's order, filter to the level-permitted set.
    permitted = set(subset)
    return tuple(name for name in all_tool_names if name in permitted)
