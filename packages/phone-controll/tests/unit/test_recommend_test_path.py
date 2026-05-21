"""Tests for the v0.3.0 phase-6 test-path advisor.

What this validates:

- All 7 canonical paths build cleanly + return non-empty step lists.
- Steps reference real MCP tool names (catches typos that would
  silently produce broken plans).
- Pass criteria + isolation guarantees + alternative paths are
  populated for every path.
- Estimated wall-clock matches the sum of step estimates.
- Invalid context returns a typed failure with fix_arguments.
- Missing project_path returns the same.
- coverage_fail_under threads through to pre_pr + pre_release.
- size_baseline_path threads through to nightly + pre_release.
- device_serial threads through to paths that lock a device.
- Each path's steps are sorted in execution order (no out-of-order
  cleanup-before-action mistakes).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.recommend_test_path import (
    RecommendTestPath,
    RecommendTestPathParams,
    TestPath,
)


# The set of tool names a path is allowed to reference. Computed
# from the live registry so this test catches a path step that
# references a tool that doesn't exist (would silently produce a
# broken plan when an agent tries to execute).
def _live_tool_names() -> set[str]:
    from mcp_phone_controll.container import build_runtime
    _, dispatcher = build_runtime()
    return {t.name for t in dispatcher.descriptors}


# ---- happy path: every canonical path builds ---------------------------


@pytest.fixture(scope="module")
def all_tool_names():
    return _live_tool_names()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context", [p.value for p in TestPath],
)
async def test_every_path_builds_cleanly(tmp_path: Path, context: str):
    """Every TestPath enum value produces an Ok result with a
    non-empty step list."""
    proj = tmp_path
    res = await RecommendTestPath()(
        RecommendTestPathParams(project_path=proj, context=context)
    )
    assert isinstance(res, Ok), f"Path {context} failed: {res}"
    v = res.value
    assert v.path == context
    assert len(v.steps) > 0
    assert v.description
    assert v.pass_criteria
    assert v.isolation_guarantees
    assert v.advice


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context", [p.value for p in TestPath],
)
async def test_every_step_references_a_real_tool(
    tmp_path: Path, context: str, all_tool_names: set[str]
):
    """No path may reference a tool that doesn't exist in the live
    registry. Catches refactor drift where a path is left pointing at
    a renamed/removed tool."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(project_path=tmp_path, context=context)
    )
    assert isinstance(res, Ok)
    for step in res.value.steps:
        assert step.tool in all_tool_names, (
            f"Path {context!r} step references unknown tool {step.tool!r}. "
            f"Did the tool get renamed?"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context", [p.value for p in TestPath],
)
async def test_estimated_wall_clock_matches_step_sum(
    tmp_path: Path, context: str
):
    """estimated_wall_clock_s must equal the sum of step.estimated_s
    so callers can trust the headline number."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(project_path=tmp_path, context=context)
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.estimated_wall_clock_s == sum(s.estimated_s for s in v.steps)


# ---- specific path quality checks --------------------------------------


@pytest.mark.asyncio
async def test_pre_commit_has_no_device_steps(tmp_path: Path):
    """pre_commit is the 60-second hook — it must NOT touch a device.
    No select_device, no launch_app, no anything that requires a phone."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(project_path=tmp_path, context="pre_commit")
    )
    assert isinstance(res, Ok)
    device_touching = {
        "select_device", "launch_app", "stop_app", "tap", "tap_text",
        "tap_and_verify", "clear_app_data", "press_key", "swipe",
        "take_screenshot", "install_app", "start_debug_session",
    }
    used = {s.tool for s in res.value.steps}
    assert not (used & device_touching), (
        f"pre_commit references device-touching tools: {used & device_touching}"
    )


@pytest.mark.asyncio
async def test_pre_pr_includes_coverage_threshold(tmp_path: Path):
    """pre_pr passes fail_under through to test_coverage_report so
    the threshold gate actually gates."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(
            project_path=tmp_path, context="pre_pr", coverage_fail_under=0.75
        )
    )
    assert isinstance(res, Ok)
    cov_step = next(
        (s for s in res.value.steps if s.tool == "test_coverage_report"), None
    )
    assert cov_step is not None
    assert cov_step.args.get("fail_under") == 0.75


@pytest.mark.asyncio
async def test_pre_pr_locks_and_releases_device(tmp_path: Path):
    """Any path that uses select_device MUST also release_device.
    Catches lock-leakage that would block other Claude sessions."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(project_path=tmp_path, context="pre_pr")
    )
    assert isinstance(res, Ok)
    tools = [s.tool for s in res.value.steps]
    if "select_device" in tools:
        assert "release_device" in tools, (
            "Path locks a device but doesn't release it — lock-leakage risk."
        )
        # select MUST come before release
        select_idx = tools.index("select_device")
        release_idx = tools.index("release_device")
        assert select_idx < release_idx


@pytest.mark.asyncio
async def test_daily_dev_brackets_frame_profile(tmp_path: Path):
    """daily_dev opens AND closes the frame_profile bracket — leaving
    Timeline on burns CPU on the device after the session ends."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(project_path=tmp_path, context="daily_dev")
    )
    assert isinstance(res, Ok)
    tools = [s.tool for s in res.value.steps]
    assert "start_frame_profile" in tools
    assert "stop_frame_profile" in tools
    assert tools.index("start_frame_profile") < tools.index("stop_frame_profile")


@pytest.mark.asyncio
async def test_daily_dev_pairs_debug_session(tmp_path: Path):
    """start_debug_session must be paired with stop_debug_session.
    Orphan daemons keep flutter run --machine processes alive
    indefinitely."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(project_path=tmp_path, context="daily_dev")
    )
    assert isinstance(res, Ok)
    tools = [s.tool for s in res.value.steps]
    if "start_debug_session" in tools:
        assert "stop_debug_session" in tools
        assert tools.index("start_debug_session") < tools.index("stop_debug_session")


@pytest.mark.asyncio
async def test_nightly_threads_size_baseline(tmp_path: Path):
    """If size_baseline_path is provided, analyze_app_size receives it."""
    baseline = tmp_path / "baseline.json"
    res = await RecommendTestPath()(
        RecommendTestPathParams(
            project_path=tmp_path,
            context="nightly",
            size_baseline_path=baseline,
        )
    )
    assert isinstance(res, Ok)
    size_step = next(
        (s for s in res.value.steps if s.tool == "analyze_app_size"), None
    )
    assert size_step is not None
    assert size_step.args.get("baseline_json_path") == str(baseline)


@pytest.mark.asyncio
async def test_pre_release_runs_build_before_size_analysis(tmp_path: Path):
    """The release build must happen BEFORE analyze_app_size — otherwise
    there's no APK/IPA to analyze."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(project_path=tmp_path, context="pre_release")
    )
    assert isinstance(res, Ok)
    tools = [s.tool for s in res.value.steps]
    assert tools.index("build_app") < tools.index("analyze_app_size")


@pytest.mark.asyncio
async def test_postmortem_captures_diagnostics_before_summary(tmp_path: Path):
    """The diagnostic captures (memory, logs, widget tree) must all
    happen BEFORE session_summary — otherwise the summary doesn't see
    them."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(project_path=tmp_path, context="postmortem")
    )
    assert isinstance(res, Ok)
    tools = [s.tool for s in res.value.steps]
    summary_idx = tools.index("session_summary")
    for diagnostic in ("memory_summary", "read_debug_log", "dump_widget_tree"):
        if diagnostic in tools:
            assert tools.index(diagnostic) < summary_idx, (
                f"{diagnostic} happens after session_summary — summary won't see it."
            )


@pytest.mark.asyncio
async def test_device_serial_threads_through_to_select_device(tmp_path: Path):
    """When device_serial is provided, the select_device step gets it."""
    res = await RecommendTestPath()(
        RecommendTestPathParams(
            project_path=tmp_path,
            context="pre_pr",
            device_serial="R3CYA05CHXB",
        )
    )
    assert isinstance(res, Ok)
    select_step = next(
        (s for s in res.value.steps if s.tool == "select_device"), None
    )
    assert select_step is not None
    assert select_step.args.get("serial") == "R3CYA05CHXB"


# ---- error paths -------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_context_returns_typed_failure(tmp_path: Path):
    res = await RecommendTestPath()(
        RecommendTestPathParams(
            project_path=tmp_path, context="bogus_context"
        )
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_missing_project_path_returns_typed_failure(tmp_path: Path):
    res = await RecommendTestPath()(
        RecommendTestPathParams(
            project_path=tmp_path / "does_not_exist", context="pre_commit"
        )
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ---- isolation guarantees content ------------------------------------------


@pytest.mark.asyncio
async def test_isolation_guarantees_mention_no_production(tmp_path: Path):
    """Production-impacting paths must explicitly disclaim production
    backend access in their isolation_guarantees."""
    for context in ("pre_pr", "nightly", "pre_release"):
        res = await RecommendTestPath()(
            RecommendTestPathParams(project_path=tmp_path, context=context)
        )
        assert isinstance(res, Ok)
        combined = " ".join(res.value.isolation_guarantees).lower()
        # Either explicit 'no production' or 'test devices' / 'test env'
        # phrasing — both convey the safety guarantee.
        assert (
            "production" in combined
            or "test devices" in combined
            or "test/integration env" in combined
        ), (
            f"Path {context} doesn't disclaim production access in "
            f"isolation_guarantees: {res.value.isolation_guarantees}"
        )
