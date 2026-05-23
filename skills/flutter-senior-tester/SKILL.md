---
name: flutter-senior-tester
description: Senior-tester pre-write + post-write discipline for Flutter / Dart projects. Auto-triggers when planning tests, editing test files, opening pubspec.yaml in a Flutter project, or preparing a PR. Calls `design_test_plan` BEFORE writing tests, `audit_test_quality` AFTER, and `audit_release_readiness` before merge. Enforces the gap protocol — never silently fakes having ACs.
paths:
  - "**/pubspec.yaml"
  - "**/test/**/*.dart"
  - "**/integration_test/**/*.dart"
  - "**/lib/features/**/*.dart"
  - "**/lib/**/use_cases/*.dart"
  - "**/lib/**/usecases/*.dart"
  - "**/lib/**/repositories/*.dart"
  - "**/lib/**/bloc/*.dart"
  - "**/lib/**/cubit/*.dart"
context: fork
---

# Flutter Senior-Tester Discipline

## Purpose

```
┌─────────────────────────────────────────────────────────────────┐
│             FLUTTER SENIOR-TESTER — WHY THIS EXISTS             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Most flaky / shallow Flutter tests come from the same set     │
│   of bad habits:                                                │
│                                                                 │
│   • Writing tests without reading Acceptance Criteria first     │
│   • Bundling 4 asserts into one test "to be efficient"          │
│   • `find.text('Sign in')` (breaks on every non-default locale) │
│   • `tester.pump()` with no Duration and no await               │
│   • Vacuous assertions: `expect(x, isNotNull)` as the only line │
│   • Happy-path-only coverage — no paired failure test           │
│   • Skipped tests with no reason ("// TODO: fix" rotting)       │
│   • Hardcoded shared "the user" leaking state between tests     │
│                                                                 │
│   The senior tester applies a 60-second discipline BEFORE       │
│   writing tests (design) and a 5-second audit AFTER (gate).     │
│   This skill encodes that discipline + auto-invokes the right   │
│   MCP tool at the right moment.                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## When this skill activates

Auto-triggered when the agent is about to:

- Write a new test file under `test/` or `integration_test/`
- Refactor an existing test
- Open `pubspec.yaml` (signals project-level work)
- Edit a use case / repository / Bloc / Cubit (the layers that need paired tests)
- Prepare a PR (gate before merge)

## The 8 principles

The full reference is in `docs/senior-tester-discipline.md`. The
compressed version for in-session use:

1. **AC-first**: start from Acceptance Criteria. Per AC: 1 happy
   path + 2-3 negatives (Equivalence Partitioning) + 2-3
   boundaries (Boundary Value Analysis).
2. **Atomic**: one assertion per test. Independent.
   Sharded-CI safe.
3. **Naming**: `should_X_when_Y` so CI reports read like
   English. Dart: `test('should X when Y', () { ... })` or
   `testWidgets('should X when Y', (tester) async { ... })`.
4. **Test data**: builder pattern / factory. Never a hardcoded
   shared `theUser`. Each test owns its own.
5. **Gherkin discretion**: only if business reads the
   scenarios. In a dev-heavy team, `testWidgets`/`test()` is
   cheaper.
6. **Exploratory ≠ ad-hoc**: charter format with mission +
   time-box + notes. Each session yields 2-3 new automated
   cases.
7. **Cross-cutting = first-class**: a11y / l10n / lifecycle /
   `isA<Failure>` paired tests are baseline — not "if we have
   time."
8. **Gap protocol**: ACs missing? **Proceed but log**. Never
   silently fake having them. Surface
   `notes_for_afterwork` with: *"reverse-engineer ACs from
   implementation; re-run `design_test_plan` against them."*

## Hard rules (always)

1. **NEVER write a test without first calling `design_test_plan`**
   if `mcp-phone-controll` is registered. The plan tells you
   the exact `should_X_when_Y` names + the factories to create
   + what cross-cutting to cover. Skip = junk tests.
2. **NEVER silently ship a test with no failure-path counterpart**.
   For every `should_X_when_Y` happy test, there should be a
   `should_X_when_Y_fails` asserting `isA<Failure>` or the
   matching error envelope.
3. **NEVER use `find.text('English label')` in widget tests**.
   It breaks the day someone switches locale. Use
   `find.byKey()` or look up via `AppLocalizations` in setUp.
4. **STOP if `audit_release_readiness` returns `block`**. Don't
   merge. Read the cross-domain `top_actions`, fix, re-run.

If you ever think "I'll just write the test and check later" —
you have already broken rule #1.

## The two-tool loop

```
       ┌─────────────────────────────────────────────────┐
       │  design_test_plan(...)        ← BEFORE writing  │
       │      ↓                                          │
       │  agent writes tests                             │
       │      ↓                                          │
       │  audit_test_quality(...)      ← AFTER writing   │
       │      ↓                                          │
       │  audit_release_readiness(...) ← BEFORE merge    │
       └─────────────────────────────────────────────────┘
```

### Pre-write: `design_test_plan`

When the user asks for tests for a feature, **start here**:

```python
plan = design_test_plan(
    user_story="As a <role>, I want to <X> so that <Y>",
    acceptance_criteria=(
        "User can sign in with valid credentials",
        "User cannot sign in with invalid credentials",
        "Session persists across app restart",
    ),
    feature_kind="auth",          # auth/form/list/detail/payment/
                                  # settings/onboarding/navigation/
                                  # generic
    team_style="developer_heavy", # or "mixed_with_business"
    time_box_min=60,              # for the exploratory charter
)
```

**Don't have ACs?** Still call the tool. It engages the gap
protocol: synthesises ACs from `feature_kind` heuristics +
populates `gaps[]` and `notes_for_afterwork[]` so the obligation
to revisit is captured.

**Read the plan's:**
- `ac_coverage[].happy_path[].name` — these are your test names
- `ac_coverage[].negative_cases[]` — EP partitions to cover
- `ac_coverage[].boundary_cases[]` — BVA boundaries to cover
- `cross_cutting_required[]` — a11y/l10n/lifecycle to bake in
- `test_data_factories[]` — what to create in `test/helpers/`
- `exploratory_charter` — the session to run after auto tests

### Post-write: `audit_test_quality`

After writing tests, before opening the PR:

```python
audit = audit_test_quality(
    project_path="/path/to/project",
    min_level="junior",   # catch everything
)
```

Read `findings[]` and fix any:
- `bare_pump` / `await_missing_on_pump` — flakiness
- `mocked_sut` — you're testing the mock
- `vacuous_expect` — `isNotNull` alone is meaningless
- `hardcoded_locale_string` — Polish-phone lesson
- `network_call_unmocked` / `firestore_instance_unmocked`
- `missing_failure_path` — pair every happy with a failure
- `e2e_doing_unit_work` — wrong layer
- `widget_test_no_provider` — Blocs need wrapper
- `nondeterministic_random_seed` — passes locally, fails CI

### Pre-merge: `audit_release_readiness`

Final gate before merging the PR:

```python
verdict = audit_release_readiness(
    project_path="/path/to/project",
    is_published=True,   # or False for internal-only
)
```

- `verdict == "block"` → STOP. Address the blocker(s).
- `verdict == "hold"` → resolve top mid-tier issues.
- `verdict == "ship"` → proceed.

The composite covers seniority + security + localization +
dependencies + test_quality concurrently. Sub-second on a
typical project.

## Per-feature-kind quick reference

| Kind | Auto-included ACs (heuristic) | Cross-cutting extras | Recommended layers |
|---|---|---|---|
| `auth` | sign-in valid/invalid, session persist, sign-out | session-restore | unit + widget + integration |
| `form` | submit valid/invalid, disabled while submitting, cancel discards | IME action routing | unit + widget |
| `list` | renders items, empty state, loading/error, pull-to-refresh | — | unit + widget |
| `detail` | renders selected, loading/error, edit/back | — | unit + widget |
| `payment` | success, fail recoverable, cancel, network retry, idempotency | **idempotency + audit** | unit + widget + integration |
| `settings` | persist across restart, invalid rejected, restore defaults | — | unit + widget |
| `onboarding` | first-launch shows, skip works, persists once completed | — | widget + integration |
| `navigation` | route lands correctly, back restores, deep links | — | widget + integration |

## Test-data-factory patterns (always create these)

In `test/helpers/` (create the directory if missing):

- **`UserFactory`** (auth features): `anonymous()`, `signedIn()`,
  `signedInExpired()`, `banned()`, `withCustomClaims(claims)`
- **`OrderFactory`** (payment): `pending()`, `confirmed()`,
  `failed(reason)`, `refunded()`, `withItems(items)`
- **`<Feature>InputFactory`** (forms/settings): `valid()`,
  `invalid_missingField()`, `boundary_minLength()`,
  `boundary_maxLength()`
- **`ItemFactory`** (lists/detail): `single()`, `many(count)`,
  `empty()`
- **`FailureFactory`** (ALWAYS): `networkError()`,
  `validationFailure(field)`, `unauthorised()`, `notFound()`,
  `rateLimited()`

Each happy-path test gets a paired `should_X_when_Y_fails` that
arranges the matching `FailureFactory.xxx()`.

## Exploratory session — when to write a charter

Discipline #6 says **every feature gets one**. Charter format
(use `docs/exploratory-sessions/TEMPLATE.md`):

```
Mission: <one sentence — what are you looking for?>
Time-box: <15-90 min>
Areas: <3-6 concrete surfaces>
Session log: <observations as you go — don't filter>
Findings → 2-3 new automated cases per session
```

If a session produces 0 new cases, the charter was too narrow.
Broaden next time.

## Gap protocol (principle 8) — verbatim

When the user asks you to write tests but doesn't give you ACs:

1. **Still call `design_test_plan`** — pass what you have
   (user_story + feature_kind). The tool synthesises
   placeholder ACs from heuristics.
2. **Surface the gap explicitly** in your response:
   > "ACs were not provided. I generated placeholder ACs from
   > `feature_kind="<X>"` heuristics. **You should
   > reverse-engineer real ACs from the merged implementation
   > and re-run `design_test_plan` against them as afterwork.**
   > The tool's `notes_for_afterwork` captures this obligation."
3. **Add the note** to the PR description / task ticket so
   future-you (or the PO) sees it.

**Do not** silently invent ACs and present them as the real
spec. That's how teams ship tests that "work" but don't actually
validate what the product was supposed to do.

## What this skill is NOT

- **Not a replacement for `flutter analyze`** — run that first
  for syntax/type errors.
- **Not a runtime test runner** — these are static + planning
  tools. Run `flutter test` to actually execute.
- **Not auto-fix** — `audit_test_quality.findings` give you
  fix hints; you do the edits.
- **Not project-agnostic** — encodes Clean Architecture +
  flutter_bloc + Either pattern conventions. Teams on different
  stacks tune `min_level` or wrap the tools.

## Fallback when `mcp-phone-controll` isn't registered

If the audit tools aren't available in this session, apply the
discipline manually:

1. State the 8 principles to the user up-front
2. Ask for ACs (or surface the gap explicitly)
3. Generate test names following `should_X_when_Y`
4. Suggest `test/helpers/` factories
5. Add the failure-path counterpart per happy test
6. List the cross-cutting items per feature_kind
7. Suggest the exploratory charter as a follow-up

The discipline is the value; the tools are just enforcement.

## Companion docs (in the repo)

- `docs/senior-tester-discipline.md` — full 8-principle reference
- `docs/test-quality-rubric.md` — the 28 audit_test_quality rules
- `docs/release-readiness-rubric.md` — composite verdict logic
- `docs/exploratory-sessions/TEMPLATE.md` — charter format
- `docs/v030-field-test.md` — calibration log (3 real projects)
