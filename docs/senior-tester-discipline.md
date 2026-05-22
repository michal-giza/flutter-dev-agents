# Senior-Tester Discipline

> Companion to `design_test_plan` (v0.3.0 phase 11.5).

The pre-write discipline a senior test engineer applies BEFORE
writing tests. Sister rubric to `audit_test_quality` (post-write
audit, phase 12). Together they form the senior-tester loop:

```
            design_test_plan       ←  pre-write
                  ↓
       agent writes tests
                  ↓
            audit_test_quality     ←  post-write
                  ↓
              merge / iterate
```

This document encodes the **eight non-negotiable principles**
the tool generates plans against. Each principle has a rule
slug the tool emits so reviewers can argue with the rubric
specifically.

## The eight principles

### 1. AC-first

> *"Zaczynam od Acceptance Criteria user story."*

Start from Acceptance Criteria. For each AC, design:

- **1 happy path** — what the AC literally says
- **2–3 negative cases** via **Equivalence Partitioning (EP)**:
  null / empty / wrong-shape / unauthorized / mid-flight cancel
- **2–3 boundary cases** via **Boundary Value Analysis (BVA)**:
  at minimum, just above minimum, at maximum, just above maximum

EP and BVA are 1980s-vintage discipline. They still work because
the bug classes they target — partition errors and off-by-one
errors — are still the bug classes that ship.

### 2. Atomic

> *"Test case musi być atomowy — jedna asercja per test."*

**One assertion per test.** Never mix "the response is OK" and
"the data is correct" in one test — when it fails, the report
tells you only the first thing that broke.

**Independent of every other test.** No shared state. The suite
must pass in any sharded CI order. If a test reads from a global
`currentUser`, that's a test smell.

### 3. Naming: `should_X_when_Y`

> *"Title w konwencji should_X_when_Y."*

```
should_returnFailure_whenNetworkOffline
should_navigateToHome_whenLoginSucceeds
should_disableSubmitButton_whenFormHasErrors
```

The CI report should read like English. When something fails,
you should know what's broken without opening the test file.

### 4. Test data: builder pattern / factory

> *"Preconditions zawsze przez builder pattern lub test data
> factory, nigdy hardcoded user współdzielony."*

```dart
// BAD — shared, ambiguous, leaky
const sharedUser = User(id: '42', name: 'Joe');

// GOOD — each test owns its own
final user = UserFactory.signedIn()
  .withId('42')
  .withCustomClaims({'role': 'admin'})
  .build();
```

The factory is the **single source of truth** for what a "valid
User" looks like. When the User entity changes shape, you fix
the factory once; 100 tests still pass.

### 5. Gherkin discretion

> *"Dla E2E używam Gherkin tylko jeśli biznes czyta scenariusze.
> W developer-heavy teamie zwykłe testWidgets jest tańsze w
> utrzymaniu."*

Gherkin (`Given/When/Then`) is for **stakeholder readability**.
If the only people reading your tests are developers, Gherkin is
overhead — `testWidgets()` (Flutter) or `test()` (Dart) is
cheaper to write and maintain.

The `design_test_plan` tool gates this via `team_style`:
- `developer_heavy` → no E2E layer recommended
- `mixed_with_business` → Gherkin E2E enabled

### 6. Exploratory ≠ ad-hoc

> *"Exploratory zawsze w charter format z time-boxem i notatkami,
> i z każdej sesji exploratory rodzą się 2–3 nowe automated
> cases."*

Exploratory testing **without a charter** is just clicking
around. With a charter, it's a discipline.

A charter has:
- **Mission**: what you're looking for (one sentence)
- **Areas to explore**: 3–6 concrete surfaces
- **Time-box**: 15–90 minutes
- **What to record**: notes + screenshots + logs
- **Expected outcomes**: 2–3 new automated cases per session

If a session produces 0 new cases, the charter was too narrow.
Broaden it next time.

### 7. Cross-cutting = first-class

> *"Cross-cutting concerns — a11y, lokalizacja, lifecycle —
> traktuję jako wymagania pierwszej klasy, nie afterthought."*

a11y, l10n, and lifecycle are **requirements**, not bonus rounds.
They're checked on every feature, not "if there's time."

For every feature the tool emits a baseline:
- **a11y**: Semantics label on every interactive widget; min
  48dp tap target (WCAG 2.5.5)
- **l10n**: No hardcoded user-facing strings; everything via
  `AppLocalizations` (the Polish-locale-phone lesson)
- **lifecycle**: `StatefulWidget` owning resources overrides
  `dispose()`
- **error_handling**: every happy path has a paired failure-
  path test asserting `isA<Failure>`

Feature-specific extensions:
- **Payment** → idempotency + audit logging
- **Auth** → session-restore across cold start
- **Form** → IME action routing (next/done)

### 8. Gap protocol

> *"... see lacks if any on that point when asked to or proceed
> without them but to note it in logs for afterwork thought."*

When ACs are missing, **proceed but log**. Never silently fake
having ACs — that hides the gap.

The tool:
1. Synthesises placeholder ACs from `feature_kind` heuristics
2. Returns `grade="needs_acceptance_criteria"`
3. Populates `gaps[]` with what was missing
4. Populates `notes_for_afterwork[]` with the reverse-engineer
   instruction: *"Proceeded without ACs. Afterwork: reverse-
   engineer ACs from the merged implementation, then re-run
   `design_test_plan` against them to surface gaps."*

This is the bridge between **shipping fast** and **shipping
well**. You're allowed to proceed without perfect specs — but
the log carries the obligation to fix the gap later.

## Decision tree: how to use the tool

```
Do you have user_story + ACs?
├── Yes
│   └── design_test_plan(user_story=..., acceptance_criteria=...)
│       → grade="complete"
│
├── Story only (no ACs)
│   └── design_test_plan(user_story=...)
│       → grade="needs_acceptance_criteria"
│       → AC heuristics generated from feature_kind
│       → notes_for_afterwork populated
│
├── Already-implemented feature, missing tests
│   └── design_test_plan(source_paths=["lib/features/X"], feature_kind=X)
│       → reverse-engineers ACs from source
│       → grade="needs_acceptance_criteria"
│       → afterwork: confirm ACs with PO
│
└── Nothing (just exploring shape)
    └── design_test_plan(feature_kind="auth")
        → fully synthetic plan from kind defaults
        → useful for scaffolding factories before code lands
```

## Per-feature-kind defaults

| Kind | Default ACs | Cross-cutting extras | Recommended layers |
|---|---|---|---|
| `auth` | sign-in valid/invalid, session persist, sign-out | session-restore | unit + widget + integration |
| `form` | submit valid/invalid, disabled while submitting, cancel discards | IME action routing | unit + widget |
| `list` | renders items, empty state, loading/error, pull-to-refresh | (none extra) | unit + widget |
| `detail` | renders selected, loading/error, edit/back | (none extra) | unit + widget |
| `payment` | success, fail recoverable, cancel, network retry, idempotent | idempotency + audit | unit + widget + integration |
| `settings` | persist across restart, invalid not saved, restore defaults | (none extra) | unit + widget |
| `onboarding` | first-launch shows, skip works, persists once completed | (none extra) | widget + integration |
| `navigation` | route lands correctly, back restores, deep links | (none extra) | widget + integration |
| `generic` | happy + edge + error | (none extra) | unit + widget |

## What this is NOT

- **Not an LLM.** Pure compute. The plan is generated from
  rules + heuristics, not synthesised by a model.
- **Not a replacement for the PO.** It synthesises ACs when
  they're missing so the agent isn't blocked, but the gap
  protocol always surfaces "talk to the PO" as afterwork.
- **Not Gherkin-evangelistic.** Gherkin is opt-in via team_style.
- **Not exhaustive.** The boundary cases are sample shapes; a
  specific feature might need 6 boundaries, not 3. The agent
  extends the plan; the tool seeds it.

## Composition

```python
# Step 1: design (pre-write)
plan = design_test_plan(
    user_story=story,
    acceptance_criteria=acs,
    feature_kind="auth",
    team_style="developer_heavy",
)

# Step 2: agent writes tests following the plan
# ... ai writes code ...

# Step 3: audit (post-write)
audit = audit_test_quality(project_path=...)   # phase 12

# Step 4: gate
release = audit_release_readiness(project_path=...)
# (will include test_quality as 5th domain in phase 12.5)
```

That's the full senior-tester loop. The agent owns the writing;
the rubric owns the discipline.
