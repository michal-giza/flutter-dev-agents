"""Tests for Patrol use cases, project inspector, and the doctor surface."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.composite_project_inspector import (
    CompositeProjectInspector,
)
from mcp_phone_controll.data.repositories.flutter_project_inspector import (
    FlutterProjectInspector,
)
from mcp_phone_controll.domain.entities import (
    PatrolTestFile,
    ProjectType,
    TestFramework,
)
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.base import NoParams
from mcp_phone_controll.domain.usecases.doctor import CheckEnvironment
from mcp_phone_controll.domain.usecases.patrol import (
    ListPatrolTests,
    ListPatrolTestsParams,
    RunPatrolSuite,
    RunPatrolSuiteParams,
    RunPatrolTest,
    RunPatrolTestParams,
)
from mcp_phone_controll.domain.usecases.projects import (
    InspectProject,
    InspectProjectParams,
)
from tests.fakes.fake_repositories import (
    FakeEnvironmentRepository,
    FakePatrolRepository,
    FakeProjectInspector,
    FakeSessionStateRepository,
)


# --- doctor ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_environment_returns_full_report():
    uc = CheckEnvironment(FakeEnvironmentRepository())
    res = await uc(NoParams())
    assert isinstance(res, Ok)
    names = {c.name for c in res.value.checks}
    assert {"adb", "flutter", "patrol", "pymobiledevice3"} <= names


# --- inspector ------------------------------------------------------------


@pytest.mark.asyncio
async def test_flutter_project_inspector_detects_patrol(tmp_path: Path):
    (tmp_path / "pubspec.yaml").write_text(
        "name: my_app\n"
        "dependencies:\n  flutter:\n    sdk: flutter\n"
        "dev_dependencies:\n  patrol: ^3.0.0\n"
    )
    info_res = await FlutterProjectInspector().inspect(tmp_path)
    assert isinstance(info_res, Ok)
    assert info_res.value.type is ProjectType.FLUTTER
    assert info_res.value.test_frameworks[0] is TestFramework.PATROL
    assert TestFramework.FLUTTER in info_res.value.test_frameworks
    assert info_res.value.package_id == "my_app"


@pytest.mark.asyncio
async def test_flutter_project_inspector_without_patrol(tmp_path: Path):
    (tmp_path / "pubspec.yaml").write_text(
        "name: pure_flutter\ndependencies:\n  flutter:\n    sdk: flutter\n"
    )
    info_res = await FlutterProjectInspector().inspect(tmp_path)
    assert info_res.value.test_frameworks == (TestFramework.FLUTTER,)


@pytest.mark.asyncio
async def test_inspector_unknown_project(tmp_path: Path):
    info_res = await FlutterProjectInspector().inspect(tmp_path)
    assert info_res.value.type is ProjectType.UNKNOWN


@pytest.mark.asyncio
async def test_composite_inspector_returns_first_match(tmp_path: Path):
    (tmp_path / "pubspec.yaml").write_text("name: x\nflutter:\n  uses-material-design: true\n")
    composite = CompositeProjectInspector([FlutterProjectInspector()])
    res = await composite.inspect(tmp_path)
    assert res.value.type is ProjectType.FLUTTER


@pytest.mark.asyncio
async def test_inspect_project_use_case(tmp_path: Path):
    (tmp_path / "pubspec.yaml").write_text(
        "name: foo\nflutter:\n  sdk: flutter\ndev_dependencies:\n  patrol_cli:\n"
    )
    uc = InspectProject(FlutterProjectInspector())
    res = await uc(InspectProjectParams(project_path=tmp_path))
    assert isinstance(res, Ok)
    assert TestFramework.PATROL in res.value.test_frameworks


# --- patrol use cases -----------------------------------------------------


@pytest.mark.asyncio
async def test_list_patrol_tests_passthrough(tmp_path: Path):
    files = [
        PatrolTestFile(path=tmp_path / "auth_test.dart", relative=Path("auth_test.dart"), name="auth_test")
    ]
    repo = FakePatrolRepository(files=files)
    uc = ListPatrolTests(repo)
    res = await uc(ListPatrolTestsParams(project_path=tmp_path))
    assert isinstance(res, Ok)
    assert res.value[0].name == "auth_test"


@pytest.mark.asyncio
async def test_run_patrol_test_resolves_serial_from_state(tmp_path: Path):
    repo = FakePatrolRepository()
    state = FakeSessionStateRepository(serial="EMU01")
    uc = RunPatrolTest(repo, state)
    res = await uc(
        RunPatrolTestParams(project_path=tmp_path, test_path=Path("integration_test/x_test.dart"))
    )
    assert isinstance(res, Ok)
    assert any(c[0] == "run_test" and c[3] == "EMU01" for c in repo.calls)


@pytest.mark.asyncio
async def test_run_patrol_test_without_selected_device_errors(tmp_path: Path):
    uc = RunPatrolTest(FakePatrolRepository(), FakeSessionStateRepository())
    res = await uc(
        RunPatrolTestParams(project_path=tmp_path, test_path=Path("x.dart"))
    )
    assert isinstance(res, Err)


@pytest.mark.asyncio
async def test_run_patrol_suite_uses_default_dir(tmp_path: Path):
    repo = FakePatrolRepository()
    state = FakeSessionStateRepository(serial="EMU01")
    uc = RunPatrolSuite(repo, state)
    res = await uc(RunPatrolSuiteParams(project_path=tmp_path))
    assert isinstance(res, Ok)
    suite_call = next(c for c in repo.calls if c[0] == "run_suite")
    assert suite_call[2] == "integration_test"


# --- composite test repository chooses Patrol when available --------------


@pytest.mark.asyncio
async def test_composite_test_repository_routes_to_patrol():
    """If the inspector reports Patrol availability, integration tests run via Patrol."""
    from mcp_phone_controll.data.repositories.composite.composite_repositories import (
        CompositeTestRepository,
    )
    from mcp_phone_controll.data.repositories.composite.platform_resolver import (
        CachingPlatformResolver,
    )
    from mcp_phone_controll.domain.entities import Platform
    from tests.fakes.fake_repositories import FakeTestRepository

    flutter = FakeTestRepository()
    patrol = FakePatrolRepository()
    resolver = CachingPlatformResolver()
    await resolver.remember("EMU01", Platform.ANDROID)

    repo = CompositeTestRepository(
        android=flutter,
        ios=flutter,
        resolver=resolver,
        framework_runners={TestFramework.PATROL: patrol},
        inspector=FakeProjectInspector(),  # default returns Patrol-capable
    )
    res = await repo.run_integration_tests(Path("/proj"), "EMU01")
    assert isinstance(res, Ok)
    assert any(c[0] == "run_integration_tests" for c in patrol.calls)
