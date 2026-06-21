"""batch — run an ordered tool sequence server-side in one round-trip (v0.15.0 #1)."""

from __future__ import annotations

import pytest

from tests.integration.test_tool_dispatcher import _build_fake_dispatcher


@pytest.mark.asyncio
async def test_batch_runs_steps_in_order(tmp_path):
    d = _build_fake_dispatcher(tmp_path)
    env = await d.dispatch(
        "batch",
        {
            "steps": [
                {"tool": "list_devices"},
                {"tool": "select_device", "args": {"serial": "EMU01"}},
                {"tool": "get_selected_device", "label": "confirm"},
            ]
        },
    )
    assert env["ok"] is True, env
    data = env["data"]
    assert data["steps_total"] == 3
    assert data["steps_run"] == 3
    assert data["all_ok"] is True
    assert [r["tool"] for r in data["results"]] == [
        "list_devices", "select_device", "get_selected_device"
    ]
    assert data["results"][2]["label"] == "confirm"


@pytest.mark.asyncio
async def test_batch_stops_on_first_error_by_default(tmp_path):
    d = _build_fake_dispatcher(tmp_path)
    env = await d.dispatch(
        "batch",
        {
            "steps": [
                {"tool": "list_devices"},
                {"tool": "select_device", "args": {}},   # missing serial → fails
                {"tool": "list_devices"},                # must NOT run
            ]
        },
    )
    assert env["ok"] is False
    assert env["error"]["code"] == "BatchStepFailed"
    assert env["error"]["next_action"] == "inspect_batch_results"
    data = env["data"]
    assert data["steps_run"] == 2          # stopped after the failing step
    assert data["results"][1]["ok"] is False
    assert data["all_ok"] is False


@pytest.mark.asyncio
async def test_batch_continue_on_error_runs_all(tmp_path):
    d = _build_fake_dispatcher(tmp_path)
    env = await d.dispatch(
        "batch",
        {
            "stop_on_error": False,
            "capture_on_failure": False,
            "steps": [
                {"tool": "select_device", "args": {}},   # fail
                {"tool": "list_devices"},                # still runs
            ],
        },
    )
    assert env["ok"] is False
    assert env["data"]["steps_run"] == 2
    assert env["data"]["results"][0]["ok"] is False
    assert env["data"]["results"][1]["ok"] is True


@pytest.mark.asyncio
async def test_batch_captures_diagnostics_on_failure(tmp_path):
    """v0.15.0 #2: a failed step folds in a screenshot + recent logs, so
    the agent diagnoses inline instead of spending another round-trip."""
    d = _build_fake_dispatcher(tmp_path)
    env = await d.dispatch(
        "batch",
        {
            "steps": [
                {"tool": "select_device", "args": {"serial": "EMU01"}},  # ok
                {"tool": "select_device", "args": {}},                   # fails
            ]
        },
    )
    assert env["ok"] is False
    failed = env["data"]["results"][1]
    assert failed["ok"] is False
    assert "diagnostics" in failed
    assert "screenshot" in failed["diagnostics"]
    assert "recent_logs" in failed["diagnostics"]


@pytest.mark.asyncio
async def test_batch_no_diagnostics_when_disabled(tmp_path):
    d = _build_fake_dispatcher(tmp_path)
    env = await d.dispatch(
        "batch",
        {
            "capture_on_failure": False,
            "steps": [
                {"tool": "select_device", "args": {"serial": "EMU01"}},
                {"tool": "select_device", "args": {}},
            ],
        },
    )
    assert "diagnostics" not in env["data"]["results"][1]


@pytest.mark.asyncio
async def test_batch_rejects_nested_batch(tmp_path):
    d = _build_fake_dispatcher(tmp_path)
    env = await d.dispatch(
        "batch",
        {"steps": [{"tool": "batch", "args": {"steps": []}}], "capture_on_failure": False},
    )
    assert env["ok"] is False
    assert "nested batch" in env["data"]["results"][0]["error"]["message"]


@pytest.mark.asyncio
async def test_batch_empty_steps_is_invalid(tmp_path):
    d = _build_fake_dispatcher(tmp_path)
    env = await d.dispatch("batch", {"steps": []})
    assert env["ok"] is False
    assert env["error"]["code"] == "InvalidArgumentFailure"
    assert "corrected_example" in env["error"]["details"]


@pytest.mark.asyncio
async def test_batch_step_missing_tool_is_invalid(tmp_path):
    d = _build_fake_dispatcher(tmp_path)
    env = await d.dispatch(
        "batch", {"steps": [{"args": {}}], "capture_on_failure": False}
    )
    assert env["ok"] is False
    assert env["data"]["results"][0]["error"]["code"] == "InvalidArgumentFailure"


@pytest.mark.asyncio
async def test_batch_caps_step_count(tmp_path):
    d = _build_fake_dispatcher(tmp_path)
    env = await d.dispatch(
        "batch", {"steps": [{"tool": "list_devices"}] * 31}
    )
    assert env["ok"] is False
    assert "at most" in env["error"]["message"]
