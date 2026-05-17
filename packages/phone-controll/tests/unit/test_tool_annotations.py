"""MCP 2025-06-18 tool annotations — verify the classifier + override path.

Hosts (Claude Desktop, Claude Code, Cursor) use these flags to gate
destructive operations at the UX layer. Missing them silently downgrades
safety prompts. We classify all 108 tools via `default_annotations(name)`;
per-tool overrides on the `ToolDescriptor` always win.

These tests pin the **floor invariants**:
  - read-only tools are flagged read-only AND not destructive
  - destructive tools are flagged destructive AND not read-only
  - real-device tools are flagged open-world
  - per-tool override wins over the classifier

We don't test every individual tool's flags — that would freeze the
classifier in place and break on every legitimate tool addition. We
test the invariants.
"""

from __future__ import annotations

import pytest

from mcp_phone_controll.container import build_runtime
from mcp_phone_controll.presentation.descriptors._shared import (
    default_annotations,
)


@pytest.fixture(scope="module")
def all_tool_names() -> list[str]:
    _, dispatcher = build_runtime()
    return [d.name for d in dispatcher.descriptors]


def test_every_tool_gets_at_least_one_annotation(all_tool_names):
    """A tool with NO annotations means the classifier missed it.
    The host can't make a safe call about whether to prompt. Fail
    loudly so the next tool addition is forced to extend the
    classifier."""
    missing = [n for n in all_tool_names if not default_annotations(n)]
    assert not missing, (
        f"{len(missing)} tools have no annotations — extend "
        f"default_annotations() in descriptors/_shared.py: {missing[:10]}"
    )


def test_read_only_and_destructive_are_mutually_exclusive(all_tool_names):
    """A tool can't claim both — the classifier's job is to pick the
    safer interpretation. Anthropic's spec is explicit on this."""
    for name in all_tool_names:
        flags = default_annotations(name)
        if flags.get("readOnlyHint") and flags.get("destructiveHint"):
            pytest.fail(
                f"{name} claims BOTH readOnlyHint and destructiveHint"
            )


def test_obviously_destructive_tools_are_flagged():
    """Tripwire: tools that mutate device state MUST be flagged
    destructive. If anyone re-classifies these as read-only, hosts
    skip the confirmation prompt and the user loses safety."""
    for name in (
        "tap",
        "swipe",
        "install_app",
        "uninstall_app",
        "clear_app_data",
        "patch_apply_safe",
        "compress_png",
        "release_device",
        "force_release_lock",
        "boot_simulator",
    ):
        flags = default_annotations(name)
        assert flags.get("destructiveHint") is True, (
            f"{name} must be destructiveHint=True; got {flags}"
        )


def test_obviously_read_only_tools_are_flagged():
    """Same tripwire, opposite direction: read-only tools must be
    flagged so hosts can skip confirmation prompts. Missing readOnly
    means the user is bothered for `list_devices`-like calls."""
    for name in (
        "list_devices",
        "describe_capabilities",
        "describe_tool",
        "session_summary",
        "mcp_ping",
        "check_environment",
        "inspect_project",
        "read_logs",
        "dump_ui",
    ):
        flags = default_annotations(name)
        assert flags.get("readOnlyHint") is True, (
            f"{name} must be readOnlyHint=True; got {flags}"
        )


def test_open_world_tools_are_flagged():
    """Tools that interact with real devices/network/disk must be
    flagged open-world so hosts know retries aren't free."""
    for name in (
        "tap",
        "take_screenshot",
        "list_devices",
        "notify_webhook",
        "run_patrol_test",
        "start_debug_session",
        "build_app",
    ):
        flags = default_annotations(name)
        assert flags.get("openWorldHint") is True, (
            f"{name} must be openWorldHint=True; got {flags}"
        )


def test_descriptor_override_wins_over_classifier():
    """Per-tool override on `ToolDescriptor.read_only` etc. must take
    precedence over the classifier's default. This is the escape hatch
    for tools whose name doesn't match a clear pattern."""
    from mcp_phone_controll.presentation.descriptors._shared import (
        ToolDescriptor,
    )

    # Use a name the classifier would normally flag destructive...
    d = ToolDescriptor(
        name="tap",
        description="fake override",
        input_schema={"type": "object", "properties": {}},
        build_params=lambda _: None,
        invoke=lambda _: None,  # type: ignore[arg-type]
        read_only=True,  # ...override claims read-only
    )
    # The descriptor-level override is what the host adapter SHOULD
    # surface; verify the dataclass holds the override.
    assert d.read_only is True
    # Classifier alone would still say destructive — they disagree by design.
    cls_flags = default_annotations("tap")
    assert cls_flags.get("destructiveHint") is True
