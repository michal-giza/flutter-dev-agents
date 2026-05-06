"""Unit tests for narrate."""

from __future__ import annotations

from mcp_phone_controll.domain.usecases.narrate import narrate_envelope


def test_ok_with_list():
    msg = narrate_envelope({"ok": True, "data": [1, 2, 3]}, tool="list_devices")
    assert "list_devices" in msg and "3 item" in msg


def test_ok_with_truncation_marker():
    msg = narrate_envelope(
        {"ok": True, "data": "x" * 9000, "data_truncated": True},
        tool="read_logs",
    )
    assert "truncated" in msg


def test_error_with_next_action():
    msg = narrate_envelope(
        {
            "ok": False,
            "error": {
                "code": "DeviceBusyFailure",
                "message": "Lock held by other session",
                "next_action": "wait_or_force",
            },
        },
        tool="select_device",
    )
    assert "✗" in msg
    assert "DeviceBusyFailure" in msg
    assert "→ wait_or_force" in msg


def test_ok_with_dict_keys():
    msg = narrate_envelope(
        {"ok": True, "data": {"a": 1, "b": 2, "c": 3}},
        tool="inspect_project",
    )
    assert "object with keys" in msg
