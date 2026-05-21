# Code-Seniority Rubric

> Companion document to the **`audit_code_seniority`** MCP tool.
> Shipped as part of `mcp-phone-controll` v0.3.0 phase 7.

This document explains the rubric `audit_code_seniority` applies
when grading a Flutter codebase. It exists so reviewers can argue
with the linter — every rule has a stated rationale, severity,
and citation. Disagree? Pick a different `min_level` or skip the
rule in your team's wrapper.

## What the tool answers

`flutter analyze` answers: *does this compile and pass the lints
the Dart team chose?*

`audit_code_seniority` answers: *does this look like it was
written by a senior?* That's a different question. Some code is
syntactically perfect and architecturally junior. Some code looks
sloppy but encodes deep domain knowledge. The rubric tries to
catch the former without flagging the latter.

## Why pure regex

The rules are intentionally shallow. They catch what a reviewer
notices in the first 5 seconds of opening a file. Deeper semantic
checks belong in:

- `dart_analyze` — type & null-safety errors
- `custom_lint` packages — project-specific AST rules
- Code review by a human — actual judgment

This tool is the layer in between. It runs in <1 second on a 50k
LOC codebase and gives the human reviewer a list of *what to look
at first*.

## Decision tree: which `min_level` to use

```
Code under review is...
├── A teammate's PR you're about to approve
│   └── min_level="junior"   (catch everything)
│
├── A large legacy codebase you just inherited
│   └── min_level="senior"   (skip noise; focus on architecture)
│
├── A pre-release audit of mission-critical code
│   └── min_level="junior" + autofix=True
│       (then review the preview_diffs by hand)
│
└── Your own feature branch, mid-development
    └── min_level="mid"      (skip pedantic junior smells)
```

## Grade thresholds

Score = weighted findings per KLOC.

| Score | Grade | Meaning |
|---|---|---|
| < 2 | `staff` | Clean. Defensible at architecture review. |
| 2 – 5 | `senior` | Solid. A few rough spots, no architectural debt. |
| 5 – 10 | `mid` | Working code with consistent smells. Refactor candidates exist. |
| 10 – 20 | `junior` | Multiple architectural patterns missing. Needs review. |
| > 20 | `needs_review` | Linter doesn't have enough signal to grade. Open the files. |

Severity weights: blocker = 10, serious = 4, minor = 1.

## The 24 rules

### Tier 1 — Junior smells (6 rules)

These catch patterns a junior developer would still ship; a
mid-level dev catches them in their own diff before opening the
PR.

#### `print_in_lib` — **serious**
Bare `print(...)` calls in `lib/`. `print` doesn't get stripped
from release builds, so this leaks to production logs. Use
`debugPrint` guarded by `kDebugMode` instead — or better, a
proper logger.

**Standard:** Effective Dart — AVOID print calls in production.

#### `magic_numbers` — **minor**
A widget file with 5+ distinct hardcoded layout numbers in
`EdgeInsets`/`SizedBox`/`Padding`. Extract to design tokens
(`AppSpacing.s8`, `AppSpacing.s16`) so the design system is
discoverable.

**Standard:** Material Design 4dp/8dp grid system.

#### `setstate_in_stateless` — **blocker**
`setState(...)` called in a `StatelessWidget`. It compiles to a
runtime error. Either convert to `StatefulWidget` or move state
into a Bloc/Cubit.

#### `untitled_todo` — **minor**
A `TODO` comment without owner+date. Use
`// TODO(name, YYYY-MM-DD): ...` so future-you knows when this
was punted.

**Standard:** Effective Dart — DO use TODO comments with owner.

#### `double_question_mark` — **minor**
`?? null` (no-op) or `!!.` (two consecutive force-unwraps). Both
indicate confusion about null-safety semantics.

#### `bang_on_nullable` — **minor**
Catches some patterns of force-unwrap on a freshly-nullable
expression — weak heuristic; tune your team's expectations.

### Tier 2 — Mid-level oversights (6 rules)

Patterns a 2-year dev would still write, but a senior would not.

#### `business_logic_in_widget` — **serious**
Dio/Firebase/HTTP call inside a Widget file (matched by
`*_page.dart` / `*_screen.dart` / `*_widget.dart` / `*_view.dart`).
Move to a repository; let the Bloc dispatch.

**Standard:** Clean Architecture — Presentation → Domain ← Data.

#### `missing_dispose` — **blocker**
`StatefulWidget` that declares a `Controller` / `StreamSubscription`
/ `Timer` field but doesn't override `dispose()`. Memory leak;
animation handles stay attached after the widget unmounts.

**Standard:** Flutter docs — `State.dispose()` lifecycle.

#### `throw_in_repo` — **serious**
`throw` statement in a file matching `*_repository.dart`. Project
convention (CLAUDE.md): repos return `Either<Failure, T>`. Wrap
the throw in `try/catch` and return `Left(Failure(...))`.

#### `deep_nesting` — **minor**
`build()` method reaches more than 5 levels of nested braces.
Flatten with private `_buildXxx()` methods or stateless
sub-widgets.

#### `god_widget` — **serious**
`build()` method exceeds 150 LOC. Extract sub-widgets — build
methods should rarely exceed 80 LOC.

**Standard:** Flutter docs — keep build methods small.

#### `blocking_io_in_build` — **serious**
Synchronous file I/O inside `build()`. Hangs the UI thread.

### Tier 3 — Senior-level architecture (6 rules)

This is the tier the rubric is calibrated for. A senior eye
catches these in code review without thinking.

#### `missing_key_param` — **minor**
Public Widget constructor without `super.key`. Breaks Flutter's
widget reordering optimizations.

**Standard:** flutter_lints — `use_key_in_widget_constructors`.

*Autofixable:* yes — adds `super.key,` to the constructor.

#### `no_base_class` — **serious**
A `Bloc` or `Cubit` class that doesn't extend the project's
`BaseBloc` / `BaseCubit`. Project convention (CLAUDE.md): all
Blocs extend a Base class for cross-cutting concerns (logging,
trace IDs, etc.).

#### `no_either_return` — **serious**
A repository interface method that returns `Future<T>` instead
of `Future<Either<Failure, T>>`. Either pattern is the project's
non-negotiable error-handling convention.

#### `orphan_source` — **minor**
A `lib/*.dart` file with no corresponding `*_test.dart` anywhere
under `test/`. Excluded: entities, models, failures, main.dart —
these are often legitimately untested.

#### `direct_di_lookup` — **serious**
`GetIt.I<X>()` / `getIt<X>()` outside `core/di/` or `injection/`.
Use constructor injection in business code; the service-locator
should only be touched from DI bootstrap.

#### `debugprint_in_release` — **minor**
`debugPrint(...)` not guarded by `kDebugMode` / `kReleaseMode`.
`debugPrint` is NOT stripped in release; it just throttles. Wrap
it.

### Tier 4 — Staff-level layering (5 rules)

Architectural invariants. A staff-level reviewer enforces these
because violations rot the codebase over time.

#### `presentation_imports_data` — **blocker**
A file under `/presentation/` imports from a `/data/` path. This
bypasses the domain layer and violates the Clean Architecture
dependency rule.

#### `data_imports_presentation` — **blocker**
A file under `/data/` imports from `/presentation/`. The
dependency rule says data must not know about UI.

#### `cross_feature_data_import` — **serious**
Feature A imports Feature B's `data/` layer directly. Module
boundaries are broken. Route through a domain interface.

#### `monolithic_bloc` — **minor**
A Bloc handling 6+ distinct event types. Single Responsibility
violation; split it by sub-domain.

#### `repo_in_widget` — **blocker**
`Repository` class instantiated directly in a widget. The widget
owns a data source. Inject via DI instead.

## What this tool is NOT

- **Not a replacement for `flutter analyze`.** Run that first.
- **Not a correctness checker.** A "junior smell" doesn't mean
  the code is broken — it means it looks like a junior wrote it.
- **Not an auto-refactor tool.** Even with `autofix=True`, only
  mechanical, single-line fixes are proposed. The deeper rules
  return `fix_hint` only.
- **Not project-agnostic.** The senior-tier rules encode Clean
  Architecture + flutter_bloc + Either patterns this project
  follows. A team on a different stack would tune the rule set.

## Using the tool

```python
# Full audit with autofix preview
result = audit_code_seniority(
    project_path="/path/to/project",
    min_level="junior",     # catch everything
    autofix=True,           # populate preview_diffs
)

# Read the grade
print(result.grade)         # "senior"
print(result.advice)        # one-line PR-comment summary
print(result.top_actions)   # 5 highest-impact fixes
```

For a single feature scope:

```python
result = audit_code_seniority(
    project_path="/path/to/project",
    paths=["lib/features/auth"],
    min_level="senior",     # legacy-friendly
)
```

## Integration with `recommend_test_path`

The advisor surfaces `audit_code_seniority` as the cheapest
step in the **pre_pr** path — it runs in <1 second and surfaces
the architectural smells worth catching before code review burns
human cycles. Pair them:

1. `audit_code_seniority` — *what does this code look like?*
2. `propose_test_scenarios` — *what should I test?*
3. `recommend_test_path` — *how do I run those tests safely?*

All three are pure compute. Zero device interaction. Safe to run
on a battery-powered laptop in under a minute.

## Tuning the rubric for your team

If your codebase doesn't follow Clean Architecture or doesn't use
Either, the senior-tier rules will fire constantly. Either:

- Raise `min_level` to `"staff"` to suppress them, OR
- Wrap the tool and filter out specific rule names in your
  team's MCP adapter.

The rubric is opinionated on purpose — it encodes a specific
target architecture. That's what makes the grade meaningful.
