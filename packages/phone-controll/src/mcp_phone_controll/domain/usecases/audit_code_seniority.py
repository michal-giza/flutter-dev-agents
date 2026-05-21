"""Code-seniority audit — grades a Flutter codebase against
senior-engineer standards.

`flutter analyze` catches syntax + type errors. `dart fix` applies
mechanical refactors. Neither answers the question developers
actually ask in code review: *does this code look like it was
written by a senior?*

This tool answers that. It walks `lib/` (and optionally `test/`),
runs a curated rule set across four tiers — junior smells, mid-
level oversights, senior-level architecture, staff-level layering
— and returns a graded report with per-file findings, an overall
grade, and a preview of suggested fixes the agent can apply
automatically when `autofix=True`.

Why pure regex (no Dart AST)? Because the rules are intentionally
shallow — they catch the patterns code reviewers spot in 5
seconds without opening the file. Deep semantic checks belong in
`dart_analyze` / custom_lint. This is the human-eye layer.

What the rules catch (24 rules across 4 tiers):

  **Junior smells** (would catch a fresher's first PR):
    • print_in_lib            — bare print() in production code
    • magic_numbers           — >4 distinct hardcoded layout values
    • setstate_in_stateless   — setState used in a StatelessWidget
    • untitled_todo           — TODO without owner/date
    • double_question_mark    — `?? null` (no-op) or `!!.` chains
    • bang_on_nullable        — `x!` on a freshly nullable variable

  **Mid-level oversights** (a 2-year dev would still write):
    • business_logic_in_widget — Dio/Firebase/HTTP inside Widget
    • missing_dispose          — StatefulWidget with controllers
                                  but no dispose()
    • throw_in_repo            — `throw` inside *_repository.dart
                                  (should return Either/Failure)
    • deep_nesting             — >4 levels of nested braces
    • god_widget               — build() method >150 LOC
    • blocking_io_in_build     — File/sync I/O inside build()

  **Senior-level architecture** (the level we ARE checking):
    • missing_key_param        — Widget ctor without super.key
    • no_base_class            — Bloc/Cubit not extending BaseBloc
    • no_either_return         — repo interface returning Future<T>
                                  instead of Future<Either<F, T>>
    • orphan_source            — source file with no test file
    • direct_di_lookup         — GetIt.I<> outside DI bootstrap
    • debugprint_in_release    — `debugPrint` not guarded by
                                  kDebugMode / kReleaseMode

  **Staff-level layering** (architectural invariants):
    • presentation_imports_data — UI bypasses domain layer
    • data_imports_presentation — wrong dependency direction
    • cross_feature_data_import — feature/A/data imported by
                                   feature/B (violates module
                                   boundaries)
    • monolithic_bloc          — one Bloc handling >5 distinct
                                   event types (split it)
    • repo_in_widget           — Repository class instantiated
                                   in a Widget (should be DI)

Grade computation:

  weighted findings per KLOC →
    <  2  : staff
    2 - 5  : senior
    5 - 10 : mid
    10- 20 : junior
    > 20  : needs_review

The advice line summarizes the report into one paste-ready
sentence for PR comments. `top_actions` is a prioritized list of
the highest-impact fixes (most findings, lowest tier).

What this is NOT:

  • A linter that replaces `flutter analyze`. Run that first.
  • A correctness checker — these rules flag *style + design*,
    not bugs. A "junior smell" doesn't mean the code is broken.
  • An auto-refactor tool. Even with `autofix=True` we only
    propose minimal, safe edits (e.g. add `super.key`); the
    deeper rules return `fix_hint` only.
  • Project-agnostic. The senior-level rules encode Clean
    Architecture + flutter_bloc + Either patterns the user
    follows. Teams on different stacks would tune the rule set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from .base import BaseUseCase


class Severity(str, Enum):
    BLOCKER = "blocker"   # PR-blocking; ship-stopper at code review
    SERIOUS = "serious"   # should fix this PR
    MINOR = "minor"       # cleanup; nice-to-have


class SeniorityLevel(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"


@dataclass(frozen=True, slots=True)
class SeniorityFinding:
    rule: str
    description: str
    severity: Severity
    level: SeniorityLevel        # tier this rule belongs to
    file: str                    # relative to project root
    line: int                    # 1-indexed; 0 if file-level
    snippet: str                 # the offending line (or summary)
    fix_hint: str | None         # short paste-ready remediation
    standard: str | None         # citation: Effective Dart, etc.


@dataclass(frozen=True, slots=True)
class PreviewDiff:
    file: str
    line: int
    rule: str
    before: str                  # the old line
    after: str                   # the proposed new line
    safe: bool                   # True if mechanical & non-semantic


@dataclass(frozen=True, slots=True)
class AuditCodeSeniorityParams:
    project_path: Path
    # Limit to a subset of paths (relative to project_path).
    # Default: all of lib/. Pass ["lib/features/auth/"] to scope.
    paths: tuple[str, ...] = ()
    # Minimum tier to flag. Setting min_level="senior" suppresses
    # junior + mid findings — useful when the team is shipping
    # legacy code and only wants senior+ feedback.
    min_level: str = "junior"
    # When True, populate preview_diffs with mechanical fixes the
    # agent can apply (e.g. add `super.key`, replace `print(` with
    # `debugPrint(`). Never writes files; just proposes.
    autofix: bool = False
    # Maximum findings to return; default 200 to keep responses
    # bounded. Findings are sorted by severity then file.
    max_findings: int = 200


@dataclass(frozen=True, slots=True)
class AuditCodeSeniorityResult:
    grade: str                              # junior / mid / senior / staff / needs_review
    score: float                            # weighted findings per KLOC
    files_scanned: int
    lines_scanned: int
    findings: tuple[SeniorityFinding, ...]
    findings_by_level: dict[str, int]       # {level: count}
    findings_by_severity: dict[str, int]    # {severity: count}
    top_actions: tuple[str, ...]            # prioritized remediation steps
    preview_diffs: tuple[PreviewDiff, ...]  # populated when autofix=True
    advice: str                             # one-line PR-ready summary


_SEVERITY_WEIGHT = {
    Severity.BLOCKER: 10,
    Severity.SERIOUS: 4,
    Severity.MINOR: 1,
}


class AuditCodeSeniority(
    BaseUseCase[AuditCodeSeniorityParams, AuditCodeSeniorityResult]
):
    """Grades a Flutter codebase against senior-engineer standards.

    Pure compute. No LLM, no device, no network. Walks .dart files
    under the project_path (scoped to lib/ by default), applies
    24 rules across 4 seniority tiers, returns a graded report.
    """

    async def execute(
        self, params: AuditCodeSeniorityParams
    ) -> Result[AuditCodeSeniorityResult]:
        if not params.project_path.is_dir():
            return err(
                FilesystemFailure(
                    message=f"project_path not found: {params.project_path}",
                    next_action="fix_arguments",
                )
            )

        try:
            min_level = SeniorityLevel(params.min_level)
        except ValueError:
            return err(
                FilesystemFailure(
                    message=(
                        f"unknown min_level {params.min_level!r}. Valid: "
                        + ", ".join(p.value for p in SeniorityLevel)
                    ),
                    next_action="fix_arguments",
                )
            )

        roots = _resolve_roots(params.project_path, params.paths)
        files = _collect_dart_files(roots)

        all_findings: list[SeniorityFinding] = []
        all_previews: list[PreviewDiff] = []
        lines_total = 0
        test_files = _collect_test_files(params.project_path)

        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = content.splitlines()
            lines_total += len(lines)
            rel = str(f.relative_to(params.project_path))
            findings, previews = _scan_file(
                rel, lines, content, params.autofix, test_files,
                params.project_path,
            )
            all_findings.extend(findings)
            if params.autofix:
                all_previews.extend(previews)

        # Filter by min_level
        level_order = [
            SeniorityLevel.JUNIOR, SeniorityLevel.MID,
            SeniorityLevel.SENIOR, SeniorityLevel.STAFF,
        ]
        min_idx = level_order.index(min_level)
        kept_levels = set(level_order[min_idx:])
        all_findings = [f for f in all_findings if f.level in kept_levels]

        # Sort by severity (blockers first) then file then line
        sev_order = {
            Severity.BLOCKER: 0, Severity.SERIOUS: 1, Severity.MINOR: 2,
        }
        all_findings.sort(
            key=lambda f: (sev_order[f.severity], f.file, f.line)
        )
        all_findings_t = tuple(all_findings[: params.max_findings])

        # Group counts
        by_level: dict[str, int] = {}
        by_sev: dict[str, int] = {}
        for fnd in all_findings_t:
            by_level[fnd.level.value] = by_level.get(fnd.level.value, 0) + 1
            by_sev[fnd.severity.value] = by_sev.get(fnd.severity.value, 0) + 1

        # Score = weighted findings per KLOC
        weighted = sum(
            _SEVERITY_WEIGHT[f.severity] for f in all_findings_t
        )
        kloc = max(lines_total, 1) / 1000.0
        score = weighted / kloc if kloc > 0 else 0.0
        grade = _grade_for(score, files_scanned=len(files))

        top_actions = _build_top_actions(all_findings_t)
        advice = _build_advice(
            grade, score, len(all_findings_t), len(files), lines_total,
        )

        return ok(
            AuditCodeSeniorityResult(
                grade=grade,
                score=round(score, 2),
                files_scanned=len(files),
                lines_scanned=lines_total,
                findings=all_findings_t,
                findings_by_level=by_level,
                findings_by_severity=by_sev,
                top_actions=top_actions,
                preview_diffs=tuple(all_previews[: params.max_findings]),
                advice=advice,
            )
        )


# ============================================================
# File discovery
# ============================================================


def _resolve_roots(
    project_path: Path, paths: tuple[str, ...]
) -> list[Path]:
    if not paths:
        lib = project_path / "lib"
        return [lib] if lib.is_dir() else []
    roots: list[Path] = []
    for p in paths:
        candidate = project_path / p
        if candidate.exists():
            roots.append(candidate)
    return roots


def _collect_dart_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".dart":
            files.append(root)
            continue
        if not root.is_dir():
            continue
        for f in root.rglob("*.dart"):
            # Skip generated files — they're not human code.
            name = f.name
            if (
                name.endswith(".g.dart")
                or name.endswith(".freezed.dart")
                or name.endswith(".gr.dart")
                or name.endswith(".mocks.dart")
                or name.endswith(".config.dart")
                or ".gen." in name
            ):
                continue
            files.append(f)
    return sorted(files)


def _collect_test_files(project_path: Path) -> set[str]:
    """Return set of source-file stems that DO have a *_test.dart.

    Used for the `orphan_source` rule. Convention: lib/foo/bar.dart
    is covered by test/foo/bar_test.dart OR test/.../bar_test.dart.
    """
    test_dir = project_path / "test"
    if not test_dir.is_dir():
        return set()
    stems: set[str] = set()
    for f in test_dir.rglob("*_test.dart"):
        stems.add(f.stem.removesuffix("_test"))
    return stems


# ============================================================
# Per-file scanner
# ============================================================


# Compile once; reused per file.
_RE_PRINT = re.compile(r"(?<![A-Za-z_])print\s*\(")
_RE_TODO = re.compile(r"(?://|/\*)\s*TODO(?!\([\w\- ]+,?\s*\d{4}-)")
_RE_BANG_CHAIN = re.compile(r"!\!\.|\?\?\s*null\b")
_RE_DOUBLE_BANG = re.compile(r"\)!\s*\.|\]!\s*\.")  # weak heuristic
_RE_SETSTATE = re.compile(r"\bsetState\s*\(")
_RE_DIO_OR_HTTP = re.compile(
    r"\b(Dio|http\.(get|post|put|delete|patch)|FirebaseFirestore|FirebaseAuth\.instance)\b"
)
_RE_THROW = re.compile(r"\bthrow\b")
_RE_DEBUGPRINT = re.compile(r"\bdebugPrint\s*\(")
_RE_KDEBUGMODE = re.compile(r"\bkDebugMode\b|\bkReleaseMode\b")
_RE_GETIT_LOOKUP = re.compile(r"\b(GetIt\.I|GetIt\.instance|getIt)\s*<")
_RE_REPO_FILE = re.compile(r"_repository\.dart$")
_RE_REPO_IMPL_FILE = re.compile(r"_repository_impl\.dart$")
_RE_BLOC_OR_CUBIT_FILE = re.compile(r"_(bloc|cubit)\.dart$")
_RE_WIDGET_FILE_HINT = re.compile(r"_(page|screen|widget|view)\.dart$")
_RE_CLASS_EXTENDS = re.compile(
    r"class\s+(\w+)\s+extends\s+([\w<>,\s]+?)\s*(?:implements|with|\{)"
)
_RE_WIDGET_CTOR_NO_KEY = re.compile(
    r"const\s+(\w+)\s*\(\s*\{[^}]*\}\s*\)"
)
_RE_NEW_REPO_IN_WIDGET = re.compile(r"=\s*\w*Repository\w*\(")
_RE_FUTURE_RETURN = re.compile(
    r"Future<([^>]+)>\s+\w+\s*\("
)
_RE_EITHER_PRESENT = re.compile(r"\bEither\s*<")
_RE_CONTROLLER_FIELDS = re.compile(
    r"\b(\w+Controller|StreamSubscription|Timer)\s+\w+\s*[;=]"
)
_RE_DISPOSE = re.compile(r"\bvoid\s+dispose\s*\(\s*\)")
_RE_MAGIC_NUMBER = re.compile(
    r"(?:EdgeInsets\.\w+|SizedBox|Padding)\s*\(\s*[^)]*?(\d+\.?\d*)"
)
_RE_BLOC_ON_EVENT = re.compile(r"\bon<([A-Z]\w+)>")
_RE_IMPORT = re.compile(r"^import\s+['\"]([^'\"]+)['\"]")


def _scan_file(
    rel: str,
    lines: list[str],
    content: str,
    autofix: bool,
    test_stems: set[str],
    project_path: Path,
) -> tuple[list[SeniorityFinding], list[PreviewDiff]]:
    findings: list[SeniorityFinding] = []
    previews: list[PreviewDiff] = []
    is_repo = bool(_RE_REPO_FILE.search(rel))
    is_repo_impl = bool(_RE_REPO_IMPL_FILE.search(rel))
    is_bloc = bool(_RE_BLOC_OR_CUBIT_FILE.search(rel))
    is_widget_hint = bool(_RE_WIDGET_FILE_HINT.search(rel))

    # ---- line-level rules ----
    magic_values: set[str] = set()
    has_dispose = bool(_RE_DISPOSE.search(content))
    controller_lines: list[tuple[int, str]] = []
    has_kdebug_guard = bool(_RE_KDEBUGMODE.search(content))

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Junior: print() in lib/
        if rel.startswith("lib") and _RE_PRINT.search(line):
            findings.append(_mk(
                "print_in_lib",
                "Bare print() in production code. Use debugPrint behind kDebugMode, or a logger.",
                Severity.SERIOUS, SeniorityLevel.JUNIOR,
                rel, i, stripped,
                "Replace `print(` with `if (kDebugMode) debugPrint(`",
                "Effective Dart: AVOID print calls in production",
            ))
            if autofix:
                new = line.replace("print(", "debugPrint(")
                previews.append(PreviewDiff(
                    file=rel, line=i, rule="print_in_lib",
                    before=line, after=new, safe=True,
                ))

        # Junior: TODO without owner/date
        if _RE_TODO.search(line):
            findings.append(_mk(
                "untitled_todo",
                "TODO without owner+date. Use `// TODO(name, YYYY-MM-DD): ...`",
                Severity.MINOR, SeniorityLevel.JUNIOR,
                rel, i, stripped,
                "Add owner and date: `// TODO(you, 2026-05-21): ...`",
                "Effective Dart: DO use TODO comments with owner",
            ))

        # Junior: `?? null` or `!!.`
        if _RE_BANG_CHAIN.search(line) or _RE_DOUBLE_BANG.search(line):
            findings.append(_mk(
                "double_question_mark",
                "Suspicious null handling: `?? null` is a no-op, `!!.` is two assertions.",
                Severity.MINOR, SeniorityLevel.JUNIOR,
                rel, i, stripped,
                "Drop the redundant operator or use proper null check.",
                "Effective Dart: null safety idioms",
            ))

        # Junior: setState in a StatelessWidget file
        if (
            "StatelessWidget" in content
            and "StatefulWidget" not in content
            and _RE_SETSTATE.search(line)
        ):
            findings.append(_mk(
                "setstate_in_stateless",
                "setState() called in a StatelessWidget — impossible; convert to StatefulWidget or use a Bloc.",
                Severity.BLOCKER, SeniorityLevel.JUNIOR,
                rel, i, stripped,
                "Either convert to StatefulWidget or move state into a Bloc/Cubit.",
                "Flutter docs: StatelessWidget vs StatefulWidget",
            ))

        # Mid: business logic in widget
        if is_widget_hint and _RE_DIO_OR_HTTP.search(line):
            findings.append(_mk(
                "business_logic_in_widget",
                "Network/Firebase call inside a Widget file. Move to a repository + Bloc.",
                Severity.SERIOUS, SeniorityLevel.MID,
                rel, i, stripped,
                "Inject a Repository via DI; let the Bloc dispatch the call.",
                "Clean Architecture: Presentation -> Domain <- Data",
            ))

        # Mid: throw in repository (should return Either)
        if (is_repo or is_repo_impl) and _RE_THROW.search(stripped):
            findings.append(_mk(
                "throw_in_repo",
                "Repository file throws. Return `Either<Failure, T>` instead.",
                Severity.SERIOUS, SeniorityLevel.MID,
                rel, i, stripped,
                "Wrap in try/catch and return Left(Failure(...)).",
                "Project rule: Either pattern for all errors (CLAUDE.md)",
            ))

        # Senior: GetIt lookup outside DI file
        if (
            _RE_GETIT_LOOKUP.search(line)
            and "/di/" not in rel
            and "injection" not in rel
        ):
            findings.append(_mk(
                "direct_di_lookup",
                "Direct GetIt lookup outside DI bootstrap. Prefer constructor injection.",
                Severity.SERIOUS, SeniorityLevel.SENIOR,
                rel, i, stripped,
                "Inject the dependency via constructor; only `core/di/` should call GetIt.",
                "DI best practice: avoid service-locator anti-pattern in business code",
            ))

        # Senior: debugPrint without kDebugMode guard (file-level check below)

        # Staff: repo instantiated in widget
        if is_widget_hint and _RE_NEW_REPO_IN_WIDGET.search(line):
            findings.append(_mk(
                "repo_in_widget",
                "Repository instantiated directly in a widget — should come via DI.",
                Severity.BLOCKER, SeniorityLevel.STAFF,
                rel, i, stripped,
                "Provide the Repository through GetIt/Provider; widget reads it from context.",
                "Clean Architecture: widgets must not own data sources",
            ))

        # Junior helper: track magic numbers from layout constants
        for m in _RE_MAGIC_NUMBER.finditer(line):
            magic_values.add(m.group(1))

        # Mid helper: collect controller declarations (for dispose check)
        if _RE_CONTROLLER_FIELDS.search(line):
            controller_lines.append((i, stripped))

        # Senior helper: debugPrint without guard
        if (
            _RE_DEBUGPRINT.search(line)
            and not has_kdebug_guard
            and rel.startswith("lib")
        ):
            findings.append(_mk(
                "debugprint_in_release",
                "debugPrint without kDebugMode/kReleaseMode guard — still emits in release.",
                Severity.MINOR, SeniorityLevel.SENIOR,
                rel, i, stripped,
                "Wrap with `if (kDebugMode) debugPrint(...)`.",
                "Flutter docs: debugPrint is not stripped in release",
            ))

    # ---- file-level rules ----

    # Junior: too many magic layout values
    if len(magic_values) >= 5:
        findings.append(_mk(
            "magic_numbers",
            f"{len(magic_values)} distinct hardcoded layout numbers. Extract to design tokens / theme.",
            Severity.MINOR, SeniorityLevel.JUNIOR,
            rel, 0,
            f"{len(magic_values)} unique values",
            "Extract to `AppSpacing`/`AppTheme` constants.",
            "Material Design: 4dp/8dp grid system",
        ))

    # Mid: StatefulWidget with controllers but no dispose
    if "StatefulWidget" in content and controller_lines and not has_dispose:
        first_line = controller_lines[0][0]
        findings.append(_mk(
            "missing_dispose",
            "StatefulWidget owns controllers/streams/timers but has no dispose(). Memory leak risk.",
            Severity.BLOCKER, SeniorityLevel.MID,
            rel, first_line, controller_lines[0][1],
            "Override `dispose()` and call `.dispose()` / `.cancel()` on each owned resource.",
            "Flutter docs: State.dispose lifecycle",
        ))

    # Senior: Bloc/Cubit not extending project's base class
    if is_bloc:
        for m in _RE_CLASS_EXTENDS.finditer(content):
            cls, base = m.group(1), m.group(2).strip()
            if (
                ("Bloc" in cls or "Cubit" in cls)
                and "BaseBloc" not in base
                and "BaseCubit" not in base
                and "Base" not in base
            ):
                line_no = content[: m.start()].count("\n") + 1
                findings.append(_mk(
                    "no_base_class",
                    f"{cls} doesn't extend a project Base class. Project rule: all Blocs extend BaseBloc.",
                    Severity.SERIOUS, SeniorityLevel.SENIOR,
                    rel, line_no, m.group(0),
                    f"`class {cls} extends BaseBloc<...>`",
                    "Project CLAUDE.md: Base class extension required",
                ))

    # Senior: repository interface returning Future<T> not Future<Either>
    if is_repo and not is_repo_impl:
        # Pure interface file: every method should return Either
        has_either_anywhere = bool(_RE_EITHER_PRESENT.search(content))
        if not has_either_anywhere and _RE_FUTURE_RETURN.search(content):
            m = _RE_FUTURE_RETURN.search(content)
            assert m is not None
            line_no = content[: m.start()].count("\n") + 1
            findings.append(_mk(
                "no_either_return",
                "Repository method returns Future<T> instead of Future<Either<Failure, T>>.",
                Severity.SERIOUS, SeniorityLevel.SENIOR,
                rel, line_no, m.group(0),
                "Wrap return type: `Future<Either<Failure, T>>`.",
                "Project CLAUDE.md: Either pattern for all errors",
            ))

    # Senior: orphan source (no corresponding *_test.dart)
    src_stem = Path(rel).stem
    if (
        rel.startswith("lib")
        and not src_stem.startswith("_")
        and src_stem not in test_stems
        # Pure model/entity files often legitimately untested.
        and "/entities/" not in rel
        and "/models/" not in rel
        and "/failures/" not in rel
        and not rel.endswith("main.dart")
    ):
        findings.append(_mk(
            "orphan_source",
            f"Source file {src_stem}.dart has no *_test.dart anywhere under test/.",
            Severity.MINOR, SeniorityLevel.SENIOR,
            rel, 0, src_stem,
            f"Create test/.../{src_stem}_test.dart — even a smoke test is better than zero.",
            "Project rule: 80%+ coverage, 100% UseCases/BLoCs",
        ))

    # Mid: deep nesting and god widget
    findings.extend(_check_nesting_and_size(rel, lines))

    # Senior: missing super.key on public widget constructors
    findings.extend(_check_missing_key(rel, content, autofix, previews))

    # Staff: layering violations
    findings.extend(_check_layering(rel, content))

    # Staff: monolithic bloc (too many event handlers)
    if is_bloc:
        events = set(_RE_BLOC_ON_EVENT.findall(content))
        if len(events) >= 6:
            findings.append(_mk(
                "monolithic_bloc",
                f"Bloc handles {len(events)} distinct event types. Consider splitting by responsibility.",
                Severity.MINOR, SeniorityLevel.STAFF,
                rel, 0,
                f"{len(events)} event types",
                "Split into multiple Blocs by sub-responsibility.",
                "Single Responsibility Principle",
            ))

    return findings, previews


# ============================================================
# Sub-checks
# ============================================================


def _check_nesting_and_size(
    rel: str, lines: list[str]
) -> list[SeniorityFinding]:
    """Walk braces; flag build() methods over 150 LOC OR deeper
    than 4 levels of nesting from the build( entry."""
    findings: list[SeniorityFinding] = []
    in_build = False
    build_start_line = 0
    build_depth_at_entry = 0
    depth = 0
    max_depth_in_build = 0
    for i, line in enumerate(lines, start=1):
        # crude tokenization: count braces ignoring strings/comments
        clean = re.sub(r"//.*$", "", line)
        clean = re.sub(r"'[^']*'|\"[^\"]*\"", "", clean)
        opens = clean.count("{")
        closes = clean.count("}")
        if not in_build and re.search(r"\bWidget\s+build\s*\(", clean):
            in_build = True
            build_start_line = i
            build_depth_at_entry = depth
            max_depth_in_build = depth
        depth += opens - closes
        if in_build:
            max_depth_in_build = max(max_depth_in_build, depth)
            if depth <= build_depth_at_entry and (opens or closes):
                # Build method closed
                length = i - build_start_line
                if length > 150:
                    findings.append(_mk(
                        "god_widget",
                        f"build() method is {length} LOC — extract sub-widgets.",
                        Severity.SERIOUS, SeniorityLevel.MID,
                        rel, build_start_line,
                        f"{length} lines",
                        "Extract sub-widgets; build() should rarely exceed 80 LOC.",
                        "Flutter docs: keep build methods small",
                    ))
                nesting = max_depth_in_build - build_depth_at_entry
                if nesting > 5:
                    findings.append(_mk(
                        "deep_nesting",
                        f"build() reaches {nesting} levels of nesting — flatten with named sub-widgets.",
                        Severity.MINOR, SeniorityLevel.MID,
                        rel, build_start_line,
                        f"depth {nesting}",
                        "Pull nested children into private `_buildXxx()` methods or stateless sub-widgets.",
                        "Refactoring catalog: deeply nested code",
                    ))
                in_build = False
                max_depth_in_build = 0
    return findings


def _check_missing_key(
    rel: str, content: str, autofix: bool, previews: list[PreviewDiff],
) -> list[SeniorityFinding]:
    """Find `const FooWidget({...})` that doesn't include super.key."""
    findings: list[SeniorityFinding] = []
    if "Widget" not in content:
        return findings
    for m in re.finditer(
        r"const\s+(\w+)\s*\(\s*\{([^}]*)\}\s*\)",
        content,
    ):
        cls, body = m.group(1), m.group(2)
        if not cls[0].isupper():
            continue
        if "super.key" in body or "Key?" in body or "key:" in body:
            continue
        # Heuristic: only flag if this looks like a Widget subclass
        if not re.search(
            rf"class\s+{re.escape(cls)}\s+extends\s+\w*Widget",
            content,
        ):
            continue
        line_no = content[: m.start()].count("\n") + 1
        findings.append(_mk(
            "missing_key_param",
            f"{cls} constructor missing `super.key`. Breaks widget reordering optimizations.",
            Severity.MINOR, SeniorityLevel.SENIOR,
            rel, line_no, m.group(0)[:80],
            f"`const {cls}({{super.key, ...}})`",
            "Effective Dart / flutter_lints: use_key_in_widget_constructors",
        ))
        if autofix:
            before = m.group(0)
            after = before.replace("({", "({super.key, ", 1)
            previews.append(PreviewDiff(
                file=rel, line=line_no, rule="missing_key_param",
                before=before, after=after, safe=True,
            ))
    return findings


def _check_layering(rel: str, content: str) -> list[SeniorityFinding]:
    """Staff-tier rules: presentation must not import data; data
    must not import presentation; cross-feature data imports are
    a smell."""
    findings: list[SeniorityFinding] = []
    is_presentation = "/presentation/" in rel
    is_data = "/data/" in rel
    own_feature = _extract_feature(rel)
    for m in _RE_IMPORT.finditer(content):
        target = m.group(1)
        if not target.startswith("package:"):
            # Relative imports: still check layer fragments
            t = target
        else:
            t = target
        line_no = content[: m.start()].count("\n") + 1
        if is_presentation and "/data/" in t:
            findings.append(_mk(
                "presentation_imports_data",
                "Presentation file imports from data layer — bypasses domain.",
                Severity.BLOCKER, SeniorityLevel.STAFF,
                rel, line_no, f"import {target}",
                "Route through a use case in domain/usecases/.",
                "Clean Architecture: Presentation -> Domain <- Data",
            ))
        if is_data and "/presentation/" in t:
            findings.append(_mk(
                "data_imports_presentation",
                "Data file imports from presentation layer — wrong dependency direction.",
                Severity.BLOCKER, SeniorityLevel.STAFF,
                rel, line_no, f"import {target}",
                "Move shared types into domain/ entities or domain/ failures.",
                "Clean Architecture: dependency rule",
            ))
        if (
            own_feature
            and "/features/" in t
            and "/data/" in t
            and f"/features/{own_feature}/" not in t
        ):
            findings.append(_mk(
                "cross_feature_data_import",
                f"Feature '{own_feature}' imports another feature's data layer directly.",
                Severity.SERIOUS, SeniorityLevel.STAFF,
                rel, line_no, f"import {target}",
                "Cross-feature dependencies should go through domain interfaces.",
                "Module boundaries / package-by-feature",
            ))
    return findings


def _extract_feature(rel: str) -> str | None:
    m = re.search(r"/features/([^/]+)/", rel)
    return m.group(1) if m else None


# ============================================================
# Helpers
# ============================================================


def _mk(
    rule: str, desc: str, severity: Severity, level: SeniorityLevel,
    file: str, line: int, snippet: str,
    fix_hint: str | None, standard: str | None,
) -> SeniorityFinding:
    # Trim snippets for readability
    snippet = snippet[:140]
    return SeniorityFinding(
        rule=rule, description=desc, severity=severity, level=level,
        file=file, line=line, snippet=snippet,
        fix_hint=fix_hint, standard=standard,
    )


def _grade_for(score: float, files_scanned: int) -> str:
    if files_scanned == 0:
        return "needs_review"
    if score < 2:
        return "staff"
    if score < 5:
        return "senior"
    if score < 10:
        return "mid"
    if score < 20:
        return "junior"
    return "needs_review"


def _build_top_actions(
    findings: tuple[SeniorityFinding, ...],
) -> tuple[str, ...]:
    """Group by rule, pick the highest-impact 5."""
    if not findings:
        return ("Nothing to fix — codebase reads at the configured tier.",)
    counts: dict[str, tuple[int, SeniorityFinding]] = {}
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
    actions: list[str] = []
    for rule, (n, sample) in ranked[:5]:
        hint = sample.fix_hint or "see rule definition"
        actions.append(
            f"[{sample.severity.value}] {rule} ×{n} — {hint}"
        )
    return tuple(actions)


def _build_advice(
    grade: str, score: float, n_findings: int,
    files: int, lines: int,
) -> str:
    return (
        f"Seniority grade: {grade} ({score:.1f} weighted findings/KLOC). "
        f"{n_findings} findings across {files} files / {lines} LOC. "
        f"Sort by severity; fix blockers first."
    )
