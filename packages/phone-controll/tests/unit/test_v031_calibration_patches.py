"""Regression tests for the 8 v0.3.1 calibration patches surfaced
by the v0.3.0 field test on party_games_ui, mytaskboardapp, and
bike_news_room/frontend.

Each test verifies that a specific false-positive (or false-
negative) from the field test no longer fires after the patch.

See docs/v030-field-test.md for the calibration log that drove
these patches.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Ok
from mcp_phone_controll.domain.usecases.audit_code_seniority import (
    AuditCodeSeniority,
    AuditCodeSeniorityParams,
)
from mcp_phone_controll.domain.usecases.audit_dependencies import (
    AuditDependencies,
    AuditDependenciesParams,
)
from mcp_phone_controll.domain.usecases.audit_localization import (
    AuditLocalization,
    AuditLocalizationParams,
)
from mcp_phone_controll.domain.usecases.audit_security import (
    AuditSecurity,
    AuditSecurityParams,
)
from mcp_phone_controll.domain.usecases.audit_test_quality import (
    AuditTestQuality,
    AuditTestQualityParams,
)


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ============================================================
# Patches #1 + #2 — exclude build/ and .claude/worktrees/
# ============================================================


@pytest.mark.asyncio
async def test_security_skips_build_dir(tmp_path: Path):
    """Patch #1: Flutter-generated AndroidManifest.xml in build/
    must NOT trigger exported_component."""
    (tmp_path / "lib").mkdir()
    _write(tmp_path / "lib" / "main.dart", "void main() {}\n")
    # Real manifest at standard location → should be scanned
    _write(
        tmp_path / "android" / "app" / "src" / "main" / "AndroidManifest.xml",
        '<manifest><activity android:exported="true"/></manifest>\n',
    )
    # Generated build manifest — should be EXCLUDED
    _write(
        tmp_path / "build" / "app" / "intermediates"
        / "merged_manifest" / "release" / "AndroidManifest.xml",
        '<manifest><activity android:exported="true"/></manifest>\n',
    )
    res = await AuditSecurity()(
        AuditSecurityParams(project_path=tmp_path, min_severity="high")
    )
    assert isinstance(res, Ok)
    files = {f.file for f in res.value.findings}
    assert any("android/app/src/main" in f for f in files), (
        "Real manifest must still fire"
    )
    assert not any("build/" in f for f in files), (
        "Generated build manifest must NOT fire"
    )


@pytest.mark.asyncio
async def test_security_skips_claude_worktrees(tmp_path: Path):
    """Patch #2: agent worktree copies under .claude/worktrees/
    must NOT be scanned."""
    (tmp_path / "lib").mkdir()
    _write(
        tmp_path / "lib" / "real.dart",
        "// only-real-code\n",
    )
    # Worktree copy with a fake AWS key — should be excluded
    _write(
        tmp_path / ".claude" / "worktrees" / "abc123"
        / "lib" / "fake_secret.dart",
        "const key = 'AKIA" + "0123456789ABCDEF" + "';\n",
    )
    res = await AuditSecurity()(
        AuditSecurityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    files = {f.file for f in res.value.findings}
    assert not any(".claude" in f for f in files), (
        ".claude/worktrees/ must be excluded; got: " + str(files)
    )


@pytest.mark.asyncio
async def test_test_quality_skips_build_dir(tmp_path: Path):
    """Patch #1 (test_quality variant): generated test files under
    build/ are not real tests."""
    (tmp_path / "test").mkdir()
    _write(
        tmp_path / "test" / "real_test.dart",
        "void main() { test('x', () { expect(1, 1); }); }\n",
    )
    _write(
        tmp_path / "build" / "test_cache" / "fake_test.dart",
        "void main() { test('x', () { tester.pump(); }); }\n",
    )
    res = await AuditTestQuality()(
        AuditTestQualityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    files = {f.file for f in res.value.findings}
    assert not any("build/" in f for f in files)


# ============================================================
# Patch #3 — firebase_options.dart exception
# ============================================================


@pytest.mark.asyncio
async def test_firebase_options_dart_does_not_fire(tmp_path: Path):
    """Patch #3: AIza keys INSIDE firebase_options.dart with a
    FirebaseOptions(...) constructor are legitimate."""
    (tmp_path / "lib").mkdir()
    _write(
        tmp_path / "lib" / "firebase_options.dart",
        "import 'package:firebase_core/firebase_core.dart';\n"
        "class DefaultFirebaseOptions {\n"
        "  static FirebaseOptions get android => const FirebaseOptions(\n"
        "    apiKey: 'AIza" + "0123456789012345678901234567890abcd" + "',\n"
        "    appId: '1:123:android:abc',\n"
        "  );\n"
        "}\n",
    )
    res = await AuditSecurity()(
        AuditSecurityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert not any(
        f.rule == "hardcoded_firebase_key"
        for f in res.value.findings
    ), "Canonical firebase_options.dart must not fire the rule"


@pytest.mark.asyncio
async def test_aiza_key_in_other_file_still_fires(tmp_path: Path):
    """Patch #3 must NOT silence legitimate findings: AIza in any
    OTHER file is still a smell."""
    (tmp_path / "lib").mkdir()
    _write(
        tmp_path / "lib" / "leaked.dart",
        "const apiKey = 'AIza" + "0123456789012345678901234567890abcd" + "';\n",
    )
    res = await AuditSecurity()(
        AuditSecurityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert any(
        f.rule == "hardcoded_firebase_key"
        for f in res.value.findings
    )


# ============================================================
# Patch #4 — await_missing_on_pump with Patrol's $.tester
# ============================================================


@pytest.mark.asyncio
async def test_patrol_dollar_tester_with_await_silent(tmp_path: Path):
    """Patch #4: `await $.tester.pumpAndSettle(...)` (Patrol
    convention) must NOT fire await_missing_on_pump."""
    (tmp_path / "test").mkdir()
    _write(
        tmp_path / "test" / "x_test.dart",
        "void main() {\n"
        "  patrolTest('x', ($) async {\n"
        "    await $.tester.pumpAndSettle(const Duration(seconds: 1));\n"
        "  });\n"
        "}\n",
    )
    res = await AuditTestQuality()(
        AuditTestQualityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert not any(
        f.rule == "await_missing_on_pump"
        for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_dollar_tester_without_await_still_fires(tmp_path: Path):
    """Patch #4 must not over-silence: `$.tester.pumpAndSettle(...)`
    WITHOUT await must still fire."""
    (tmp_path / "test").mkdir()
    _write(
        tmp_path / "test" / "x_test.dart",
        "void main() {\n"
        "  patrolTest('x', ($) async {\n"
        "    $.tester.pumpAndSettle();\n"
        "  });\n"
        "}\n",
    )
    res = await AuditTestQuality()(
        AuditTestQualityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert any(
        f.rule == "await_missing_on_pump"
        for f in res.value.findings
    )


# ============================================================
# Patch #5 — test_imports_test must not match flutter_test
# ============================================================


@pytest.mark.asyncio
async def test_flutter_test_package_import_silent(tmp_path: Path):
    """Patch #5: `import 'package:flutter_test/flutter_test.dart'`
    must NOT fire test_imports_test."""
    (tmp_path / "test").mkdir()
    _write(
        tmp_path / "test" / "x_test.dart",
        "import 'package:flutter_test/flutter_test.dart';\n"
        "void main() {\n"
        "  test('x', () { expect(1, 1); });\n"
        "}\n",
    )
    res = await AuditTestQuality()(
        AuditTestQualityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert not any(
        f.rule == "test_imports_test"
        for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_test_importing_another_test_still_fires(tmp_path: Path):
    """Patch #5 must not over-silence: importing a REAL test file
    from another test still fires."""
    (tmp_path / "test").mkdir()
    _write(
        tmp_path / "test" / "shared_test.dart",
        "void sharedHelper() {}\n",
    )
    _write(
        tmp_path / "test" / "x_test.dart",
        "import 'shared_test.dart';\n"
        "void main() {\n"
        "  test('x', () { expect(1, 1); });\n"
        "}\n",
    )
    res = await AuditTestQuality()(
        AuditTestQualityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert any(
        f.rule == "test_imports_test"
        for f in res.value.findings
    )


# ============================================================
# Patch #6 — transitive_used_as_direct must exclude own package
# ============================================================


@pytest.mark.asyncio
async def test_own_package_self_import_not_undeclared(tmp_path: Path):
    """Patch #6: `import 'package:my_app/foo.dart'` inside my_app's
    own lib/ is a self-import, not a transitive."""
    (tmp_path / "lib").mkdir()
    _write(
        tmp_path / "pubspec.yaml",
        "name: my_app\n"
        "environment:\n"
        "  sdk: '>=3.0.0 <4.0.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n",
    )
    _write(
        tmp_path / "lib" / "main.dart",
        "import 'package:my_app/widgets/home.dart';\n"
        "void main() {}\n",
    )
    res = await AuditDependencies()(
        AuditDependenciesParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert not any(
        f.rule == "transitive_used_as_direct" and f.package == "my_app"
        for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_actual_undeclared_transitive_still_fires(tmp_path: Path):
    """Patch #6 must not silence real undeclared transitives."""
    (tmp_path / "lib").mkdir()
    _write(
        tmp_path / "pubspec.yaml",
        "name: my_app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n",
    )
    _write(
        tmp_path / "lib" / "main.dart",
        "import 'package:bloc/bloc.dart';\n"  # bloc not declared
        "void main() {}\n",
    )
    res = await AuditDependencies()(
        AuditDependenciesParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert any(
        f.rule == "transitive_used_as_direct" and f.package == "bloc"
        for f in res.value.findings
    )


# ============================================================
# Patch #7 — orphan_source must skip barrel files
# ============================================================


@pytest.mark.asyncio
async def test_barrel_file_not_orphan(tmp_path: Path):
    """Patch #7: a file containing only `export 'x.dart';` lines
    has no logic to test."""
    (tmp_path / "lib").mkdir()
    _write(
        tmp_path / "lib" / "my_lib.dart",
        "library my_lib;\n"
        "\n"
        "export 'src/foo.dart';\n"
        "export 'src/bar.dart';\n"
        "// public surface\n",
    )
    _write(
        tmp_path / "lib" / "src" / "foo.dart",
        "class Foo {}\n",
    )
    res = await AuditCodeSeniority()(
        AuditCodeSeniorityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    orphans = [
        f for f in res.value.findings
        if f.rule == "orphan_source" and "my_lib" in f.file
    ]
    assert orphans == [], (
        f"Barrel file my_lib.dart wrongly flagged: {orphans}"
    )


@pytest.mark.asyncio
async def test_non_barrel_file_still_orphan(tmp_path: Path):
    """Patch #7 must not silence legitimate orphan findings."""
    (tmp_path / "lib").mkdir()
    _write(
        tmp_path / "lib" / "service.dart",
        "class Service {\n"
        "  void doThing() {}\n"
        "}\n",
    )
    res = await AuditCodeSeniority()(
        AuditCodeSeniorityParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert any(
        f.rule == "orphan_source" and "service.dart" in f.file
        for f in res.value.findings
    )


# ============================================================
# Patch #8 — missing_localizations_delegates must accept getter
# ============================================================


@pytest.mark.asyncio
async def test_delegates_getter_reference_silent(tmp_path: Path):
    """Patch #8: `localizationsDelegates: AppLocalizations.localizationsDelegates`
    (getter, no literal list) must NOT fire."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "l10n").mkdir(parents=True, exist_ok=True)
    (tmp_path / "lib" / "l10n" / "intl_en.arb").write_text(
        json.dumps({"hello": "Hi"}), encoding="utf-8",
    )
    (tmp_path / "lib" / "l10n" / "intl_pl.arb").write_text(
        json.dumps({"hello": "Cześć"}), encoding="utf-8",
    )
    _write(
        tmp_path / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget app() => MaterialApp(\n"
        "  localizationsDelegates: AppLocalizations.localizationsDelegates,\n"
        "  supportedLocales: const [Locale('en'), Locale('pl')],\n"
        ");\n",
    )
    _write(
        tmp_path / "pubspec.yaml",
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  flutter_localizations:\n"
        "    sdk: flutter\n",
    )
    res = await AuditLocalization()(
        AuditLocalizationParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert not any(
        f.rule == "missing_localizations_delegates"
        for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_no_delegates_at_all_still_fires(tmp_path: Path):
    """Patch #8 must not over-silence: a MaterialApp with NO
    localizationsDelegates anywhere still fires."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "l10n").mkdir(parents=True, exist_ok=True)
    (tmp_path / "lib" / "l10n" / "intl_en.arb").write_text(
        json.dumps({"hello": "Hi"}), encoding="utf-8",
    )
    (tmp_path / "lib" / "l10n" / "intl_pl.arb").write_text(
        json.dumps({"hello": "Cześć"}), encoding="utf-8",
    )
    _write(
        tmp_path / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget app() => MaterialApp(\n"
        "  supportedLocales: const [Locale('en'), Locale('pl')],\n"
        ");\n",
    )
    _write(
        tmp_path / "pubspec.yaml",
        "name: app\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  flutter_localizations:\n"
        "    sdk: flutter\n",
    )
    res = await AuditLocalization()(
        AuditLocalizationParams(project_path=tmp_path)
    )
    assert isinstance(res, Ok)
    assert any(
        f.rule == "missing_localizations_delegates"
        for f in res.value.findings
    )
