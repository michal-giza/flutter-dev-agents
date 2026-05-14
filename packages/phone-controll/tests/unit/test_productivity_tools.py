"""Unit tests for Tier-F productivity tools."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mcp_phone_controll.domain.entities import SessionTrace, TraceEntry
from mcp_phone_controll.domain.result import Err, ok
from mcp_phone_controll.domain.usecases.productivity import (
    FindFlutterWidget,
    FindFlutterWidgetParams,
    GrepLogs,
    GrepLogsParams,
    ScaffoldFeature,
    ScaffoldFeatureParams,
    SummarizeSession,
    SummarizeSessionParams,
)

# ---- scaffold_feature ----------------------------------------------------


def _flutter_project(tmp_path: Path) -> Path:
    proj = tmp_path / "app"
    proj.mkdir()
    (proj / "pubspec.yaml").write_text("name: app\n")
    return proj


@pytest.mark.asyncio
async def test_scaffold_feature_creates_full_skeleton(tmp_path: Path):
    proj = _flutter_project(tmp_path)
    res = await ScaffoldFeature().execute(
        ScaffoldFeatureParams(project_path=proj, feature_name="auth_login")
    )
    assert res.is_ok
    created = res.value.created
    assert any("entities/auth_login.dart" in p for p in created)
    assert any("usecases/get_auth_login.dart" in p for p in created)
    assert any("bloc/auth_login_bloc.dart" in p for p in created)
    body = (proj / "lib/features/auth_login/domain/entities/auth_login.dart").read_text()
    assert "class AuthLogin" in body


@pytest.mark.asyncio
async def test_scaffold_feature_rejects_non_flutter(tmp_path: Path):
    res = await ScaffoldFeature().execute(
        ScaffoldFeatureParams(project_path=tmp_path, feature_name="x")
    )
    assert isinstance(res, Err)


@pytest.mark.asyncio
async def test_scaffold_feature_rejects_camel_case_name(tmp_path: Path):
    proj = _flutter_project(tmp_path)
    res = await ScaffoldFeature().execute(
        ScaffoldFeatureParams(project_path=proj, feature_name="AuthLogin")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_scaffold_feature_skips_existing_unless_overwrite(tmp_path: Path):
    proj = _flutter_project(tmp_path)
    await ScaffoldFeature().execute(
        ScaffoldFeatureParams(project_path=proj, feature_name="x")
    )
    res = await ScaffoldFeature().execute(
        ScaffoldFeatureParams(project_path=proj, feature_name="x")
    )
    assert res.is_ok
    assert res.value.created == ()
    assert len(res.value.skipped) > 0


# ---- grep_logs -----------------------------------------------------------


@pytest.mark.asyncio
async def test_grep_logs_returns_matches_with_context(tmp_path: Path):
    log = tmp_path / "session.log"
    log.write_text("\n".join(
        ["line one", "line two", "boom error here", "line four", "line five"]
    ))
    res = await GrepLogs().execute(
        GrepLogsParams(path=log, pattern=r"error", context_lines=1)
    )
    assert res.is_ok
    matches = res.value.matches
    assert len(matches) == 1
    assert matches[0].line_no == 3
    assert matches[0].context_before == ("line two",)
    assert matches[0].context_after == ("line four",)


@pytest.mark.asyncio
async def test_grep_logs_truncates_at_max_matches(tmp_path: Path):
    log = tmp_path / "session.log"
    log.write_text("\n".join(["match"] * 20))
    res = await GrepLogs().execute(
        GrepLogsParams(path=log, pattern=r"match", max_matches=5)
    )
    assert res.is_ok
    assert len(res.value.matches) == 5
    assert res.value.truncated is True


# ---- summarize_session ---------------------------------------------------


class _Repo:
    def __init__(self, entries):
        self._entries = entries

    async def record(self, _entry):
        return ok(None)

    async def summary(self, _sid=None):
        return ok(
            SessionTrace(
                session_id="s1",
                started_at=datetime(2024, 1, 1),
                entries=tuple(self._entries),
            )
        )


@pytest.mark.asyncio
async def test_summarize_session_produces_pitch():
    entries = [
        TraceEntry(1, "select_device", {}, True, None, "ok"),
        TraceEntry(2, "tap_text", {}, False, "UiElementNotFoundFailure", "no Welcome"),
        TraceEntry(3, "take_screenshot", {}, True, None, "ok"),
    ]
    res = await SummarizeSession(_Repo(entries)).execute(
        SummarizeSessionParams()
    )
    assert res.is_ok
    pitch = res.value
    assert "3 calls" in pitch.headline
    assert "2✓" in pitch.headline
    assert "1✗" in pitch.headline
    assert any("tap_text" in e for e in pitch.errors)


# ---- find_flutter_widget -------------------------------------------------


@pytest.mark.asyncio
async def test_find_flutter_widget_locates_classes(tmp_path: Path):
    proj = _flutter_project(tmp_path)
    lib = proj / "lib"
    lib.mkdir()
    (lib / "page.dart").write_text(
        "class HomePage extends StatelessWidget {}\n"
        "class _Helper extends Object {}\n"
    )
    (lib / "second.dart").write_text(
        "class SettingsPage extends StatefulWidget {}\n"
    )
    res = await FindFlutterWidget().execute(
        FindFlutterWidgetParams(project_path=proj, name_pattern=r"Page$")
    )
    assert res.is_ok
    names = {m.name for m in res.value.matches}
    assert names == {"HomePage", "SettingsPage"}
