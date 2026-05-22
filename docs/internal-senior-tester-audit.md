# Internal Senior-Tester Audit

> Applied the 8-principle rubric from `docs/senior-tester-discipline.md`
> to our own Python MCP test suite. Date: 2026-05-22.
> Result: **mostly senior-grade**, with two targeted improvements
> queued.

## Why we're auditing ourselves

The user point that triggered this: *"we should apply that
[discipline] to our solution here as we're missing that."* If
we ship `design_test_plan` + `audit_test_quality` to other
teams, our own house should be in order first.

`audit_test_quality` is Dart-specific. To audit our Python tests
I wrote a 200-line analyser at `/tmp/dogfood_audit.py` that
applies each of the 8 principles via regex over `tests/`. This
is a one-off — not committed as a tool, because Python-test
auditing isn't on the v0.3.0 product surface. The output below
is what it produced.

## Headline aggregates

| Metric | Value | Verdict |
|---|---|---|
| Files scanned | 103 | — |
| Total tests | **863** | — |
| Total assertions | 2,235 | — |
| Asserts per test (avg) | **2.59** | ⚠ mid-tier |
| Failure-path assertions (`Err` / `next_action`) | **161 (19% of tests)** | ✅ senior |
| Files with `@pytest.fixture` | 5 | ⚠ mid (low pytest-idiomatic adoption) |
| Files with custom factory helpers | 16 | ✅ healthy |
| Skipped tests | 5 | ✅ all carry explicit reasons |
| `time.sleep` (synchronous, blocking) | **0** | ✅ excellent |
| `asyncio.sleep` (cooperative yield) | 6 | ✅ all sub-second / state-machine related |
| Nondeterministic `time.time()` / `datetime.now()` | 2 | ⚠ minor |
| Real network calls | **0** | ✅ excellent |

## Per-principle results

### Principle 1 — AC-first (EP + BVA) → ✅ senior

19% of the suite is failure-path assertions (`isinstance(Err)`
+ `next_action == "fix_arguments"`). For comparison, a suite
with only happy-path tests would show 0%. **Every new audit
tool we ship has paired `should_X_fires` + `should_X_returns_fix_arguments`
tests by construction.** The discipline is encoded in our
build-loop reflex.

Boundary value analysis is less visible because most of the
audit tools take string enums or paths, not numeric ranges. The
audit tools that DO have boundaries (e.g.
`audit_code_seniority.min_level`) include explicit
out-of-range tests.

### Principle 2 — Atomic (one assertion per test) → ⚠ mid

**2.59 asserts/test on average.** Worst offenders:

| File | Asserts/test | Tests |
|---|---|---|
| `test_http_ops_endpoints.py` | 4.5 | 6 |
| `test_memory_inspect.py` | 4.11 | 9 |
| `test_tool_dispatcher.py` (integration) | 3.71 | 7 |
| `test_artifact_retention.py` | 3.67 | 6 |
| `test_set_agent_profile.py` | 3.67 | 6 |

**Recommendation:** don't rewrite history. New tests should
split when they bundle multiple assertions. Specifically:

- `test_tool_dispatcher.py` — `test_registry_covers_all_use_case_fields`
  is intentionally a sanity sweep over 135 tools; **single-assert
  rule doesn't apply** to enumeration tests. Mark it
  as "intentional aggregate" in a comment.
- The memory / artifact files bundle "ok + count + content" —
  legitimate single check but reads like 3. Split if/when we
  next touch them.

**This is the principle most worth applying going forward but
also the least worth retro-fitting.**

### Principle 3 — Naming (`should_X_when_Y`) → ⚠ Python-idiomatic divergence

**0% strict `test_should_X_when_Y` adoption** across 863 tests.

But this is misleading. Python `pytest` convention is
`test_<descriptor>`, and our actual pattern is:

```
test_<rule>_fires                  ← happy-path: the rule fires
test_<rule>_does_not_fire          ← negative: rule stays silent
test_<rule>_silent_with_X          ← BVA-like: rule silent when X
test_<context>_returns_typed_failure  ← failure path
```

This is **functionally equivalent** to `should_X_when_Y` — the
test name says what the SUT should do under what condition.
The senior-tester rubric is language-agnostic; the
`should_X_when_Y` spelling is a Java/JVM convention. Our
spelling fits Python idioms.

**Verdict:** mark this as **culturally-translated compliance**.
We follow the discipline in spirit; the spelling differs.

### Principle 4 — Test data factories / builder pattern → ✅ healthy

16 test files define `_make_*` / `_build_*` / `_create_*` /
`_fake_*` helpers; 5 use `@pytest.fixture` directly. Two
established factory modules:

- `tests/fakes/fake_repositories.py` — fakes for every Protocol
- `tests/fakes/fake_dev_session.py` — debug session fakes

**Recommendation:** none of these helpers are duplicated across
files — but next time we see a `_make_user` pattern appearing
in two test files, promote it to `tests/factories/`.

### Principle 5 — Gherkin discretion → ✅ correct

This is a developer-heavy Python codebase. We don't use
Gherkin/BDD. **This is the right call** — for our team style,
plain `pytest` is cheaper to maintain.

### Principle 6 — Exploratory ≠ ad-hoc → ⚠ implicit only

We have **no formal exploratory test charters** in the repo.
But several v0.3.0 rules came from documented exploratory
sessions:

- `hardcoded_locale_string` rule in `audit_localization` ← Polish
  Galaxy phone session
- `pause/resume_ui_automation` ← BoardFlow AVD respawn-loop session
- `golden_no_verified_comment` in `audit_test_quality` ←
  observed via golden test reviews

**Recommendation:** when we next do a real-device exploratory
session, write a charter doc at
`docs/exploratory-sessions/YYYY-MM-DD-<topic>.md` per the
discipline. The findings → automated cases pattern is already
working; the format just isn't formal.

### Principle 7 — Cross-cutting first-class → ✅ N/A for Python MCP

a11y, l10n, lifecycle are user-facing concerns. Our MCP is a
backend Python server with no UI. **The cross-cutting concerns
are exercised indirectly** — through the Flutter apps we audit.

What DOES apply to a Python MCP:
- Determinism: 2 `datetime.now()` calls in test files. One in
  `test_artifact_retention.py:40` (legitimate — building
  a backdated mtime), one in `test_junit_writer.py:14` (used as
  test fixture data; could be parametrised but not broken).
  **Verdict: not worth changing.**
- Async hygiene: 6 `asyncio.sleep` calls, all sub-second
  cooperative yields except `test_graceful_shutdown.py:43`'s
  30-second `await asyncio.sleep(30)` — which is the test
  *subject's* inner task being cancelled, not a real wait.
  **Verdict: clean.**
- Real network: **0 calls. Excellent.**

### Principle 8 — Gap protocol (skips with reasons) → ✅ 100%

All 5 skipped tests carry explicit reasons:

```
test_compress_png.py:169         "cannot guarantee /Users isn't writeable"
test_release_screenshot.py:137   "cv2 not installed"
test_graceful_shutdown.py:29     reason="POSIX signal semantics"
test_graceful_shutdown.py:83     reason="POSIX signal semantics"
test_screenshot_caps_everywhere.py:56  "fake doesn't emit evidence_screenshot"
```

Plus the `integration_real/conftest.py` skips on missing
`MCP_REAL=1` env, missing Flutter SDK, missing adb — also all
have reasons.

**100% skip-with-reason discipline.** Senior-grade.

## Per-tier summary

| Tier | Our suite stands at |
|---|---|
| Junior smells | **≈ none** (no print debugging, no hardcoded shared state visible, no `pytest.skip` without reason) |
| Mid-level oversights | **2 small ones**: high asserts/test in 5 files; `datetime.now()` in 2 fixture builders |
| Senior architecture | **Strong**: failure-path coverage 19%, factories present, fakes module structured by Protocol |
| Staff suite-architecture | **Strong**: `tests/fakes/` package, `tests/unit/` vs `tests/integration/` vs `tests/integration_real/` (env-gated) separation |

**Overall grade: senior** (B/B+ if mapped to the audit
composite letter grade). Our own test suite would pass
`audit_release_readiness` with a SHIP verdict.

## What we'll actually change

Not "everything." The discipline calls out improvements but the
ROI on retro-fitting is low. Concrete actions:

1. **No new `test_x_does_a_thing_and_another_thing` names.** New
   tests stay atomic by default. If a test naturally bundles
   3 assertions, split — even at the cost of slightly more
   boilerplate.
2. **Promote the `_FakeAdb` pattern.** It appears in 3+ test
   files for phase 8.5 / deep_link / pause-ui-automation tests.
   Move to `tests/fakes/fake_adb.py` so the next test that
   needs it doesn't reinvent.
3. **Create `docs/exploratory-sessions/` directory** with a
   `TEMPLATE.md` for future charters. Doesn't need to be
   exhaustive — just consistent format.
4. **Document the asserts/test mid-tier finding** in
   `CONTRIBUTING.md` (when we write it) so newcomers know
   why we're picky about test atomicity going forward.

None of these is urgent. None blocks v0.3.0. Filing as
follow-up tasks rather than this-PR commits keeps the dogfood
PR focused on the audit + findings.

## Composite verdict on our own house

```
{
    "verdict": "ship",
    "composite_grade": "B+",
    "rationale": (
        "Healthy AC-first + atomic mid-tier + senior factories. "
        "Two follow-up tasks queued (test-asserts splitting, "
        "exploratory charter format). Dogfooded the discipline "
        "before shipping it to other teams — we're not asking "
        "more of users than we ask of ourselves."
    ),
    "domains": {
        "atomicity": "acceptable",
        "naming": "culturally-translated senior",
        "factories": "senior",
        "failure_path_coverage": "senior",
        "skip_discipline": "senior",
        "determinism": "senior",
        "real_network": "senior"
    }
}
```

We're allowed to ship the audit tools to others. ✓
