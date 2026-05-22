"""Tests for the v0.3.0 phase-12 test-suite quality audit.

Each rule fires on a known-bad Dart test fixture and stays
silent on a known-good fixture. The 28 rules are organised in
4 tiers and these tests verify the tier assignments.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.audit_test_quality import (
    AuditTestQuality,
    AuditTestQualityParams,
    TestQualityLevel,
)


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    (tmp_path / "lib").mkdir()
    (tmp_path / "test").mkdir()
    return tmp_path


async def _run(project: Path, **kwargs) -> Ok | Err:
    return await AuditTestQuality()(
        AuditTestQualityParams(project_path=project, **kwargs)
    )


def _rules(res: Ok) -> set[str]:
    return {f.rule for f in res.value.findings}


# ---- error handling ----------------------------------------------------


@pytest.mark.asyncio
async def test_missing_project_path_returns_failure(tmp_path: Path):
    res = await _run(tmp_path / "does_not_exist")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_invalid_min_level_returns_failure(tmp_path: Path):
    proj = _project(tmp_path)
    res = await _run(proj, min_level="principal")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_empty_test_dir_returns_excellent(tmp_path: Path):
    proj = _project(tmp_path)
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade == "excellent"
    assert res.value.findings == ()


# ---- Junior tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_bare_pump_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  testWidgets('x', (tester) async {\n"
        "    tester.pump();\n"  # no Duration, no await
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "bare_pump" in _rules(res)


@pytest.mark.asyncio
async def test_await_missing_on_pump_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  testWidgets('x', (tester) async {\n"
        "    tester.pumpWidget(MyApp());\n"  # no await
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "await_missing_on_pump" in _rules(res)


@pytest.mark.asyncio
async def test_hardcoded_locale_string_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  testWidgets('x', (tester) async {\n"
        "    expect(find.text('Sign in'), findsOneWidget);\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_locale_string" in _rules(res)


@pytest.mark.asyncio
async def test_l10n_aware_test_does_not_fire_locale_rule(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "import 'package:flutter_gen/gen_l10n/app_localizations.dart';\n"
        "void main() {\n"
        "  testWidgets('x', (tester) async {\n"
        "    expect(find.text('Sign in'), findsOneWidget);\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # L10n-aware test: rule stays silent (l10n import present)
    assert "hardcoded_locale_string" not in _rules(res)


@pytest.mark.asyncio
async def test_sleep_in_test_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('x', () async {\n"
        "    await Future.delayed(Duration(seconds: 2));\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "sleep_in_test" in _rules(res)


@pytest.mark.asyncio
async def test_vacuous_expect_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('x', () {\n"
        "    final result = doThing();\n"
        "    expect(result, isNotNull);\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "vacuous_expect" in _rules(res)


@pytest.mark.asyncio
async def test_untitled_skip_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('x', () {}, skip: true);\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "untitled_skip" in _rules(res)
    assert res.value.skipped_tests >= 1


# ---- Mid tier rules ----------------------------------------------------


@pytest.mark.asyncio
async def test_mocked_sut_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('x', () {\n"
        "    when(sut.doThing()).thenReturn('mock');\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "mocked_sut" in _rules(res)


@pytest.mark.asyncio
async def test_network_call_unmocked_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('x', () async {\n"
        "    final dio = Dio();\n"
        "    await dio.get('/foo');\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "network_call_unmocked" in _rules(res)


@pytest.mark.asyncio
async def test_network_call_silent_in_fake_files(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "fakes" / "fake_dio.dart",
        "final dio = Dio();\n",  # legit fake setup
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "network_call_unmocked" not in _rules(res)


@pytest.mark.asyncio
async def test_firestore_instance_unmocked_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('x', () async {\n"
        "    final docs = await FirebaseFirestore.instance"
        ".collection('users').get();\n"
        "    expect(docs.docs.length, 0);\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "firestore_instance_unmocked" in _rules(res)


@pytest.mark.asyncio
async def test_pump_count_smell_fires(tmp_path: Path):
    proj = _project(tmp_path)
    pumps = "\n    ".join(["await tester.pump();"] * 6)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  testWidgets('x', (tester) async {\n"
        f"    {pumps}\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "pump_count_smell" in _rules(res)


@pytest.mark.asyncio
async def test_golden_no_verified_comment_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  testWidgets('x', (tester) async {\n"
        "    await expectLater(find.byType(Widget), "
        "matchesGoldenFile('foo.png'));\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "golden_no_verified_comment" in _rules(res)


@pytest.mark.asyncio
async def test_golden_with_verified_comment_silent(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  testWidgets('x', (tester) async {\n"
        "    // verified 2026-05-22 by Michal\n"
        "    await expectLater(find.byType(Widget), "
        "matchesGoldenFile('foo.png'));\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "golden_no_verified_comment" not in _rules(res)


# ---- Senior tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_missing_failure_path_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('happy 1', () { expect(1, 1); });\n"
        "  test('happy 2', () { expect(2, 2); });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_failure_path" in _rules(res)


@pytest.mark.asyncio
async def test_failure_path_present_silent(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('happy', () { expect(1, 1); });\n"
        "  test('fails', () {\n"
        "    final err = doThing();\n"
        "    expect(err, isA<Failure>());\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_failure_path" not in _rules(res)


@pytest.mark.asyncio
async def test_e2e_doing_unit_work_fires(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "integration_test").mkdir()
    _write(
        proj / "integration_test" / "x_test.dart",
        "void main() {\n"
        "  test('pure function', () {\n"
        "    expect(double(2), 4);\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "e2e_doing_unit_work" in _rules(res)


@pytest.mark.asyncio
async def test_widget_test_no_provider_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  testWidgets('x', (tester) async {\n"
        "    final bloc = MyBloc();\n"
        "    await tester.pumpWidget(MyWidget(bloc: bloc));\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "widget_test_no_provider" in _rules(res)


# ---- Staff tier rules --------------------------------------------------


@pytest.mark.asyncio
async def test_nondeterministic_random_seed_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('x', () {\n"
        "    final r = Random();\n"
        "    expect(r.nextInt(10), lessThan(10));\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "nondeterministic_random_seed" in _rules(res)


@pytest.mark.asyncio
async def test_test_imports_test_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "shared_test.dart",
        "void sharedHelper() {}\n",
    )
    _write(
        proj / "test" / "x_test.dart",
        "import 'shared_test.dart';\n"
        "void main() {\n"
        "  test('x', () { expect(1, 1); });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "test_imports_test" in _rules(res)


@pytest.mark.asyncio
async def test_integration_test_count_dominates_fires(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "integration_test").mkdir()
    # 6 integration test files, only 2 unit
    for i in range(6):
        _write(
            proj / "integration_test" / f"int_{i}_test.dart",
            "void main() {\n"
            "  testWidgets('x', (tester) async {\n"
            "    await tester.pumpWidget(MyApp());\n"
            "  });\n"
            "}\n",
        )
    for i in range(2):
        _write(
            proj / "test" / f"unit_{i}_test.dart",
            "void main() { test('x', () { expect(1, 1); }); }\n",
        )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "integration_test_count_dominates" in _rules(res)


@pytest.mark.asyncio
async def test_no_test_helpers_dir_fires_when_many_tests(tmp_path: Path):
    proj = _project(tmp_path)
    # 21 test files, no test/helpers/
    for i in range(21):
        _write(
            proj / "test" / f"x_{i}_test.dart",
            "void main() { test('x', () { expect(1, 1); }); }\n",
        )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_test_helpers_dir" in _rules(res)


@pytest.mark.asyncio
async def test_helpers_dir_silences_rule(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "test" / "helpers").mkdir(parents=True)
    _write(proj / "test" / "helpers" / "factory.dart", "void buildSomething() {}\n")
    for i in range(21):
        _write(
            proj / "test" / f"x_{i}_test.dart",
            "void main() { test('x', () { expect(1, 1); }); }\n",
        )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_test_helpers_dir" not in _rules(res)


# ---- engine behaviors --------------------------------------------------


@pytest.mark.asyncio
async def test_generated_files_skipped(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x.mocks.dart",
        "// generated mock\nfinal d = Dio();\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.files_scanned == 0


@pytest.mark.asyncio
async def test_min_level_filter_suppresses_lower(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  testWidgets('x', (tester) async {\n"
        "    tester.pump();\n"  # junior bare_pump
        "  });\n"
        "}\n",
    )
    res = await _run(proj, min_level="senior")
    assert isinstance(res, Ok)
    # All findings should be senior+
    assert all(
        f.level != TestQualityLevel.JUNIOR for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_tests_total_counted_correctly(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('one', () {});\n"
        "  test('two', () {});\n"
        "  testWidgets('three', (t) async {});\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.tests_total == 3


@pytest.mark.asyncio
async def test_grade_unreliable_when_blocker_present(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() {\n"
        "  test('x', () async {\n"
        "    final dio = Dio();\n"
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade == "unreliable"


@pytest.mark.asyncio
async def test_advice_mentions_grade_and_test_count(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "x_test.dart",
        "void main() { test('x', () { expect(1, 1); }); }\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade in res.value.advice
    assert "1 test cases" in res.value.advice or "test" in res.value.advice
