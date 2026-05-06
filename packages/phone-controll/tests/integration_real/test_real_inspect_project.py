"""Opt-in: real inspect_project + list_patrol_tests against the fixture app.

Verifies the parser layer (pubspec.yaml inspection, integration_test/
listing) against a real Flutter project layout — the kind of coverage
unit tests with fake repositories cannot give.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_inspect_project_parses_fixture(sample_flutter_app: Path):
    from mcp_phone_controll.container import build_runtime

    use_cases, dispatcher = build_runtime()
    res = await dispatcher.dispatch(
        "inspect_project", {"project_path": str(sample_flutter_app)}
    )
    assert res["ok"] is True, res
    info = res["data"]
    assert info["name"] == "sample_app"
    assert "patrol" in {d["name"] for d in info.get("dev_dependencies", [])}


@pytest.mark.asyncio
async def test_list_patrol_tests_finds_smoke(sample_flutter_app: Path):
    from mcp_phone_controll.container import build_runtime

    use_cases, dispatcher = build_runtime()
    res = await dispatcher.dispatch(
        "list_patrol_tests", {"project_path": str(sample_flutter_app)}
    )
    assert res["ok"] is True, res
    files = res["data"]
    assert isinstance(files, list)
    assert any(
        Path(item["path"] if isinstance(item, dict) else item).name == "smoke_test.dart"
        for item in files
    ), files
