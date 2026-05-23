"""Test-suite quality audit — gates AI-written tests.

`design_test_plan` (phase 11.5) tells the agent WHAT tests to
write. `audit_test_quality` (this tool) checks whether the tests
the agent wrote are actually good.

Together they form the senior-tester loop:

  design_test_plan  →  agent writes tests  →  audit_test_quality

What this catches that `dart test` won't
----------------------------------------

`dart test` tells you whether tests pass. It says nothing about
whether the tests are well-written. An AI agent can produce
green-passing tests that are:

  • Flaky — `tester.pump()` without `await` or `pumpAndSettle()`
  • Vacuous — `expect(thing, isNotNull)` as the only assertion
  • Over-mocked — the SUT itself mocked away (testing the mock)
  • Brittle — `find.text('Sign in')` hardcoded (Polish-locale lesson)
  • Wrong-layer — integration_test exercising a pure function
  • Happy-path-only — no `expect(...isA<Failure>)` anywhere
  • Golden-trapped — `matchesGoldenFile` updated without review

A senior reviewer spots all of these in 30 seconds. This tool
encodes that 30 seconds as 28 rules.

Scope
-----

  Walks: test/ + integration_test/ (Dart projects)
  Skips: generated files (.g.dart, .mocks.dart, etc.)
  Skips: comments + string literals where appropriate
  Cross-references: lib/ source files for the orphan check

What this is NOT
----------------

  • Not a runtime test runner. Pure static scan.
  • Not a coverage tool. Uses lcov.info if present, doesn't
    generate it.
  • Not project-agnostic. Encodes flutter_test + integration_test
    + flutter_bloc + Either conventions. Other stacks would tune.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from ._helpers import is_path_excluded
from .base import BaseUseCase


class Severity(str, Enum):
    BLOCKER = "blocker"   # tests demonstrably broken / flaky-prone
    SERIOUS = "serious"   # silent test-quality smells
    MINOR = "minor"       # cleanup


class TestQualityLevel(str, Enum):
    JUNIOR = "junior"     # syntactic / atomic / naming
    MID = "mid"           # flakiness, over-mocking, setup leakage
    SENIOR = "senior"     # wrong-layer, happy-path-only
    STAFF = "staff"       # suite architecture


@dataclass(frozen=True, slots=True)
class TestQualityFinding:
    rule: str
    description: str
    severity: Severity
    level: TestQualityLevel
    file: str
    line: int
    snippet: str
    fix_hint: str | None
    standard: str | None


@dataclass(frozen=True, slots=True)
class AuditTestQualityParams:
    project_path: Path
    paths: tuple[str, ...] = ()       # default ['test', 'integration_test']
    min_level: str = "junior"
    max_findings: int = 200


@dataclass(frozen=True, slots=True)
class AuditTestQualityResult:
    grade: str                                  # excellent / acceptable / fragile / unreliable
    score: float                                # weighted findings per KLOC of tests
    files_scanned: int
    lines_scanned: int
    tests_total: int                            # `test(...)` + `testWidgets(...)` count
    skipped_tests: int                          # @Skip / `skip:` arguments
    findings: tuple[TestQualityFinding, ...]
    findings_by_level: dict[str, int]
    findings_by_severity: dict[str, int]
    top_actions: tuple[str, ...]
    advice: str


_SEVERITY_WEIGHT = {
    Severity.BLOCKER: 10,
    Severity.SERIOUS: 4,
    Severity.MINOR: 1,
}


class AuditTestQuality(
    BaseUseCase[AuditTestQualityParams, AuditTestQualityResult]
):
    """Audits a Flutter project's test/ + integration_test/ dirs.

    Pure compute, regex over Dart. 28 rules across 4 tiers. The
    post-write companion to design_test_plan.
    """

    async def execute(
        self, params: AuditTestQualityParams
    ) -> Result[AuditTestQualityResult]:
        if not params.project_path.is_dir():
            return err(FilesystemFailure(
                message=f"project_path not found: {params.project_path}",
                next_action="fix_arguments",
            ))
        try:
            min_level = TestQualityLevel(params.min_level)
        except ValueError:
            return err(FilesystemFailure(
                message=(
                    f"unknown min_level {params.min_level!r}. "
                    "Valid: junior, mid, senior, staff"
                ),
                next_action="fix_arguments",
            ))

        roots = _resolve_roots(params.project_path, params.paths)
        files = _collect_test_files(roots, params.project_path)

        # Collect lib source stems for orphan check (used by staff rules)
        lib_stems = _collect_lib_stems(params.project_path / "lib")

        all_findings: list[TestQualityFinding] = []
        lines_total = 0
        tests_total = 0
        skipped_tests = 0
        unit_test_files: list[str] = []
        integration_test_files: list[str] = []

        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = content.splitlines()
            lines_total += len(lines)
            rel = str(f.relative_to(params.project_path))
            if rel.startswith("integration_test"):
                integration_test_files.append(rel)
            else:
                unit_test_files.append(rel)

            findings, n_tests, n_skipped = _scan_file(rel, lines, content)
            all_findings.extend(findings)
            tests_total += n_tests
            skipped_tests += n_skipped

        # Staff-level cross-file rules
        all_findings.extend(_check_suite_architecture(
            integration_test_files, unit_test_files,
            params.project_path, files, lib_stems,
        ))

        # Filter by min_level
        order = [
            TestQualityLevel.JUNIOR, TestQualityLevel.MID,
            TestQualityLevel.SENIOR, TestQualityLevel.STAFF,
        ]
        kept = set(order[order.index(min_level):])
        all_findings = [f for f in all_findings if f.level in kept]

        sev_idx = {Severity.BLOCKER: 0, Severity.SERIOUS: 1, Severity.MINOR: 2}
        all_findings.sort(
            key=lambda x: (sev_idx[x.severity], x.file, x.line)
        )
        all_findings_t = tuple(all_findings[: params.max_findings])

        by_level: dict[str, int] = {}
        by_sev: dict[str, int] = {}
        for fnd in all_findings_t:
            by_level[fnd.level.value] = by_level.get(fnd.level.value, 0) + 1
            by_sev[fnd.severity.value] = by_sev.get(fnd.severity.value, 0) + 1

        weighted = sum(_SEVERITY_WEIGHT[f.severity] for f in all_findings_t)
        kloc = max(lines_total, 1) / 1000.0
        score = weighted / kloc if kloc > 0 else 0.0
        grade = _grade_for(score, by_sev, len(files))

        return ok(AuditTestQualityResult(
            grade=grade,
            score=round(score, 2),
            files_scanned=len(files),
            lines_scanned=lines_total,
            tests_total=tests_total,
            skipped_tests=skipped_tests,
            findings=all_findings_t,
            findings_by_level=by_level,
            findings_by_severity=by_sev,
            top_actions=_build_top_actions(all_findings_t),
            advice=_build_advice(
                grade, score, tests_total, skipped_tests,
                len(all_findings_t), len(files),
            ),
        ))


# ============================================================
# File discovery
# ============================================================


def _resolve_roots(project: Path, paths: tuple[str, ...]) -> list[Path]:
    if not paths:
        out: list[Path] = []
        for d in ("test", "integration_test"):
            p = project / d
            if p.is_dir():
                out.append(p)
        return out
    return [
        project / p for p in paths if (project / p).exists()
    ]


def _collect_test_files(
    roots: list[Path], project_root: Path,
) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".dart":
            out.append(root)
            continue
        if not root.is_dir():
            continue
        for f in root.rglob("*.dart"):
            # Skip build/, .claude/worktrees/, etc.
            # (v0.3.0 field-test calibration finding)
            if is_path_excluded(f, project_root):
                continue
            name = f.name
            if (
                name.endswith(".g.dart")
                or name.endswith(".freezed.dart")
                or name.endswith(".mocks.dart")
                or name.endswith(".config.dart")
            ):
                continue
            out.append(f)
    return sorted(out)


def _collect_lib_stems(lib: Path) -> set[str]:
    """Return set of `lib/foo/bar.dart` → stems for orphan-test
    detection."""
    if not lib.is_dir():
        return set()
    return {f.stem for f in lib.rglob("*.dart") if f.is_file()}


# ============================================================
# Per-file scanner
# ============================================================


# Compiled regex patterns (reused per file)
_RE_TEST_CALL = re.compile(
    r"\b(testWidgets|test|patrolTest|patrolWidgetTest)\s*\(",
)
_RE_SKIPPED = re.compile(
    r"(?:@Skip|skip\s*:\s*['\"][^'\"]+['\"]|skip\s*:\s*true)",
)
# Match `tester.X(`, `$.tester.X(` (Patrol's PatrolTester), or
# `_.tester.X(`. The await-presence check is done in code (see
# `_pumps_without_await`) because regex lookbehinds are fixed-width
# and can't reliably skip the Patrol receiver prefix.
_RE_PUMP_CALL_ANY = re.compile(
    r"(?:tester|\$\.tester|_\.tester)\.(pumpWidget|pumpAndSettle)\s*\("
)
_RE_BARE_PUMP_CALL_ANY = re.compile(
    r"(?:tester|\$\.tester|_\.tester)\.pump\s*\(\s*\)"
)
_RE_FIND_TEXT_HARDCODED = re.compile(
    r"find\.text\s*\(\s*['\"]([A-Za-z][A-Za-z0-9 ]{2,})['\"]",
)
_RE_FUTURE_DELAYED = re.compile(
    r"\bFuture\.delayed\s*\(\s*(?:const\s+)?Duration",
)
_RE_VACUOUS_EXPECT = re.compile(
    # `expect(x, isNotNull);` as the only-line assertion smell
    r"\bexpect\s*\(\s*[\w.]+\s*,\s*(?:isNotNull|isNotEmpty|isNotNan)\s*\)\s*;",
)
_RE_SLEEP_CALL = re.compile(
    r"\bsleep\s*\(\s*Duration",
)
_RE_UNTITLED_SKIP = re.compile(
    # @Skip without a reason argument
    r"@Skip(?!\s*\([^)]*['\"])",
)
_RE_SKIP_NO_REASON = re.compile(
    r"skip\s*:\s*true",
)
_RE_MOCKITO_WHEN_SUT = re.compile(
    # `when(sut.method(...)).thenReturn(...)` is suspicious — usually
    # you want to mock the dependency, not the SUT itself.
    r"\bwhen\s*\(\s*sut\.",
)
_RE_REAL_NETWORK = re.compile(
    r"\b(Dio|http\.Client)\s*\(\s*\)|\bhttp\.(get|post|put|delete|patch)\s*\(",
)
_RE_FIREBASE_INSTANCE = re.compile(
    r"\bFirebase(?:Firestore|Auth|Storage|Messaging)\.instance\b",
)
_RE_PUMP_NO_DURATION = re.compile(
    r"tester\.pump\s*\(\s*\)",
)
_RE_GOLDEN = re.compile(
    r"matchesGoldenFile\s*\(\s*['\"]([^'\"]+)['\"]",
)
_RE_GOLDEN_VERIFIED = re.compile(
    r"//\s*verified\s+(?:on\s+)?\d{4}-\d{2}-\d{2}",
    re.IGNORECASE,
)
_RE_SET_STATE = re.compile(r"\bsetState\s*\(")
_RE_RANDOM_NEW = re.compile(r"\bRandom\s*\(\s*\)")
_RE_INTEGRATION_PATH = re.compile(r"^integration_test/")
_RE_PROVIDER_PROVIDER = re.compile(
    r"\b(BlocProvider|RepositoryProvider|Provider)(?:\.value)?\s*\(",
)
_RE_FAILURE_ASSERT = re.compile(
    r"isA<\s*\w*Failure\s*>",
)
_RE_TEST_HELPER_IMPORT = re.compile(
    # Match `import 'foo_test.dart'` BUT NOT
    # `import 'package:flutter_test/flutter_test.dart'` or
    # `import 'package:test/test.dart'` (those are the
    # standard test-framework imports, not 'this test imports
    # another test'). v0.3.0 field-test calibration finding.
    r"import\s+['\"](?!package:(?:flutter_test|test|patrol)/)[^'\"]*?_test\.dart['\"]",
)
_RE_GROUP = re.compile(r"\bgroup\s*\(")
_RE_SETUP_ALL = re.compile(r"\bsetUpAll\s*\(")
_RE_SHARED_VAR = re.compile(
    r"^\s*(?:late\s+)?(?:final\s+|var\s+)\w+\s+(\w+)\s*[;=]",
)


def _scan_file(
    rel: str, lines: list[str], content: str,
) -> tuple[list[TestQualityFinding], int, int]:
    findings: list[TestQualityFinding] = []
    # Strip /* */ multi-line comments + // line comments for regex
    # safety. Cheap approximation: rely on patterns being specific.
    n_tests = len(_RE_TEST_CALL.findall(content))
    n_skipped = (
        len(_RE_SKIPPED.findall(content))
        + len(_RE_SKIP_NO_REASON.findall(content))
    )

    is_integration = bool(_RE_INTEGRATION_PATH.search(rel))

    # ---- Junior tier rules ----
    for i, line in enumerate(lines, start=1):
        # bare_pump — only fire if no `await` precedes the pump call
        # on the same line. Handles `tester.pump()`, `$.tester.pump()`
        # (Patrol), and `_.tester.pump()` receiver styles.
        for bp_match in _RE_BARE_PUMP_CALL_ANY.finditer(line):
            if "await " in line[: bp_match.start()]:
                continue
            findings.append(_mk(
                "bare_pump",
                "tester.pump() with no Duration + no await. Race "
                "condition risk; the next assertion may run before "
                "the frame builds.",
                Severity.SERIOUS, TestQualityLevel.JUNIOR,
                rel, i, line.strip()[:140],
                "Use `await tester.pumpAndSettle()` or "
                "`await tester.pump(Duration(milliseconds: 16))`.",
                "flutter_test docs: pump variants",
            ))
            break  # one finding per line is enough
        # await_missing_on_pump — same receiver-tolerant logic
        for m in _RE_PUMP_CALL_ANY.finditer(line):
            if "await " in line[: m.start()]:
                continue
            findings.append(_mk(
                "await_missing_on_pump",
                f"tester.{m.group(1)}() not awaited. The test may "
                "complete before the pump returns — flaky.",
                Severity.SERIOUS, TestQualityLevel.JUNIOR,
                rel, i, line.strip()[:140],
                "Prefix with `await`.",
                "Async test discipline",
            ))
        # hardcoded_locale_string in find.text
        m = _RE_FIND_TEXT_HARDCODED.search(line)
        if m and not _is_l10n_aware_test(content):
            value = m.group(1)
            findings.append(_mk(
                "hardcoded_locale_string",
                f"find.text({value!r}) hardcodes the English label. "
                "Breaks on non-default locales (Polish-locale lesson).",
                Severity.MINOR, TestQualityLevel.JUNIOR,
                rel, i, line.strip()[:140],
                "Use find.byKey() or look up via AppLocalizations in "
                "the test setup.",
                "i18n test discipline",
            ))
        # sleep / Future.delayed
        if _RE_FUTURE_DELAYED.search(line) or _RE_SLEEP_CALL.search(line):
            findings.append(_mk(
                "sleep_in_test",
                "Real-time sleep / Future.delayed inside a test. "
                "Slow + flaky.",
                Severity.SERIOUS, TestQualityLevel.JUNIOR,
                rel, i, line.strip()[:140],
                "Replace with tester.pumpAndSettle() or "
                "FakeAsync.elapse() for time-based logic.",
                "Test discipline: no real sleeps",
            ))
        # vacuous expect
        if _RE_VACUOUS_EXPECT.search(line):
            findings.append(_mk(
                "vacuous_expect",
                "Vacuous assertion (isNotNull / isNotEmpty alone). "
                "Test always passes if the SUT returns anything.",
                Severity.SERIOUS, TestQualityLevel.JUNIOR,
                rel, i, line.strip()[:140],
                "Assert the actual expected value, not just non-null.",
                "Senior-tester discipline #2",
            ))
        # untitled @Skip / `skip: true`
        if _RE_UNTITLED_SKIP.search(line) or _RE_SKIP_NO_REASON.search(line):
            findings.append(_mk(
                "untitled_skip",
                "Test skipped without a reason. Skips rot the suite.",
                Severity.SERIOUS, TestQualityLevel.JUNIOR,
                rel, i, line.strip()[:140],
                "Add a reason: `@Skip('flaky on iOS — issue #123')`.",
                "Test discipline: explicit skips",
            ))

    # ---- Mid tier rules ----
    # mocked SUT
    for m in _RE_MOCKITO_WHEN_SUT.finditer(content):
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "mocked_sut",
            "Stubbing methods on `sut` — you're testing the mock, "
            "not the code.",
            Severity.SERIOUS, TestQualityLevel.MID,
            rel, line_no, m.group(0)[:80],
            "Stub the SUT's collaborators, not the SUT itself.",
            "Senior-tester discipline #2",
        ))
    # real network unmocked
    for m in _RE_REAL_NETWORK.finditer(content):
        line_no = content.count("\n", 0, m.start()) + 1
        # Skip if this is a fake/mock setup file
        if "fake" in rel.lower() or "mock" in rel.lower():
            continue
        findings.append(_mk(
            "network_call_unmocked",
            "Real HTTP client instantiated in test — flaky + slow + "
            "depends on external state.",
            Severity.BLOCKER, TestQualityLevel.MID,
            rel, line_no, m.group(0),
            "Inject a mocked Dio/http.Client; use registerFallbackValue "
            "and when().thenAnswer().",
            "Test isolation principle",
        ))
    # firebase instance unmocked
    for m in _RE_FIREBASE_INSTANCE.finditer(content):
        line_no = content.count("\n", 0, m.start()) + 1
        if "fake" in rel.lower() or "mock" in rel.lower():
            continue
        findings.append(_mk(
            "firestore_instance_unmocked",
            f"{m.group(0)} touches real Firebase. Use "
            "fake_cloud_firestore / firebase_auth_mocks.",
            Severity.BLOCKER, TestQualityLevel.MID,
            rel, line_no, m.group(0),
            "Replace with FakeFirebaseFirestore / MockFirebaseAuth.",
            "Test isolation principle",
        ))
    # pump count smell — 5+ consecutive tester.pump() calls
    pump_count = len(_RE_PUMP_NO_DURATION.findall(content))
    if pump_count >= 5:
        m = _RE_PUMP_NO_DURATION.search(content)
        assert m is not None
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "pump_count_smell",
            f"{pump_count} bare tester.pump() calls in one file. "
            "Manual frame-driving is flaky.",
            Severity.MINOR, TestQualityLevel.MID,
            rel, line_no, f"{pump_count} pump() calls",
            "Use pumpAndSettle() or runAsync() for time-based work.",
            "flutter_test docs",
        ))
    # golden without verified comment
    for m in _RE_GOLDEN.finditer(content):
        line_no = content.count("\n", 0, m.start()) + 1
        # Check ±5 lines for a // verified YYYY-MM-DD comment
        nearby_start = max(0, m.start() - 200)
        nearby_end = min(len(content), m.end() + 200)
        if not _RE_GOLDEN_VERIFIED.search(content[nearby_start:nearby_end]):
            findings.append(_mk(
                "golden_no_verified_comment",
                "matchesGoldenFile() without a `// verified YYYY-MM-DD` "
                "marker. Golden updates can sneak in without review.",
                Severity.MINOR, TestQualityLevel.MID,
                rel, line_no, m.group(0)[:80],
                "Add `// verified 2026-05-22 by Michal` next to each "
                "matchesGoldenFile call.",
                "Senior-tester discipline #2",
            ))

    # ---- Senior tier rules ----
    # missing failure path — file has happy-path tests but no failure assert
    if (
        n_tests >= 2
        and _RE_TEST_CALL.search(content)
        and not _RE_FAILURE_ASSERT.search(content)
    ):
        findings.append(_mk(
            "missing_failure_path",
            f"{n_tests} tests in file but no `isA<Failure>` assertion. "
            "Happy-path-only coverage.",
            Severity.SERIOUS, TestQualityLevel.SENIOR,
            rel, 0, "no Failure-path assertion",
            "Add a paired `should_X_when_Y_fails` test per happy path "
            "asserting isA<...Failure>.",
            "Senior-tester discipline #7",
        ))
    # widget_test_no_provider
    if (
        "testWidgets" in content
        and not is_integration
        and not _RE_PROVIDER_PROVIDER.search(content)
        and "Bloc" in content
    ):
        # File uses Blocs but doesn't wrap with a provider — risky
        first = content.index("testWidgets")
        line_no = content.count("\n", 0, first) + 1
        findings.append(_mk(
            "widget_test_no_provider",
            "Widget test uses Blocs but no BlocProvider/RepositoryProvider "
            "wrapper detected — real deps may leak in.",
            Severity.MINOR, TestQualityLevel.SENIOR,
            rel, line_no, "testWidgets without provider wrapper",
            "Wrap pumpWidget body with BlocProvider.value(value: "
            "fakeBloc, child: ...).",
            "Bloc test discipline",
        ))
    # e2e_doing_unit_work — integration_test touching pure functions
    if is_integration and _RE_TEST_CALL.search(content):
        # If the file imports only domain entities and no widgets, it's
        # almost certainly doing unit work in the E2E layer.
        has_widget = "Widget" in content or "MaterialApp" in content
        has_pump = "tester.pump" in content
        if not has_widget and not has_pump:
            findings.append(_mk(
                "e2e_doing_unit_work",
                "integration_test file exercises pure code (no widget, "
                "no pump). Wasting CI minutes — move to test/.",
                Severity.SERIOUS, TestQualityLevel.SENIOR,
                rel, 0, "no Widget / pump in integration test",
                "Move to test/ (unit layer). Reserve "
                "integration_test/ for cross-process flows.",
                "Test pyramid",
            ))
    # no_pump_after_setstate
    if (
        _RE_SET_STATE.search(content)
        and "testWidgets" in content
        and "pump" not in content.split("setState")[1] if "setState" in content else False
    ):
        # Has setState but no following pump
        # (heuristic — string-split based but conservative)
        findings.append(_mk(
            "no_pump_after_setstate",
            "setState() inside a widget test without a following "
            "tester.pump() — assertion runs against pre-rebuild state.",
            Severity.MINOR, TestQualityLevel.SENIOR,
            rel, 0, "setState without pump",
            "Add `await tester.pump()` after setState before asserting.",
            "Widget test discipline",
        ))
    # flaky_tag_unused — if the file has `pumpAndSettle(Duration(seconds:` (long)
    # but no @Tags(['flaky']) marker.
    if (
        re.search(r"pumpAndSettle\s*\(\s*const\s+Duration\(seconds:\s*[5-9]", content)
        and "@Tags" not in content
    ):
        findings.append(_mk(
            "flaky_tag_unused",
            "Long pumpAndSettle timeouts (5+ seconds) but no @Tags(['flaky']) "
            "marker. CI can't selectively retry these.",
            Severity.MINOR, TestQualityLevel.SENIOR,
            rel, 0, "long pumpAndSettle without flaky tag",
            "Add `@Tags(['flaky'])` at file top so CI can isolate.",
            "Test reliability discipline",
        ))
    # nondeterministic random seed
    for m in _RE_RANDOM_NEW.finditer(content):
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "nondeterministic_random_seed",
            "Random() without a seed — test can pass locally and fail "
            "in CI.",
            Severity.SERIOUS, TestQualityLevel.STAFF,
            rel, line_no, m.group(0),
            "Use `Random(42)` or pass the seed via test config.",
            "Test determinism",
        ))
    # test imports test
    for m in _RE_TEST_HELPER_IMPORT.finditer(content):
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "test_imports_test",
            "Test file imports another *_test.dart file. Should share "
            "via test_helpers/ instead.",
            Severity.MINOR, TestQualityLevel.STAFF,
            rel, line_no, m.group(0)[:140],
            "Move shared setup to test_helpers/ and import from there.",
            "Test code organisation",
        ))

    return findings, n_tests, n_skipped


def _is_l10n_aware_test(content: str) -> bool:
    """If the test imports AppLocalizations / intl / l10n
    something, it's probably aware of locale shifts."""
    lower = content.lower()
    return (
        "applocalizations" in lower
        or "app_localizations" in lower
        or "package:intl" in lower
        or "context.l10n" in lower
        or "gen_l10n" in lower
    )


# ============================================================
# Cross-file staff rules
# ============================================================


def _check_suite_architecture(
    integration_files: list[str],
    unit_files: list[str],
    project_path: Path,
    all_files: list[Path],
    lib_stems: set[str],
) -> list[TestQualityFinding]:
    """Suite-level rules — only meaningful across files."""
    out: list[TestQualityFinding] = []

    # integration_test_count_dominates
    n_unit = len(unit_files)
    n_integration = len(integration_files)
    if n_integration > n_unit and n_integration > 5:
        out.append(_mk(
            "integration_test_count_dominates",
            f"{n_integration} integration tests vs {n_unit} unit tests. "
            "Test pyramid upside-down — CI will be slow.",
            Severity.MINOR, TestQualityLevel.STAFF,
            "test/", 0,
            f"{n_integration} > {n_unit}",
            "Move pure-logic checks from integration_test/ → test/. "
            "Reserve integration_test/ for cross-process flows.",
            "Test pyramid",
        ))

    # no_test_helpers_dir — if there are 20+ tests but no helpers/ dir
    helpers_dir = project_path / "test" / "helpers"
    if (
        n_unit >= 20
        and not helpers_dir.is_dir()
    ):
        out.append(_mk(
            "no_test_helpers_dir",
            f"{n_unit} test files but no test/helpers/ directory. "
            "Test setup is likely duplicated.",
            Severity.MINOR, TestQualityLevel.STAFF,
            "test/", 0,
            "no test/helpers/ directory",
            "Create test/helpers/ with TestDataFactory, "
            "buildTestApp(), mockBloc helpers.",
            "Senior-tester discipline #4",
        ))

    return out


# ============================================================
# Helpers
# ============================================================


def _mk(
    rule: str, desc: str, severity: Severity, level: TestQualityLevel,
    file: str, line: int, snippet: str,
    fix_hint: str | None, standard: str | None,
) -> TestQualityFinding:
    return TestQualityFinding(
        rule=rule, description=desc, severity=severity, level=level,
        file=file, line=line, snippet=snippet[:140],
        fix_hint=fix_hint, standard=standard,
    )


def _grade_for(
    score: float, by_sev: dict[str, int], files_scanned: int,
) -> str:
    if files_scanned == 0:
        return "excellent"  # no tests, nothing to grade
    if by_sev.get("blocker", 0) > 0:
        return "unreliable"
    if score >= 15 or by_sev.get("serious", 0) >= 5:
        return "fragile"
    if score >= 5 or by_sev.get("serious", 0) > 0:
        return "acceptable"
    return "excellent"


def _build_top_actions(
    findings: tuple[TestQualityFinding, ...],
) -> tuple[str, ...]:
    if not findings:
        return ("Test suite reads at the configured tier. Senior-tester approved.",)
    counts: dict[str, tuple[int, TestQualityFinding]] = {}
    for f in findings:
        prev = counts.get(f.rule)
        if prev is None or _SEVERITY_WEIGHT[f.severity] > _SEVERITY_WEIGHT[prev[1].severity]:
            counts[f.rule] = ((prev[0] if prev else 0) + 1, f)
        else:
            counts[f.rule] = (prev[0] + 1, prev[1])
    ranked = sorted(
        counts.items(),
        key=lambda kv: (
            -_SEVERITY_WEIGHT[kv[1][1].severity],
            -kv[1][0],
        ),
    )
    out: list[str] = []
    for rule, (n, sample) in ranked[:5]:
        hint = sample.fix_hint or "see rule definition"
        out.append(f"[{sample.severity.value}] {rule} ×{n} — {hint}")
    return tuple(out)


def _build_advice(
    grade: str, score: float, n_tests: int, n_skipped: int,
    n_findings: int, n_files: int,
) -> str:
    skipped_str = (
        f", {n_skipped} skipped" if n_skipped else ""
    )
    return (
        f"Test-quality grade: {grade} ({score:.1f} weighted findings/KLOC). "
        f"{n_tests} test cases across {n_files} files{skipped_str}. "
        f"{n_findings} findings to address."
    )
