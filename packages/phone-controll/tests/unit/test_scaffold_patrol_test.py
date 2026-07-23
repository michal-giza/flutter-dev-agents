"""scaffold_patrol_test — emit a Patrol-4 web+mobile e2e smoke test.

The EMITTED Dart is compile-verified out-of-band against a real
`flutter analyze` on patrol 4.7.1 (see the session log / docs). These
hermetic tests pin the tool's behavior: correct target path, package-name
substitution, patrol-presence detection, idempotency, and validation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.usecases.productivity import (
    ScaffoldPatrolTest,
    ScaffoldPatrolTestParams,
)


def _project(tmp_path: Path, *, name: str = "my_app", patrol: bool = True) -> Path:
    pubspec = "name: " + name + "\nenvironment:\n  sdk: '>=3.8.0 <4.0.0'\n"
    if patrol:
        pubspec += "dev_dependencies:\n  patrol: ^4.7.0\n"
    (tmp_path / "pubspec.yaml").write_text(pubspec, encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_emits_test_into_patrol_test_dir(tmp_path: Path):
    proj = _project(tmp_path)
    res = await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=proj, test_name="checkout_flow")
    )
    assert res.is_ok
    v = res.value
    assert v.created == ("patrol_test/checkout_flow_test.dart",)
    body = (proj / "patrol_test" / "checkout_flow_test.dart").read_text()
    # verified-API surface must be present verbatim
    assert "import 'package:patrol/patrol.dart';" in body
    assert "import 'package:my_app/main.dart';" in body   # package-name substituted
    assert "patrolTest(" in body
    assert "tags: 'smoke'," in body
    assert "await $.pumpWidgetAndSettle(const MyApp());" in body
    assert "$(#checkout_flow_primary_action).tap()" in body
    # never the deprecated native automator
    assert "$.native" not in body


@pytest.mark.asyncio
async def test_custom_root_widget_is_used(tmp_path: Path):
    proj = _project(tmp_path)
    await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=proj, root_widget="KayonApp")
    )
    body = (proj / "patrol_test" / "app_smoke_test.dart").read_text()
    assert "const KayonApp()" in body


@pytest.mark.asyncio
async def test_flags_missing_patrol_dependency(tmp_path: Path):
    proj = _project(tmp_path, patrol=False)
    res = await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=proj)
    )
    assert res.is_ok
    v = res.value
    assert v.patrol_in_pubspec is False
    # the guidance must include the pubspec block to add
    assert any("patrol: ^4.7.0" in step for step in v.next_steps)


@pytest.mark.asyncio
async def test_run_commands_cover_web_and_mobile(tmp_path: Path):
    proj = _project(tmp_path)
    res = await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=proj)
    )
    v = res.value
    assert "platform=mobile" in v.run_mobile and "serial=" in v.run_mobile
    assert "platform=web" in v.run_web and "ci=true" in v.run_web
    assert "junit_path=" in v.run_web   # ties into the CI/JUnit feature


@pytest.mark.asyncio
async def test_idempotent_unless_overwrite(tmp_path: Path):
    proj = _project(tmp_path)
    first = await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=proj)
    )
    assert first.value.created and not first.value.skipped
    second = await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=proj)
    )
    assert not second.value.created and second.value.skipped
    third = await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=proj, overwrite=True)
    )
    assert third.value.created and not third.value.skipped


@pytest.mark.asyncio
async def test_rejects_non_flutter_project(tmp_path: Path):
    res = await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=tmp_path)  # no pubspec.yaml
    )
    assert not res.is_ok
    assert res.failure.next_action == "check_path"


@pytest.mark.asyncio
async def test_rejects_bad_test_name(tmp_path: Path):
    proj = _project(tmp_path)
    res = await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=proj, test_name="CheckoutFlow")
    )
    assert not res.is_ok
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_rejects_bad_root_widget(tmp_path: Path):
    proj = _project(tmp_path)
    res = await ScaffoldPatrolTest().execute(
        ScaffoldPatrolTestParams(project_path=proj, root_widget="123 not ident")
    )
    assert not res.is_ok
    assert res.failure.next_action == "fix_arguments"
