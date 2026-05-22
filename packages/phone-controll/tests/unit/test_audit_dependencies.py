"""Tests for the v0.3.0 phase-10 dependency / supply-chain audit.

Each rule fires on a known-bad pubspec fixture and stays silent
on a known-good fixture. The pubspec parser is the trickiest
piece — it has to handle nested-map overrides, version pins,
and section transitions without using a YAML library.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.audit_dependencies import (
    AuditDependencies,
    AuditDependenciesParams,
    DependencyLevel,
    Severity,
)

# ---- fixture helpers ----------------------------------------------------


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    (tmp_path / "lib").mkdir()
    return tmp_path


async def _run(project: Path, **kwargs) -> Ok | Err:
    return await AuditDependencies()(
        AuditDependenciesParams(project_path=project, **kwargs)
    )


def _rules(res: Ok) -> set[str]:
    return {f.rule for f in res.value.findings}


def _pubspec(project: Path, body: str) -> Path:
    return _write(project / "pubspec.yaml", body)


def _lock(project: Path, body: str) -> Path:
    return _write(project / "pubspec.lock", body)


# ---- happy paths + error handling --------------------------------------


@pytest.mark.asyncio
async def test_missing_project_path_returns_typed_failure(tmp_path: Path):
    res = await _run(tmp_path / "does_not_exist")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_missing_pubspec_returns_typed_failure(tmp_path: Path):
    proj = _project(tmp_path)
    # no pubspec.yaml
    res = await _run(proj)
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_invalid_min_level_returns_typed_failure(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\ndependencies:\n  flutter:\n    sdk: flutter\n",
    )
    res = await _run(proj, min_level="principal")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_clean_pubspec_returns_clean_grade(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  cupertino_icons: 1.0.5\n"
        "dev_dependencies:\n"
        "  flutter_test:\n"
        "    sdk: flutter\n",
    )
    _write(
        proj / "lib" / "main.dart",
        "import 'package:cupertino_icons/cupertino_icons.dart';\n"
        "void main() {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade in ("clean", "acceptable")


# ---- JUNIOR-tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_dev_dep_in_dependencies_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  build_runner: ^2.4.0\n"
        "  mockito: ^5.4.0\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    rules = _rules(res)
    assert "dev_dep_in_dependencies" in rules
    packages = {
        f.package for f in res.value.findings
        if f.rule == "dev_dep_in_dependencies"
    }
    assert "build_runner" in packages
    assert "mockito" in packages


@pytest.mark.asyncio
async def test_git_override_fires_on_published(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  my_internal:\n"
        "    git:\n"
        "      url: https://github.com/me/foo.git\n",
    )
    res = await _run(proj, is_published=True)
    assert isinstance(res, Ok)
    assert "git_or_path_override" in _rules(res)


@pytest.mark.asyncio
async def test_git_override_silent_on_unpublished(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  my_internal:\n"
        "    git:\n"
        "      url: https://github.com/me/foo.git\n",
    )
    res = await _run(proj, is_published=False)
    assert isinstance(res, Ok)
    assert "git_or_path_override" not in _rules(res)


# ---- MID-tier rules ----------------------------------------------------


@pytest.mark.asyncio
async def test_caret_on_security_sensitive_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  firebase_auth: ^4.0.0\n"
        "  dio: ^5.0.0\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    findings = [
        f for f in res.value.findings
        if f.rule == "pinned_to_caret_only"
    ]
    assert len(findings) >= 1
    packages = {f.package for f in findings}
    assert "firebase_auth" in packages or "dio" in packages


@pytest.mark.asyncio
async def test_caret_on_non_sensitive_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  cupertino_icons: ^1.0.5\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "pinned_to_caret_only" not in _rules(res)


@pytest.mark.asyncio
async def test_wide_version_range_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  some_pkg: '>=1.0.0 <4.0.0'\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "wide_version_range" in _rules(res)


# ---- SENIOR-tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_unused_dependency_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  http: ^1.0.0\n"
        "  orphan_pkg: ^2.0.0\n",
    )
    # Only import http, not orphan_pkg
    _write(
        proj / "lib" / "main.dart",
        "import 'package:http/http.dart' as http;\n"
        "void main() {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    rules = _rules(res)
    assert "unused_dependency" in rules
    unused = {
        f.package for f in res.value.findings
        if f.rule == "unused_dependency"
    }
    assert "orphan_pkg" in unused
    assert "http" not in unused


@pytest.mark.asyncio
async def test_transitive_used_as_direct_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n",
    )
    # Import a package that isn't declared
    _write(
        proj / "lib" / "main.dart",
        "import 'package:sneaky_transitive/foo.dart';\n"
        "void main() {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "transitive_used_as_direct" in _rules(res)
    undeclared = {
        f.package for f in res.value.findings
        if f.rule == "transitive_used_as_direct"
    }
    assert "sneaky_transitive" in undeclared


@pytest.mark.asyncio
async def test_duplicated_dependency_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  mockito: ^5.0.0\n"
        "dev_dependencies:\n"
        "  mockito: ^5.0.0\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "duplicated_dependency" in _rules(res)


# ---- STAFF-tier rules --------------------------------------------------


@pytest.mark.asyncio
async def test_known_deprecated_package_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  package_info: ^2.0.0\n"
        "  connectivity: ^3.0.0\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    rules = _rules(res)
    assert "known_vulnerable_package" in rules
    packages = {
        f.package for f in res.value.findings
        if f.rule == "known_vulnerable_package"
    }
    assert "package_info" in packages
    assert "connectivity" in packages


@pytest.mark.asyncio
async def test_loose_flutter_sdk_constraint_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "environment:\n"
        "  sdk: '>=3.0.0'\n"
        "  flutter: '>=3.16.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "flutter_sdk_constraint_loose" in _rules(res)


@pytest.mark.asyncio
async def test_tight_flutter_sdk_constraint_silent(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "environment:\n"
        "  sdk: '>=3.0.0 <4.0.0'\n"
        "  flutter: '>=3.16.0 <4.0.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "flutter_sdk_constraint_loose" not in _rules(res)


@pytest.mark.asyncio
async def test_copyleft_hint_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  some_gpl_thing: ^1.0.0\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "license_blocklist" in _rules(res)


# ---- engine behaviors --------------------------------------------------


@pytest.mark.asyncio
async def test_counts_deps_correctly(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  http: ^1.0.0\n"
        "  used_pkg: ^1.0.0\n"
        "  unused_pkg: ^2.0.0\n"
        "dev_dependencies:\n"
        "  flutter_test:\n"
        "    sdk: flutter\n"
        "  mockito: ^5.0.0\n",
    )
    _write(
        proj / "lib" / "main.dart",
        "import 'package:http/http.dart';\n"
        "import 'package:used_pkg/used_pkg.dart';\n"
        "void main() {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # 4 entries in deps section: flutter, http, used_pkg, unused_pkg
    assert res.value.deps_total == 4
    # 2 entries in dev: flutter_test, mockito
    assert res.value.dev_deps_total == 2
    # unused: unused_pkg (flutter is implicit, doesn't count)
    assert res.value.deps_unused == 1
    assert res.value.deps_undeclared == 0


@pytest.mark.asyncio
async def test_min_level_filter_suppresses_lower(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  build_runner: ^2.4.0\n",  # junior
    )
    res = await _run(proj, min_level="senior")
    assert isinstance(res, Ok)
    # All findings should be senior+
    assert all(
        f.level != DependencyLevel.JUNIOR for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_top_actions_prioritize_serious(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  build_runner: ^2.4.0\n"  # serious (junior)
        "  mockito: ^5.0.0\n"        # serious (junior)
        "dev_dependencies:\n"
        "  package_info: ^2.0.0\n",  # serious (staff)
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # All findings here are 'serious'; top_actions exists
    assert res.value.top_actions
    assert "[serious]" in res.value.top_actions[0]


@pytest.mark.asyncio
async def test_grade_clean_when_truly_clean(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "environment:\n"
        "  sdk: '>=3.0.0 <4.0.0'\n"
        "  flutter: '>=3.16.0 <4.0.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  cupertino_icons: 1.0.5\n",
    )
    _write(
        proj / "lib" / "main.dart",
        "import 'package:cupertino_icons/cupertino_icons.dart';\n"
        "void main() {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade == "clean"


@pytest.mark.asyncio
async def test_findings_sorted_by_severity(tmp_path: Path):
    proj = _project(tmp_path)
    _pubspec(
        proj,
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  firebase_auth: ^4.0.0\n"  # minor
        "  build_runner: ^2.4.0\n",  # serious
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    sev_order = {
        Severity.BLOCKER: 0, Severity.SERIOUS: 1, Severity.MINOR: 2,
    }
    seq = [sev_order[f.severity] for f in res.value.findings]
    assert seq == sorted(seq)
