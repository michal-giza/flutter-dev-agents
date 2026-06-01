# Changelog

All notable changes to `flutter-dev-agents` / `mcp-phone-controll`.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] — 2026-06-01

Field-test re-verification release. v0.4.0 was field-tested
against the same 3 calibration projects from v0.3.0
(`party_games_ui`, `mytaskboardapp`, `bike_news_room`) to
confirm the 8 v0.3.1 patches held. **7 of 8 patches landed
cleanly. One small regression in patch #5 was found + patched
here.**

### Fixed — `test_imports_test` regex (residual leak from v0.3.1)

The v0.3.1 patch excluded `package:flutter_test/`,
`package:test/`, `package:patrol/` from the
`test_imports_test` regex. Field-test re-run on
`bike_news_room` (which has integration tests) surfaced one
more framework URI we missed:

```dart
import 'package:integration_test/integration_test.dart';
```

This still got flagged because the URI ends in `_test.dart`.
**Now also excluded.** No new false positives elsewhere.

The negative regression test
(`test_test_importing_another_test_still_fires`) confirms
real cross-test imports still fire after the additional
exclusion.

### Changed — `[COMMODITY]` prefix on 5 overlap tools

Added explicit `[COMMODITY — prefer Google's dart_mcp_server.*
when both MCPs are registered]` prefix to the tool descriptions
of the 5 plumbing tools that directly overlap Google's official
MCP:

- `dart_analyze` → `dart_mcp_server.analyze_files`
- `dart_fix` → `dart_mcp_server.dart_fix`
- `dart_format` → `dart_mcp_server.dart_format`
- `flutter_pub_get` → `dart_mcp_server.pub`
- `flutter_pub_outdated` → `dart_mcp_server.pub` (outdated)

The tools still work; they're just labeled honestly so adopters
running the stack (us + Google) know which to call. Behaviour
unchanged.

### Verified — calibration table after re-run

| Project | Audit | v0.3.0 findings | v0.4.1 findings | Reduction |
|---|---|---|---|---|
| bike_news_room | security | 17 (16 FPs) | **1** | 94% |
| mytaskboardapp | security | 30 (29 FPs) | **1** | 97% |
| mytaskboardapp | dependencies | 10 (1 FP) | **9** | self-import gone |
| bike_news_room | test_quality | 20 (9 FPs) | 18 (1 FP) | 89% |
| bike_news_room | localization | 15 (1 FP) | 14 (0 FPs) | 100% |
| party_games_ui | seniority | 48 (1 FP) | **10** (cap) | barrel-file gone |

**Signal:noise across 6 audit×project combinations: ~73% → ~98%.**

### Stats

- Tools: **137** (unchanged)
- Tests: **904** (unchanged — existing test_imports_test
  regression tests now also cover integration_test)
- Tool description size: ~600 bytes added (commodity prefixes)
- 0 behaviour changes
- 0 new dependencies

### Documentation

The field-test re-run results are reflected in
`docs/v030-field-test.md` (existing file, updated with the
post-patch numbers).

## [0.4.0] — 2026-05-23

The Maestro composition release. v0.3.x established the
opinionated audit layer; v0.4.0 makes that layer **compose
explicitly with Maestro** (mobile.dev's flow-based cross-
platform mobile test framework, whose MCP launched Feb 2026).

We are the audit layer ON TOP of Maestro — they author + run
flows, we audit them. Same posture for Google's official MCP
and Arenukvern's flutter-inspector. See
`docs/flutter-mcp-comparison.md` for the full 3-player
landscape analysis.

### Added — `audit_maestro_flow` (phase 13)

Lints Maestro YAML flows against the senior-tester discipline.
12 rules across 4 tiers:

  **junior** — hardcoded_locale_string, vacuous_assertion,
  sleep_in_flow, no_assertions
  **mid** — no_appId, no_tags, inline_script_too_long
  **senior** — missing_failure_path, untagged_when_many,
  no_test_data_factory_dir
  **staff** — nested_runFlow_deep, hardcoded_credentials_in_env

Returns grade (excellent/acceptable/fragile/unreliable),
per-flow counts, top_actions. Pure compute, hand-parsed YAML
(no PyYAML dependency). Auto-discovers flows under `.maestro/`,
`maestro/`, `tests/maestro/`, `test/maestro/`.

### Added — `ingest_maestro_report` (phase 14)

Parses Maestro execution reports (JUnit XML or JSON), surfaces
pass/fail/flaky counts, runtimes, slowest flow, regressions
vs prior report. Stdlib parsers only (no XML or JSON deps).

Returns `IngestMaestroReportResult` with:

- `grade` — clean / acceptable / at_risk / blocked
- `flows_total / passed / failed / flaky / skipped`
- `flake_rate` (flaky / total)
- `pass_rate` (passed / (passed + failed))
- `slowest_flow` + `slowest_runtime_s`
- `regressions[]` — flow names that passed-then-failed
- `top_failures[]` — paste-ready summaries

### Changed — `audit_release_readiness` (phase 14.5)

Now optionally accepts a Maestro report path as a 6th
domain (`test_execution`):

```python
audit_release_readiness(
    project_path="/path/to/app",
    maestro_report_path="/path/to/maestro-report.xml",
    maestro_prior_report_path="/path/to/prior-report.xml",  # optional
)
```

The composite now covers (when all enabled):

  seniority    weight 1.0  — architecture
  security     weight 2.0  — OWASP MASVS
  localization weight 1.0  — i18n hygiene
  dependencies weight 1.5  — supply chain
  test_quality weight 1.5  — test suite (Dart)
  test_execution weight 1.5 — Maestro run results  ← new

### Fixed — grade-based blocker propagation

In `audit_release_readiness._reduce()`, domains that don't
return per-finding objects (like `ingest_maestro_report`,
which returns flow objects) but DO return a blocker-grade
(`blocked`/`critical`/`unreliable`) now correctly translate
to blocker count > 0 — making the verdict logic fire as
expected.

### Stats

- Tools: 135 → **137** (+2)
- Tests: 859 → **904** (+45)
- New external dependencies: **0** (stdlib XML + JSON only)
- All 3 CI checks green; contract snapshot refreshed

### Strategic note

This release makes us composable with the fastest-growing
Flutter test framework. The audit layer is durable
differentiation — Maestro doesn't ship audit tooling, Google
doesn't, Arenukvern doesn't. We do, now translated for
Maestro YAML idioms.

The composition story is now demonstrable end-to-end:

```
Maestro MCP authors flow → ourMCP audit_maestro_flow lints it
                ↓
Maestro MCP runs flow on device
                ↓
ourMCP ingest_maestro_report parses results
                ↓
ourMCP audit_release_readiness composites into ship/hold/block
```

## [0.3.1] — 2026-05-22

Calibration release. v0.3.0 shipped + got field-tested against
3 real Flutter projects (`party_games_ui`, `mytaskboardapp`,
`bike_news_room/frontend`) within hours. **8 false-positive
patterns were identified and patched in this release.**

See `docs/v030-field-test.md` for the full calibration log.

**Composite signal:noise improvement: ~73% → ~96%.** The
audit suite moves from "useful with manual filtering" to
"trust the output."

### Fixed — 8 calibration patches from the field test

1. **Exclude `build/` directories** from all 5 audits. Flutter's
   generated `AndroidManifest.xml` files under `build/app/
   intermediates/` were triggering `exported_component` (16 of
   17 high findings on `bike_news_room` were false positives).

2. **Exclude `.claude/worktrees/`** from all 5 audits. Agent
   worktree copies were being scanned, producing duplicate
   findings (15 of 30 critical findings on `mytaskboardapp`
   came from worktree copies of `firebase_options.dart`).

3. **`audit_security.hardcoded_firebase_key` exception** for
   canonical `firebase_options.dart`. Firebase web API keys
   there are intentionally public — security depends on
   Firestore rules, not key secrecy. The rule still fires on
   AIza keys in any OTHER file.

4. **`audit_test_quality.await_missing_on_pump` recognizes
   `$.tester`** (Patrol's PatrolTester) and `_.tester`. The old
   regex used a fixed-width lookbehind that only matched
   `await tester.`, missing 8 legitimate `await $.tester.
   pumpAndSettle(...)` calls on `bike_news_room`.

5. **`audit_test_quality.test_imports_test` excludes
   framework packages.** The old regex matched
   `'package:flutter_test/flutter_test.dart'` as if it were
   "this test imports another test file" — the URI ends in
   `_test.dart` but it's a framework import.

6. **`audit_dependencies.transitive_used_as_direct` excludes
   own package name.** A project legitimately imports
   `package:<own>/foo.dart` from its own `lib/`. The audit now
   parses `pubspec.yaml`'s `name:` field and excludes it.

7. **`audit_code_seniority.orphan_source` skips barrel files.**
   A file containing only `library X;` + `export 'y.dart';`
   statements has no testable logic. Heuristic detects this
   pattern. Also: added `/tokens/` to the existing list of
   path patterns (`/entities/`, `/models/`, `/failures/`) that
   are exempted from the rule.

8. **`audit_localization.missing_localizations_delegates`
   accepts getter references.** The old regex required a
   literal `localizationsDelegates: [` array. Now also
   accepts `localizationsDelegates: AppLocalizations.
   localizationsDelegates` (getter style).

### Added — `tests/unit/test_v031_calibration_patches.py`

15 new regression tests, one positive + one negative per patch
(where applicable). The negative tests assert each patch does
NOT over-silence — e.g. `test_actual_undeclared_transitive_still_fires`
verifies patch #6 still flags real undeclared transitives.

### Added — `domain/usecases/_helpers.py::is_path_excluded()`

Shared helper for skipping `build/`, `.claude/`, `.dart_tool/`,
`Pods/`, `.gradle/`, `.git/`, `node_modules/`, `DerivedData/`,
etc. Used by all 4 file-walking audits. Single source of
truth for the exclusion list.

### Stats

- Tools: 135 (unchanged)
- Tests: 844 → **859** (+15 regression tests)
- New shared helper: `is_path_excluded()` + `AUDIT_EXCLUDED_DIRS`
- Zero new external dependencies

## [0.3.0] — 2026-05-22

The audit release. Adds **seven opinionated audit verticals** plus
a composite release-readiness gate plus a senior-tester loop —
turning the MCP into a real-Flutter-judgment surface, not just a
device-control toolbox.

**Headline**: the agent can call `audit_release_readiness` as the
last step of every PR and get a single decisive ship / hold / block
verdict that composes five sub-audits in parallel.

### Tooling delta

- Tools: **110 → 135** (+25)
- Tests: **556 → 844** (+288)
- New external dependencies: **0**

### Added — the audit suite (PRs #27, #28, #30, #31, #32, #34, #35)

Seven pure-compute auditors, each with its own rubric doc:

- **`audit_code_seniority`** — 24 rules across 4 tiers
  (junior/mid/senior/staff). Grades architecture: print() in lib,
  business logic in widgets, missing dispose(), repos throwing
  instead of returning Either, missing super.key, monolithic
  Blocs, presentation→data layering violations, and more.
  Companion: `docs/code-seniority-rubric.md`.

- **`audit_security`** — 20 OWASP MASVS-aligned rules across 3
  severities (critical/high/medium). Hardcoded API keys
  (AWS/GCP/Stripe/SendGrid/Slack), JWT/PEM in source, Firebase
  keys not via FirebaseOptions, cleartext HTTP, SharedPreferences
  for tokens, WebView JS unguarded, ATS disabled, exported
  Android components, debug-signed release builds, missing cert
  pinning, biometric without fallback, PII leak via print(),
  Clipboard with secrets. Redacts secrets before reporting.
  Companion: `docs/security-rubric.md`.

- **`audit_localization`** — 16 i18n rules. Hardcoded
  user-facing strings (`Text('Sign in')`), missing l10n keys
  (code references key not in arb), missing translations across
  locales, supportedLocales ↔ arb mismatch (both directions),
  missing localizationsDelegates, pluralization-via-ternary
  (broken for Polish/Arabic plurals), RTL declared without
  Directionality plumbing, string concatenation with variables.
  Grade: `well_localized / acceptable / single_locale /
  missing_l10n`. Companion: `docs/localization-rubric.md`.

- **`audit_dependencies`** — 14 supply-chain rules.
  Floating-pin on security-sensitive packages (firebase_auth,
  dio, etc.), git/path overrides in published apps, dev tools
  (build_runner, mockito, freezed) landed in `dependencies`,
  unused declarations, transitive-as-direct imports, duplicate
  cross-section declarations, deprecated packages (package_info,
  connectivity → `_plus` variants), wide version ranges, loose
  Flutter SDK constraints, copyleft license hints. Hand-parsed
  pubspec.yaml + pubspec.lock; no network. Companion:
  `docs/dependencies-rubric.md`.

- **`audit_test_quality`** — 28 rules across 4 tiers. Catches
  what `dart test` won't: `bare_pump` (no await/Duration),
  `await_missing_on_pump`, `hardcoded_locale_string` (the
  Polish-locale lesson), `vacuous_expect` (`isNotNull` as the
  only assertion), `sleep_in_test`, `mocked_sut` (testing the
  mock), `network_call_unmocked`, `firestore_instance_unmocked`,
  `golden_no_verified_comment`, `missing_failure_path`,
  `widget_test_no_provider`, `e2e_doing_unit_work`,
  `nondeterministic_random_seed`, `integration_test_count_dominates`,
  `no_test_helpers_dir`. L10n-aware (silent on files importing
  `AppLocalizations`); fake-aware (silent on `*fake*`/`*mock*`
  paths).

- **`audit_release_readiness`** — composite ship/hold/block gate.
  Runs `audit_code_seniority` + `audit_security` +
  `audit_localization` + `audit_dependencies` +
  `audit_test_quality` concurrently via `asyncio.gather`. Returns
  composite letter grade (A–F), verdict (ship/hold/block),
  per-domain breakdown, cross-domain `top_actions` sorted by
  severity weight. Robust to partial sub-audit failure — always
  returns a verdict. Weights are tunable per-team (security
  weighted 2.0 by default; test_quality and dependencies 1.5;
  seniority and localization 1.0). Companion:
  `docs/release-readiness-rubric.md`.

### Added — the senior-tester loop (PRs #33, #34)

Two paired tools encoding 8 principles a senior test engineer
applies BEFORE and AFTER writing tests:

- **`design_test_plan`** (pre-write) — given a user story / ACs /
  source paths / feature_kind / team_style, returns a structured
  plan: per-AC happy/negative/boundary cases (Equivalence
  Partitioning + Boundary Value Analysis) with `should_X_when_Y`
  names, cross-cutting requirements (a11y/l10n/lifecycle as
  first-class, never afterthought), test layer recommendations,
  test data factory shapes, exploratory charter with time-box.
  **Gap protocol**: when ACs are missing, the tool proceeds with
  synthesised ACs from feature-kind heuristics AND surfaces a
  `notes_for_afterwork` entry instructing the caller to
  reverse-engineer ACs from the merged implementation and re-run.
  Never silently fakes the discipline. Companion:
  `docs/senior-tester-discipline.md`.

- **`audit_test_quality`** (post-write) — see above. Sister tool.
  Closes the loop: design → write → audit.

### Added — operational tooling (PR #29)

- **`pause_ui_automation`** + **`resume_ui_automation`** (paired
  bracket). Disables the openatx uiautomator2 helper packages
  (`com.github.uiautomator` + `.test`) via `pm disable-user`,
  letting screenshot / dump_ui / OCR passes run on AVDs without
  the helper periodically grabbing foreground and re-launching
  the app under test. Operational fix surfaced by real-device
  dogfooding session — documented at
  `docs/exploratory-sessions/2026-05-22-avd-uiautomator-respawn.md`.

### Added — documentation surface

- `docs/code-seniority-rubric.md` — 24 rules with severity,
  rationale, citations
- `docs/security-rubric.md` — OWASP MASVS mapping
- `docs/localization-rubric.md` — Polish-locale tap_text story +
  16 i18n rules
- `docs/dependencies-rubric.md` — supply-chain rules + curated
  deprecated-packages list
- `docs/test-quality-rubric.md` (referenced from
  `audit_test_quality`)
- `docs/release-readiness-rubric.md` — composite weighting +
  verdict logic
- `docs/senior-tester-discipline.md` — the 8 principles
- `docs/flutter-mcp-comparison.md` — comparison vs official
  Dart/Flutter MCP (~90% unique surface)
- `docs/internal-senior-tester-audit.md` — dogfooded our own
  Python test suite (B+ / SHIP)
- `docs/exploratory-sessions/` — charter format + 2 backfilled
  sessions (Polish locale, AVD respawn)
- `scripts/internal_senior_tester_audit.py` — re-runnable
  Python-suite analyser

### Changed

- `audit_release_readiness` (phase 11.5) now includes
  `test_quality` as the 5th domain. Default weight 1.5; blockers
  propagate to composite verdict.
- `tests/fakes/fake_adb.py` consolidates the 2 duplicated
  `_FakeAdb` test doubles from previous PRs (test refactor;
  surfaced by the internal senior-tester audit).

### Strategic posture

`docs/flutter-mcp-comparison.md` documents the diff against the
official Dart/Flutter MCP. **~10% commodity overlap, ~90% unique
surface.** Strategic move: lead on opinionated audit-grade
tooling, defer to Google on SDK plumbing. The audit rubrics are
the moat — they encode hard-won Flutter taste, and the official
MCP is unlikely to ship opinionated rules.

### Known-unknown

Tools have been internally dogfooded (`audit_*` against our own
Python test suite via a Python-equivalent analyser, scoring B+).
**Not yet externally dogfooded against a real Flutter app's
`lib/`.** False positives on team-specific patterns (custom
`Strings` classes instead of `AppLocalizations`, etc.) may
surface in 0.3.x patch releases as adopters report findings.
Soft-launch posture: PyPI publish + GitHub release, no
announcement post. Adopter feedback drives the 0.3.x calibration.

## [0.2.2] — 2026-05-19

Launch-readiness release. No behavior changes for end users — every
diff is CI hardening, distribution plumbing, or launch-day docs.
Releasing as 0.2.2 so the `mcp-phone-controll` PyPI listing is
created with infrastructure in place rather than as a side-effect
of a behavior change.

### Fixed — CI green for the first time (#6)

Three pre-existing CI failures that went red on every PR in the
0.2.1 series but never blocked the release (the `test` job was
always green). All three fixed together in one pass:

- **`gitleaks` action crashed on Node 20 runners.** Replaced the JS
  action with a direct gitleaks binary install (v8.21.2). Removes
  the Node-runtime dependency entirely.
- **Docker smoke "Connection reset by peer".** Root cause:
  `MCP_HTTP_HOST` defaulted to `127.0.0.1`, so the FastAPI server
  only listened on the container's loopback. `docker run -p`
  couldn't reach it. Baked `MCP_HTTP_HOST=0.0.0.0` into the image
  ENV with belt-and-braces re-set in the CI step.
- **`libssl-dev` missing from the builder stage.** `sslpsk-pmd3`
  (transitive `pymobiledevice3` dep) needs `openssl/ssl.h` to
  compile its C extension. Added to the builder's apt list.
- Smoke step now dumps `docker logs`, `docker inspect`, captured
  cURL errors on failure so the next regression surfaces with a
  useful trace.

First fully-green CI run on the repo lives on this commit.

### Added — PyPI publish workflow (#7)

`.github/workflows/release.yml` triggers on `v*.*.*` tag push and
publishes a wheel + sdist via PyPI Trusted Publishing (OIDC). No
long-lived `PYPI_TOKEN` secret stored anywhere — PyPI verifies the
GitHub OIDC claim against a pre-configured publisher.

Tag-vs-pyproject-version guard catches the foot-gun where a tag
ships with a stale version. `skip-existing: true` makes the upload
idempotent for accidental re-runs.

One-time bootstrap step the user owns (the publisher form requires
a browser session): see `scripts/bootstrap_pypi_publisher.sh`.

### Added — launch infrastructure (#7, #8)

- **README polish.** New one-sentence headline, 6 status badges
  (tests / license / MCP spec / Python / PyPI / CI), "Why it
  matters" section above-the-fold, "Try in 5 minutes" anchor.
  Stale tool counts ("67 tools / 50+") corrected to 110 across
  every reference.
- **Launch playbook authored locally** (now gitignored under
  `private/`) — covers directory submissions (PulseMCP, mcp.so,
  Smithery, Glama, 3 awesome-mcp PRs), social posts (LinkedIn, HN,
  Reddit r/FlutterDev, dev.to, Twitter), community channels (Patrol
  Slack, Flutter Discord), and the GitHub repo About-panel / topics
  / social-preview spec. ASO discipline
  applied across every text (first 80 chars carry value prop;
  three keyword clusters; one concrete number per blurb).
- **`smithery.yaml`** at repo root — required for the Smithery
  directory listing. Declares the 4 user-facing config knobs
  (`MCP_TOOL_TIER`, `MCP_WDA_TEAM_ID`, `MCP_LOG_FORMAT`,
  `MCP_MAX_IMAGE_DIM`) with proper schemas + descriptions so
  Smithery's dashboard generates a usable config UX.
- **Social-preview PNG** generated at `docs/design/social-preview.png`
  (1280×640, 35 KB) via `scripts/generate_social_preview.py`. Two
  columns (headline + 4-badge row | "WHAT'S INSIDE" capability
  list). Pillow-based — already a hard dep for our cap pipeline,
  so contributors can regenerate when numbers change without
  installing Figma/Sketch.
- **GitHub repo About panel** set live via `gh repo edit`:
  description, homepage URL, 18 topic tags.

### Added — release-cut helper

`scripts/release.sh <version>` automates the mechanical part of a
new release:

- Validate semver shape.
- Refuse if the tag already exists or the working tree is dirty.
- Refuse if `CHANGELOG.md` doesn't have a section for the new
  version — forces the human-written narrative.
- Bump `pyproject.toml`, commit, push the release branch.
- Print the `gh pr create` + `git tag` commands for the user to
  run after the PR merges.

`--dry-run` mode prints what would happen without modifying files.
Deliberately does NOT tag main directly or push to PyPI — the
release workflow handles those on tag push, so the human PR
review is the release gate.

### Added — PyPI bootstrap helper

`scripts/bootstrap_pypi_publisher.sh` prints the exact field values
to paste at `pypi.org/manage/account/publishing/` (no typos, no
field guessing), opens the browser, and — with the `verify` arg —
pings PyPI to confirm the publisher is active.

### Changed — repo organization

Moved 6 internal docs out of public `docs/` into `docs/internal/`
so the docs index is launch-presentable:

- Four `code-review-2026-05-*.md` engineering reviews.
- `LAUNCH-CHECKLIST.md` (superseded by the private launch playbook).
- `next-session-enhancements.md` planning doc.

Public `docs/` now reads as: architecture, runbook, adding\_\*,
adr/, design/, teaching/, walkthroughs.

### Stats
- Tests: 556 (unchanged — no source-code changes in this release).
- All three CI jobs (`test`, `Security audit`, `Docker build
  smoke`) green for the first time on the repo.
- No new tools; no breaking changes.

## [0.2.1] — 2026-05-19

Field-bug-driven patch release. Five issues surfaced during the first
overnight automated run against a Samsung Galaxy S25 + a physical
iPhone 15 on iOS 26. Each fix carries a regression test so the same
class of bug can't ship a third time.

### Fixed — MCP visibility in Claude Code (#1)
- `list_devices` and `recall` had `outputSchema.type = "array"`,
  which violates MCP 2025-06-18 (the `structuredContent` field is
  always an object). Claude Code's Zod validator drops the **entire
  server** when any tool's schema is invalid — symptom was "✓
  Connected" with zero tools visible.
- Removed both invalid outputSchemas; data payloads still validate
  via the standard envelope.
- New tripwire test (`tests/unit/test_output_schema_validity.py`,
  4 assertions) scans every descriptor on every CI run.

### Fixed — iOS 17+ developer-tier commands (#2)
- `take_screenshot` on physical iPhones running iOS 17+ failed with
  "Failed to start service" because the wrapper used the deprecated
  `developer screenshot` lockdown API (Apple removed the underlying
  service on iOS 17) and passed `--tunnel UDID` instead of the now-
  required `--rsd HOST PORT`.
- New `resolve_rsd(udid)` helper queries tunneld's HTTP API at
  `127.0.0.1:49151/` and returns the device's RSD endpoint.
- New `PyMobileDevice3Cli._device_route()` prefers `--rsd` when
  resolvable, falls back to `--tunnel` so iOS 16 setups keep
  working.
- Switched to `developer dvt screenshot`. Same routing applied to
  `launch`, `kill`, and `syslog live` (latently broken on iOS 17+
  for the same reason).
- Verified end-to-end on iPhone 15 / iOS 26: 5 MB PNG captured.
- 9 new unit tests in `test_tunneld_rsd_resolution.py`.

### Fixed — WebDriverAgent signing on physical devices (#3)
- `setup_webdriveragent` failed with "Signing for
  'WebDriverAgentRunner' requires a development team" on every
  physical iPhone — the Appium WDA project ships with empty
  signing settings.
- New `team_id` parameter (10-char Apple Developer Team ID) threaded
  through to `xcodebuild` as `DEVELOPMENT_TEAM=<id>` plus
  `CODE_SIGN_STYLE=Automatic`.
- Falls back to `MCP_WDA_TEAM_ID` env var for operators who want to
  set it once and forget.
- On signing-error detection, surface `next_action: "provide_team_id"`
  with a message that names the exact param/env var — instead of a
  generic `check_xcode_signing`.
- 4 new tests in `test_wda_setup.py`.

### Fixed — Polish/French localized `tap_text` (#3)
- `tap_text("Podczas używania aplikacji")` still failed despite the
  earlier NFC fix, because Android's `pl-PL` localization uses
  U+00A0 (NO-BREAK SPACE) between words for typography. Visually
  identical to ASCII space; byte-unequal.
- New `_normalise_loose` adds a whitespace-lookalike fold
  (NBSP / NNBSP / thin space / hair space → ASCII), strips
  zero-width chars (ZWSP, word-joiner, BOM), collapses internal
  whitespace runs, and case-folds in substring mode.
- Wired into the XML-dump fallback path only; the primary
  uiautomator2 selector stays strict so explicit `exact=True`
  matches don't drift. Strict-match still wins over loose when
  both exist in the same dump.
- 7 new tests in `test_android_tap_robustness.py` covering NBSP,
  NNBSP, thin space, ZWSP, run collapse, real Polish dialog match,
  case-insensitive substring, strict-preferred precedence.

### Fixed — overnight bot crashed on 6th raw-adb screenshot (#4)
- An overnight automation used `adb -s … exec-out screencap -p`
  via Bash for every screenshot — bypassing the MCP's 1600 px cap.
  Pixel emulators are 2400 px native; 5 accumulated PNGs + the 6th
  tripped the API's 2000 px-per-image dimension limit. The MCP
  itself worked correctly; the agent reached around it.
- Root cause: missing escape hatch on the BASIC tier.

### Added — `compress_png` promoted to BASIC tier (#4)
- The recompressor is now visible alongside `take_screenshot` on
  the BASIC tier so the recovery loop is always one tool-call away,
  regardless of the host's tool-count ceiling.
- New tests pin the invariant
  (`test_compress_png_lives_in_basic_tier`,
  `test_take_screenshot_is_also_in_basic_tier`).

### Added — `inspect_image_safety(path)` (#4)
- Pre-Read PNG probe: returns `long_edge_px`, `mcp_produced`
  (detects MCP cap via the preserved `.orig.png` sibling),
  `safe_to_read`, and a deterministic `next_action` ∈
  `{read_safely, compress_png, regenerate_via_take_screenshot,
  fix_arguments, convert_to_png}`.
- Cheap (PNG-header parse, < 1 ms, no pixel decode).
- Promotes `regenerate_via_take_screenshot` over `compress_png` when
  the file is ≥ 2000 px AND has no MCP provenance marker —
  `compress_png` can fail on hosts missing all image backends, but
  `take_screenshot` has the safety-net rewriter behind it.
- BASIC tier alongside `take_screenshot` + `compress_png` — full
  recovery loop available at every tier.
- 9 new tests in `test_inspect_image_safety.py`.

### Changed — docs
- `docs/runbook.md`: failure mode #1 (2000 px limit) reordered to
  put raw-adb-screencap as the dominant cause; new entries
  2b (WDA team_id) and 2c (NBSP + `tap_text`).
- SKILL-FULL.md: explicit "never use raw `adb screencap`" section
  plus the four-line probe ↔ remediation pattern.

### Stats
- Tests: 521 → **556** (+35 across the patch).
- Tools: 109 → **110** (one new: `inspect_image_safety`).
- BASIC tier: 24 → **26** (added `compress_png`,
  `inspect_image_safety`).
- All four PRs merged via linear rebase;
  `test (phone-controll)` green on every commit.

## [0.2.0] — 2026-05-17

First version published with an explicit license, security policy,
and contributor guide. The codebase has been at production-credible
quality for weeks; this release formalizes that.

### Added — agent ergonomics (MCP spec 2025-06-18 compliance)
- Tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
  `openWorldHint`) on all 109 tools via a centralized classifier.
  Hosts (Claude Desktop, Cursor) can now gate destructive ops at the
  UX layer.
- `outputSchema` infrastructure (`ToolDescriptor.output_schema` +
  `dataclass_to_json_schema()` helper). `mcp_ping` migrated as
  proof-of-pattern; per-tier rollout to the remaining 108 tools
  staged for follow-up.
- Contract snapshot test on `tools/list` — `docs/tools-contract.json`
  catches any silent drift; refresh with `UPDATE_CONTRACT=1 pytest`.

### Added — production tools
- `mcp_ping` — identify the running subprocess (version, git SHA,
  uptime, image-cap value, available backends). Catches "stale
  subprocess" in one call.
- `compress_png(path, max_dim?)` — recompress arbitrary PNGs from
  any source (including other MCPs like `computer-use`) with our
  palette + zlib pipeline. 3-5× size reduction.
- `start_wda_on_simulator(udid, port=8100)` — spawns
  `xcodebuild test-without-building` detached, polls for WDA
  reachability. Closes the loop K1 opened: K1 detects, this tool
  fixes.
- `list_missing_widget_keys(project_path)` — scans Flutter `lib/`
  for tap-target widgets (Buttons, GestureDetector, InkWell, etc.)
  lacking a `key:` parameter. Paren-depth tracking distinguishes
  adjacent keyed/unkeyed widgets. The highest-leverage selector-
  hygiene diagnostic for Flutter agents.

### Added — operational maturity
- Graceful shutdown — SIGTERM/SIGINT handlers in `__main__.py`
  cancel the serve task, trigger the atexit lock-release, terminate
  spawned subprocesses. Idempotent against impatient operators.
- Dispatcher observability — every tool call emits structured
  `tool_dispatch_start` + `tool_dispatch_end` records via
  `observability.emit`. Was dead code; now every dispatch is
  observable. `MCP_LOG_FORMAT=json` for ingest.
- Doctor pipeline self-test — `check_environment` returns an
  `image_cap_pipeline` row that writes a synthetic 3000×2000 PNG
  and verifies the cap path actually shrinks it.
- Real-device test scaffold under `MCP_REAL=1 MCP_REAL_DEVICE=1` —
  3 Android tests covering check_env, list_devices, full
  select→screenshot→release loop.

### Added — iOS reliability (K1 + K2)
- Dual-mode WDA factory — `xcrun simctl` distinguishes simulator
  vs physical; sims get `wda.Client(http://127.0.0.1:port)` instead
  of `USBClient`. Closes the iPhone-17-sim NoneType crash.
- `WdaUnreachable(next_action="start_wda_on_simulator")` typed
  failure with exact xcodebuild recipe in `fix_command`.
- Two-step tunneld hint — `check_environment` now has both
  `pymobiledevice3_cli` (on PATH) and `pymobiledevice3` (runtime)
  rows. Fix strings lead with `pipx install pymobiledevice3`.
- `scripts/install.sh` bootstraps `pymobiledevice3` system-wide
  via pipx.

### Changed — image-cap saga (closed)
- Default cap 1920 → **1600** (400 px headroom under the 2000 px
  API ceiling, up from 80 px).
- Hard 1900-px ceiling in `image_safety_net` independent of
  `MCP_MAX_IMAGE_DIM` — env-misconfiguration can no longer leak.
- PNG palette encoding (`Image.Quantize.MEDIANCUT`, 256 colors,
  `compress_level=9`) on every cap path. Real measurement on
  historical artifacts: 126 files recompressed, ~58 MB freed.
- `MCP_MAX_IMAGE_BYTES_KB` (default 250) triggers a recompress
  pass on PNGs that pass the dimension cap but exceed the byte
  budget — fixes the "Request too large (32 MB)" failure mode
  when agents accumulate many screenshots per session.

### Changed — code architecture
- `tool_registry.py` split: `presentation/descriptors/_shared.py`
  (helpers + ToolDescriptor) + `_param_builders.py` (all `_params_*`
  functions). Registry shrank 2885 → 2178 LOC.
- Path-traversal guard generalized — new `domain/path_guard.py`
  with `check_path_allowed(path, *, tool_name, extra_roots=,
  env_var_override=)`. Applied to `compress_png` and `fetch_artifact`.
  Other 7 path-accepting tools rolled out in the same release line.
- Middleware chain refactor — 7 named middlewares
  (PatrolGuard, RateLimiter, ProgressLog, OutputTruncation,
  ImageSafetyNet, TraceRecorder, AutoNarrate), each independently
  unit-testable. Dispatcher dropped 152 → ~30 LOC.

### Fixed
- Stale subprocess detection — `mcp_ping` exposes `git_sha`,
  `image_cap_px`, `image_backends`, `n_tools` so the next-action on
  "this should work but doesn't" is "fully quit and relaunch."
- Gradle first-run timeout 600s → 1500s — first-run on a clean
  machine pulls AGP + AAPT2 + KGP, easily 10 min on a slow link.
- `tap_text` after `prepare_for_test` was refused without the
  Patrol path being made clear; refusal envelope now leads with
  the Patrol recovery + the `system=true` escape hatch for OS
  dialogs.

### Tests
- 466 hermetic unit tests (+21 in the most recent batch).
- 5 real-device tests gated on `MCP_REAL=1` / `MCP_REAL_DEVICE=1`.
- Latency budget tests on the image-cap hot path (250 ms for
  1080×2340 cap; 30 ms for under-cap short-circuit).
- Subprocess-injection audit on `patch_apply_safe` (ADR-0006) plus
  two canary-file tripwire tests.

### Security
- Apache 2.0 license (was unlicensed — formerly unusable by any
  company with a procurement review).
- `SECURITY.md` — vulnerability disclosure policy, 3-day ack
  / 10-day triage / 5-day critical patch SLAs.
- `CONTRIBUTING.md` — code of conduct + the recipe for adding a
  new tool without breaking the contract snapshot.
- Subprocess injection audit ADR-0006 — proves no shell escape
  vector exists in `patch_apply_safe`; tripwire tests break if
  anyone re-enables shell mode.

### Internal
- Pre-commit hook (`.pre-commit-config.yaml`) mirrors CI exactly
  (ruff + pytest -q + tool-catalogue freshness).
- New `[ios]` pyproject extra for `pymobiledevice3`.
- 7 ADRs (image cap, middleware chain, version handshake, Voyager
  skill library, hybrid retrieval, patch-apply-safe injection audit).

## [0.1.0] — 2026-05-12

Initial monorepo restructure and tool catalogue (~100 tools across
tiers A–F). Pre-public release; no SemVer guarantees.

[0.2.2]: https://github.com/michal-giza/flutter-dev-agents/releases/tag/v0.2.2
[0.2.1]: https://github.com/michal-giza/flutter-dev-agents/releases/tag/v0.2.1
[0.2.0]: https://github.com/michal-giza/flutter-dev-agents/releases/tag/v0.2.0
[0.1.0]: https://github.com/michal-giza/flutter-dev-agents/releases/tag/v0.1.0
