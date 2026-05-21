"""Tests for the v0.3.0 phase-7 code-seniority audit.

The tool walks lib/*.dart with 24 regex rules grouped by tier
(junior/mid/senior/staff) and grades the codebase. These tests
build small fixture trees on tmp_path, then assert each rule
fires on a known-bad sample and stays silent on a known-good
sample.

What we validate:

- Each rule fires on a known-bad fixture (positive case).
- Each rule does NOT fire on a known-good fixture (no false
  positives in obviously clean code).
- Generated files (.g.dart, .freezed.dart) are skipped.
- Overall grade computation is deterministic given the same
  source tree.
- Severity ordering of findings is blocker -> serious -> minor.
- `min_level` filter actually filters.
- `autofix=True` populates preview_diffs only with safe
  mechanical fixes.
- Missing project_path returns fix_arguments.
- Invalid min_level returns fix_arguments.
- Layering rules detect presentation -> data imports.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.audit_code_seniority import (
    AuditCodeSeniority,
    AuditCodeSeniorityParams,
    SeniorityLevel,
    Severity,
)

# ---- fixture helpers ---------------------------------------------------


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    """Create an empty Flutter-shaped project."""
    (tmp_path / "lib").mkdir()
    return tmp_path


async def _run(
    project: Path, **kwargs
) -> Ok | Err:
    return await AuditCodeSeniority()(
        AuditCodeSeniorityParams(project_path=project, **kwargs)
    )


def _rules(res: Ok) -> set[str]:
    return {f.rule for f in res.value.findings}


# ---- happy path --------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_project_returns_clean_grade(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "main.dart",
        "void main() {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.files_scanned == 1
    assert res.value.findings == ()
    assert res.value.grade in ("staff", "senior")
    assert "Nothing to fix" in res.value.top_actions[0]


@pytest.mark.asyncio
async def test_missing_project_path_returns_typed_failure(tmp_path: Path):
    res = await _run(tmp_path / "does_not_exist")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_invalid_min_level_returns_typed_failure(tmp_path: Path):
    proj = _project(tmp_path)
    res = await _run(proj, min_level="principal")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ---- JUNIOR-tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_print_in_lib_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "stuff.dart",
        "void doit() { print('hello'); }\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "print_in_lib" in _rules(res)


@pytest.mark.asyncio
async def test_print_in_lib_does_not_fire_on_clean_file(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "clean.dart",
        "import 'package:flutter/foundation.dart';\n"
        "void doit() { if (kDebugMode) debugPrint('hi'); }\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "print_in_lib" not in _rules(res)


@pytest.mark.asyncio
async def test_untitled_todo_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "wip.dart",
        "// TODO: refactor this later\nvoid noop() {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "untitled_todo" in _rules(res)


@pytest.mark.asyncio
async def test_well_formed_todo_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "wip.dart",
        "// TODO(michal, 2026-05-21): refactor\nvoid noop() {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "untitled_todo" not in _rules(res)


@pytest.mark.asyncio
async def test_setstate_in_stateless_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "bad.dart",
        "import 'package:flutter/material.dart';\n"
        "class Bad extends StatelessWidget {\n"
        "  @override\n"
        "  Widget build(BuildContext context) {\n"
        "    setState(() {});\n"
        "    return Container();\n"
        "  }\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    rules = _rules(res)
    assert "setstate_in_stateless" in rules
    # Severity must be blocker for this one
    sev = next(
        f.severity for f in res.value.findings
        if f.rule == "setstate_in_stateless"
    )
    assert sev == Severity.BLOCKER


# ---- MID-tier rules ----------------------------------------------------


@pytest.mark.asyncio
async def test_business_logic_in_widget_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "features" / "auth" / "presentation" / "login_page.dart",
        "import 'package:dio/dio.dart';\n"
        "class LoginPage {\n"
        "  void login() { Dio().get('/auth'); }\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "business_logic_in_widget" in _rules(res)


@pytest.mark.asyncio
async def test_throw_in_repo_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "user_repository.dart",
        "class UserRepository {\n"
        "  Future<User> getUser() async {\n"
        "    throw Exception('boom');\n"
        "  }\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "throw_in_repo" in _rules(res)


@pytest.mark.asyncio
async def test_missing_dispose_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "leaky.dart",
        "import 'package:flutter/material.dart';\n"
        "class Leaky extends StatefulWidget {}\n"
        "class _LeakyState extends State<Leaky> {\n"
        "  final TextEditingController controller = TextEditingController();\n"
        "  @override Widget build(BuildContext c) => Container();\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_dispose" in _rules(res)


@pytest.mark.asyncio
async def test_missing_dispose_does_not_fire_with_dispose(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "clean.dart",
        "import 'package:flutter/material.dart';\n"
        "class Clean extends StatefulWidget {}\n"
        "class _CleanState extends State<Clean> {\n"
        "  final TextEditingController controller = TextEditingController();\n"
        "  @override void dispose() { controller.dispose(); super.dispose(); }\n"
        "  @override Widget build(BuildContext c) => Container();\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_dispose" not in _rules(res)


# ---- SENIOR-tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_no_either_return_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "auth_repository.dart",
        "abstract class AuthRepository {\n"
        "  Future<User> signIn(String email);\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_either_return" in _rules(res)


@pytest.mark.asyncio
async def test_either_return_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "auth_repository.dart",
        "abstract class AuthRepository {\n"
        "  Future<Either<Failure, User>> signIn(String email);\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_either_return" not in _rules(res)


@pytest.mark.asyncio
async def test_direct_di_lookup_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "features" / "home" / "home_page.dart",
        "final repo = GetIt.I<UserRepository>();\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "direct_di_lookup" in _rules(res)


@pytest.mark.asyncio
async def test_direct_di_lookup_silent_in_di_folder(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "core" / "di" / "injection.dart",
        "final repo = GetIt.I<UserRepository>();\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "direct_di_lookup" not in _rules(res)


@pytest.mark.asyncio
async def test_missing_key_param_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "card.dart",
        "import 'package:flutter/material.dart';\n"
        "class MyCard extends StatelessWidget {\n"
        "  const MyCard({required this.title});\n"
        "  final String title;\n"
        "  @override Widget build(BuildContext c) => Container();\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_key_param" in _rules(res)


@pytest.mark.asyncio
async def test_missing_key_param_silent_with_super_key(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "card.dart",
        "import 'package:flutter/material.dart';\n"
        "class MyCard extends StatelessWidget {\n"
        "  const MyCard({super.key, required this.title});\n"
        "  final String title;\n"
        "  @override Widget build(BuildContext c) => Container();\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_key_param" not in _rules(res)


@pytest.mark.asyncio
async def test_orphan_source_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(proj / "lib" / "service.dart", "class Service {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "orphan_source" in _rules(res)


@pytest.mark.asyncio
async def test_orphan_source_silent_with_matching_test(tmp_path: Path):
    proj = _project(tmp_path)
    _write(proj / "lib" / "service.dart", "class Service {}\n")
    _write(
        proj / "test" / "service_test.dart",
        "void main() {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "orphan_source" not in _rules(res)


# ---- STAFF-tier rules --------------------------------------------------


@pytest.mark.asyncio
async def test_presentation_imports_data_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "features" / "auth" / "presentation" / "login_page.dart",
        "import 'package:my_app/features/auth/data/repository_impl.dart';\n"
        "class Login {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "presentation_imports_data" in _rules(res)


@pytest.mark.asyncio
async def test_data_imports_presentation_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "features" / "auth" / "data" / "repository_impl.dart",
        "import 'package:my_app/features/auth/presentation/login_page.dart';\n"
        "class RepoImpl {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "data_imports_presentation" in _rules(res)


@pytest.mark.asyncio
async def test_cross_feature_data_import_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "features" / "home" / "presentation" / "home_page.dart",
        "import 'package:my_app/features/auth/data/repository_impl.dart';\n"
        "class Home {}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "cross_feature_data_import" in _rules(res)


@pytest.mark.asyncio
async def test_repo_in_widget_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "home_page.dart",
        "class HomePage {\n"
        "  final repo = UserRepository();\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "repo_in_widget" in _rules(res)


# ---- engine behaviors --------------------------------------------------


@pytest.mark.asyncio
async def test_generated_files_skipped(tmp_path: Path):
    proj = _project(tmp_path)
    # Generated file with violations — must be ignored.
    _write(
        proj / "lib" / "user.g.dart",
        "void main() { print('generated'); }\n",
    )
    _write(
        proj / "lib" / "model.freezed.dart",
        "void main() { print('also generated'); }\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.files_scanned == 0
    assert res.value.findings == ()


@pytest.mark.asyncio
async def test_findings_sorted_by_severity(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "mixed.dart",
        "import 'package:flutter/material.dart';\n"
        "// TODO: cleanup\n"  # minor
        "class Bad extends StatelessWidget {\n"
        "  @override\n"
        "  Widget build(BuildContext c) {\n"
        "    setState(() {});\n"  # blocker
        "    print('x');\n"  # serious
        "    return Container();\n"
        "  }\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    severities = [f.severity for f in res.value.findings]
    # Blocker first, then serious, then minor (within a file)
    sev_idx = {Severity.BLOCKER: 0, Severity.SERIOUS: 1, Severity.MINOR: 2}
    seq = [sev_idx[s] for s in severities]
    assert seq == sorted(seq), f"findings not sorted by severity: {severities}"


@pytest.mark.asyncio
async def test_min_level_filter_suppresses_lower_tiers(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "messy.dart",
        "// TODO: refactor\n"  # junior tier
        "void doit() { print('x'); }\n",  # junior tier
    )
    res = await _run(proj, min_level="senior")
    assert isinstance(res, Ok)
    # All findings are junior tier — should be filtered out.
    assert all(
        f.level != SeniorityLevel.JUNIOR for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_autofix_produces_safe_preview_diffs(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "card.dart",
        "import 'package:flutter/material.dart';\n"
        "class Card extends StatelessWidget {\n"
        "  const Card({required this.title});\n"
        "  final String title;\n"
        "  @override Widget build(BuildContext c) => Container();\n"
        "}\n",
    )
    res = await _run(proj, autofix=True)
    assert isinstance(res, Ok)
    previews = res.value.preview_diffs
    assert len(previews) > 0
    key_fix = next(
        (p for p in previews if p.rule == "missing_key_param"), None
    )
    assert key_fix is not None
    assert key_fix.safe is True
    assert "super.key" in key_fix.after


@pytest.mark.asyncio
async def test_grade_is_one_of_known_tiers(tmp_path: Path):
    proj = _project(tmp_path)
    _write(proj / "lib" / "x.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade in (
        "junior", "mid", "senior", "staff", "needs_review",
    )


@pytest.mark.asyncio
async def test_advice_mentions_grade(tmp_path: Path):
    proj = _project(tmp_path)
    _write(proj / "lib" / "x.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade in res.value.advice


@pytest.mark.asyncio
async def test_top_actions_prioritized_by_severity(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "noisy.dart",
        "import 'package:flutter/material.dart';\n"
        "class Bad extends StatelessWidget {\n"
        "  @override\n"
        "  Widget build(BuildContext c) {\n"
        "    setState(() {});\n"  # blocker
        "    return Container();\n"
        "  }\n"
        "}\n"
        "// TODO: cleanup\n"  # minor
        "// TODO: more cleanup\n"  # minor
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # Blocker rule should rank above minor in top_actions
    assert "[blocker]" in res.value.top_actions[0]


@pytest.mark.asyncio
async def test_paths_filter_restricts_scan(tmp_path: Path):
    proj = _project(tmp_path)
    _write(proj / "lib" / "features" / "auth" / "x.dart", "void main() { print('x'); }\n")
    _write(proj / "lib" / "features" / "home" / "y.dart", "void main() { print('y'); }\n")
    res = await _run(proj, paths=("lib/features/auth",))
    assert isinstance(res, Ok)
    assert res.value.files_scanned == 1
