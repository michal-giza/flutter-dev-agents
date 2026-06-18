# Changelog

All notable changes to `flutter-dev-agents` / `mcp-phone-controll`.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.13.0] — 2026-06-18

**Agent navigation latency.** The slow default for device agents is
*screenshot → reason over pixels → compute x,y → tap → screenshot to
confirm* — ~1–2k image tokens and a vision round-trip per step. This
release makes the structured (no-vision) path the easy default for any
work that isn't a visual check. Tool count unchanged (144); `tap` gains
selector resolution.

### Added — `tap` by selector (resolve + tap server-side)

`tap` now accepts **`resource_id` / `text` / `class_name`** in addition
to `x`/`y`. A selector is resolved and tapped **in one call** — no
screenshot, no pixel reasoning, no coordinate math. Resolution order:
explicit `(x, y)` → `text` (routes through the hardened `tap_text`
matcher: NFC / NBSP / dump-scan fallback / Samsung adb-tap) →
`resource_id`/`class_name` (`find` → tap the element's centre). A
selector that matches nothing fails with `next_action:
capture_diagnostics` — it never taps a guessed coordinate. Get selectors
from `extract_ui_graph`. `x`/`y` is now the fallback for targets no
selector can address. Implemented at the use-case layer, so it works on
both Android (uiautomator2) and iOS (WDA).

### Added — optional UI-hierarchy cache (`MCP_UI_CACHE_TTL_MS`)

A short-TTL, action-invalidated cache for the read-only UI dump, so
repeated `extract_ui_graph`/`dump_ui` on a stable screen don't re-hit
the device. **Off by default** (`ttl_ms <= 0` = pure pass-through).
Safety by construction: only `dump_ui` is cached; every action
(`tap`/`swipe`/`type_text`/`press_key`) clears the entry, and
`find`/`tap_text` always resolve against the **live** device — so the
cache can never decide where a tap lands, only serve an observation
that's at most `ttl_ms` stale and never across an action you just took.

### Docs — `docs/agent-navigation-latency.md` (new)

"Drive structurally, verify visually." The cost of the vision loop, the
step-by-step structured replacements (`extract_ui_graph` → selector-tap
→ `wait_for_element`/`tap_and_verify`, plus `test_deep_link` and
`replay_skill`), when you genuinely need pixels, and the cache knob. The
`mcp-phone-controll-testing` skill gains a matching discipline rule.

### Tests

- `test_tap_selector.py` (+8) — coordinate/text/resource_id/class_name
  paths, not-found → capture_diagnostics, no-target → fix_arguments,
  coordinate precedence, lone-x rejection.
- `test_caching_ui_repository.py` (+10) — disabled-by-default,
  hit-within-TTL, expiry, action-invalidation (parametrized over all 5
  actions), per-serial isolation, find-always-live.
- Full suite: **1102 passed, 6 skipped.** ruff clean. Contract snapshot
  refreshed (`tap` schema).

## [0.12.0] — 2026-06-17

A context-budget guard for ingesting large payloads — built primarily
for **small / local models**, where a 74k-char widget tree or an
MB-scale HAR/Lighthouse/trace file silently overflows the window. Tool
count: **143 → 144**.

### Added — `estimate_tokens` (BASIC tier)

The text/payload analog of `inspect_image_safety` ("will this PNG blow
the API limit?") — *"will this string/file fit my context, or do I need
to scope or compact first?"* Pure compute, no network.

- **Count** — estimate tokens of a string or a file (chars, words,
  estimated tokens with a low–high band, a `size_class` of
  small/medium/large/huge). Files over 25 MB are estimated from byte
  size without loading.
- **Predict** — size a file *before* you ingest it (e.g. "is this HAR
  safe to `ingest_har`?").
- **Validate** — pass `budget_tokens` (your remaining context) to get
  `fits` / `headroom_tokens` and a **recommendation**: `proceed` /
  `proceed_with_caution` (<20% headroom) / `flush_context` (overflow).

Uses **`tiktoken`** (cl100k_base) when installed for an exact count;
otherwise a calibrated chars/words heuristic (override
`chars_per_token` — ~4 for prose, ~3.3 for code/JSON). Placed in the
**BASIC** tier because SLMs are exactly who needs the overflow guard.

Honest scope: a server-side MCP **cannot** see the model's live
remaining context or trigger a flush — compaction is the host's job
(Claude Code auto-compacts; a local agent clears its own history). This
tool gives the signal via `recommendation`; the host acts.

### Tests

- `test_estimate_tokens.py` (+14) — counting, size classes, budget
  fits/tight/overflow verdicts, file vs text, heuristic knobs, error
  paths.
- Full suite: **1083 passed, 6 skipped.** ruff clean. Contract snapshot
  refreshed.

## [0.11.0] — 2026-06-16

SLM / local-model hardening. The composed stack is model-agnostic, but
small models choke on a 140+-tool surface — and the OpenAI-compat HTTP
adapter (the usual SLM entry point) had **no tool-tier scoping**, so it
always served all tools. Fixed.

### Added — tool-tier scoping on the HTTP adapter

`GET /tools` now honours a **`?tier=basic|intermediate|expert`** query
param **and** the `MCP_TOOL_TIER` env var (parity with the stdio
server): `basic` → ~26 tools, `intermediate` → ~59, `expert`/unset →
all (~143, unchanged default). Small/local models can now be handed a
reasoning-sized surface and pull in the long tail on demand via
`describe_capabilities(level=…)`.

### Docs — `docs/slm-setup.md` (new)

How phone-controll + the composed stack adapt to SLMs (Ollama / vLLM /
LM Studio / llama.cpp):
- Budget the tool surface (`MCP_TOOL_TIER` / `?tier=`).
- Compose only the MCP a task needs — Playwright MCP (vision-free,
  token-light) for web driving on SLMs; Chrome DevTools MCP only when
  you need traces/network.
- `dart mcp-server --force-roots-fallback` for SLM clients without MCP
  roots support; use its verbose tools surgically.
- The **commodity-tool fallback**: a lone SLM on the HTTP adapter (no
  `dart mcp-server` composed) still gets SDK plumbing via our
  `dart_analyze`/`dart_fix`/`dart_format`/`flutter_pub_*` — that's why
  we kept them after the commodity deprecation.
- Why the audit layer is the SLM sweet spot (pure-compute, concise,
  judgment offloaded to the rubric).

Linked from README + the-stack.md. Stale `MCP_TOOL_TIER` docstring
counts refreshed (24→26, 109→143).

### Tests

- `test_openai_adapter.py` (+2) — `?tier=basic`/`intermediate` scope the
  HTTP surface; `MCP_TOOL_TIER` env parity.
- Full suite: **1036 passed, 33 skipped.** ruff clean.

## [0.10.0] — 2026-06-16

Two runtime-ingest tools — the "you capture, we grade" complements to
the static audits. Tool count: **141 → 143**.

### Added — `ingest_har`

Parse a Network-panel **HAR** export (from a browser MCP) into a
per-action network-cost report: per-host request counts, reads vs
writes, p50/p95 latency, payload bytes, errors, and the slowest calls —
with one **backend host** highlighted (`backend_host=`, or auto-picked
as the busiest non-CDN host). Grade
`good/needs_improvement/poor/blocked`. The per-action data-cost
telemetry the field reports asked for (e.g. Firestore reads per screen),
validated against the bike_news_room run's `/api/*` reads.

### Added — `ingest_frame_timeline`

Grade a captured frame timeline into a **jank score** — the runtime
complement to `audit_performance` (static). Accepts a Trace Event Format
file (Flutter VM Timeline from `start/stop_frame_profile`, or a Chrome
DevTools web trace) or a `frames_ms` list. Returns frame count, % janky
(over the `fps` budget; `fps=120` for ProMotion), worst frame,
p50/p90/p99, build-vs-raster split, grade `smooth/acceptable/janky/
severe`. For web traces with no Flutter frame events it falls back to
top-level long tasks as the jank proxy.

Both are pure-compute (stdlib JSON), read-only, model-agnostic.

### Docs

- `docs/performance-rubric.md` — runtime-complements section (static
  `audit_performance` → runtime `ingest_frame_timeline` + `ingest_har`).
- `docs/web-logged-in-flow.md` — `ingest_har` wired into the before/after
  loop's grade step.

### Tests

- `test_ingest_har.py` (12) + `test_ingest_frame_timeline.py` (11) —
  parsing, grading bands, percentiles, trace + frames-list modes,
  failure paths.
- Contract refreshed. Full suite: **1034 passed, 33 skipped.** ruff clean.

## [0.9.0] — 2026-06-08

New tool — **`audit_performance`**: static Flutter jank audit. Fills the
gap no first-party MCP covers (verified against Dart 3.11.5 — Google's
built-in `dart mcp-server` has analyze/fix/inspector but **no
performance/animation tooling**). Tool count: **140 → 141**.

### Added — `audit_performance`

Pure-compute seniority-rubric auditor (like `audit_security`) over
`lib/` — no device, no VM, model-agnostic. **10 rules / 3 severities**
across the three things that drop frames:

- **Animations:** `setstate_in_animation` (setState in an animation
  listener), `controller_not_disposed`, `opacity_animated` (animated
  `Opacity` → use `FadeTransition`), `missing_repaint_boundary`,
  `implicit_anim_zero`.
- **Scroll / virtualization:** `non_lazy_list` (`ListView(children:)`
  vs `.builder`), `shrinkwrap_list`, `nested_scroll_column`.
- **Rebuild cost:** `heavy_work_in_build`, `image_no_cache_size`.

Grade `smooth / acceptable / janky / severe` (weighted findings/KLOC).
Folds into `audit_release_readiness` as a default-on **performance**
domain (`weight_performance=1.5`). Docs: `docs/performance-rubric.md`.

**Field-calibrated** on bike_news_room/frontend: 111 files / ~21k LOC →
`janky` (17 findings, ≈0.8/KLOC) — real scroll/rebuild work surfaced,
no noise.

### Docs (toolchain currency)

- `dart mcp-server` is now built into the SDK (3.9+); updated
  the-stack.md / flutter-mcp-comparison.md (the `dart_mcp_server` pub
  package is superseded).
- Registered + documented **Playwright MCP** (visual/SLM) and **Chrome
  DevTools MCP** (debug/tooling) as the model-agnostic browser-driving
  layer; added the logged-in web before/after playbook + the
  field-verified CanvasKit synthetic-scroll caveat.

### Tests

- `test_audit_performance.py` (24) — every rule + grade + filters +
  generated/test-file skip.
- `test_audit_release_readiness.py` (+1) — performance default-on domain.
- Contract refreshed. Full suite: **1014 passed, 33 skipped.** ruff clean.

## [0.8.1] — 2026-06-08

Bug fix — **WebDriverAgent couldn't build for an iOS Simulator**. Field
report: `setup_webdriveragent` ran `xcodebuild build-for-testing` with
the **device** destination (`platform=iOS,id=<udid>`) regardless of
target, so against a simulator udid xcodebuild attempted a device build
and failed demanding code signing ("Signing for 'WebDriverAgentRunner'
requires a development team"). Simulator UI taps were impossible.

### Fixed — simulator WDA build

`setup_webdriveragent` now builds correctly for simulators:
`-destination 'platform=iOS Simulator,id=<udid>'` with
`CODE_SIGNING_ALLOWED=NO` (simulators never need a team). Device builds
are unchanged (device destination + `DEVELOPMENT_TEAM`).

- **Auto-detects** device class via `xcrun simctl list devices` — a udid
  simctl knows is a simulator. Pass `is_simulator=true|false` to
  override. So simulator WDA "just works" like Android/adb, no team.
- `team_id` / `MCP_WDA_TEAM_ID` is ignored for simulators; the signing
  hint only fires for device builds.
- `start_wda_on_simulator`: when `test-without-building` exits early
  (usually because the simulator wasn't built yet), the failure now
  points at `setup_webdriveragent` instead of `check_xcode_signing`.

### Tests

- `test_wda_setup_cli.py` (new, 3) — simulator argv (sim destination +
  `CODE_SIGNING_ALLOWED=NO`, no team), device argv (device dest + team),
  `detect_is_simulator` via simctl.
- `test_wda_setup.py` (+3) — simulator builds without signing even with
  `MCP_WDA_TEAM_ID` set; auto-detect simulator vs physical device.
- Contract refreshed (setup_webdriveragent gains `is_simulator`).
- Full suite: **994 passed, 33 skipped.** ruff clean.

## [0.8.0] — 2026-06-08

Completes the web debug story v0.7.0 started: the **inspector/service-
extension tools now work on Flutter web**, routed through the direct VM
Service WebSocket. **Live-verified** against a stock Flutter app
(`dump_widget_tree` returned a 7,912-char tree on web).

### Fixed — service extensions on web (via direct VM Service)

`dump_widget_tree`, `dump_render_tree`, `toggle_inspector` and generic
`call_service_extension` failed on web because they routed through the
Flutter daemon's `app.callServiceExtension`, whose debug-service
connection doesn't complete for an automated Chrome launch. They now go
through the **direct VM Service WebSocket** (the DWDS `wsUri` v0.7.0
captures) when the session is web — `getVM` → isolate →
`callServiceExtension`.

**Readiness handling:** Flutter's `ext.flutter.*` extensions register a
few seconds *after* the web app loads (measured: ~3s, 61 extensions).
The web path **retries on `-32601` (method-not-found)** until they
register (≤20s), so the first call after start doesn't race the app.

If the extensions never register, the failure now says so precisely
(`service extension … not registered after 20s — the web app hasn't
reached its first frame…`) instead of a bare "Unknown method". Verified
against `bike_news_room`, whose frontend doesn't render without its
backend — the stock app working in the same run proves it's app-state,
not our plumbing.

### Still not available on web (platform limit)

**Frame/heap timeline profiling** — `start_frame_profile` /
`stop_frame_profile` need `getVMTimeline`, which **DWDS does not
implement** (`-32601 Unknown method "getVMTimeline"`). This is a
dart2js/DWDS limitation, not fixable here; those tools stay mobile-only.

### Added — `VmServiceClient` helpers

`first_isolate_id()` and `call_service_extension(isolate_id, method,
args)` — the direct-VM-Service service-extension primitives, reusable by
any tool.

### Tests

- `test_dev_session_web.py` (+5) — web path retries to registration,
  succeeds first-try, surfaces real errors, handles missing
  `websockets` (`install_debug_extras`) and no-isolate.
- Contract refreshed (start_debug_session description).
- Full suite: **988 passed, 33 skipped.** ruff clean.

## [0.7.0] — 2026-06-06

Field report (web capabilities) #2: the live-session profiling tools
(`start_frame_profile`, `take_heap_snapshot`, `vm_evaluate`,
`dump_widget_tree`, `call_service_extension`, `read_debug_log`, …) were
device-coupled, so a Flutter **web** app couldn't be driven through a
live debug session.

### Added — web debug sessions (`start_debug_session(serial="chrome")`)

`start_debug_session` now accepts the Flutter **web** device ids
`chrome` and `web-server`:

```python
start_debug_session(project_path="…", serial="chrome")   # or "web-server"
```

**Live-verified against `flutter run -d chrome` (2026-06-08, on
bike_news_room + a stock app).** What works on web:

- ✅ Session boot — **lock-free** (no physical device to contend on).
- ✅ Captures the **DWDS VM Service URI** — on web, `app.debugPort`
  (`wsUri`) fires *after* `app.started`, so start() now waits for it
  (the fix below). Paste the URI into DevTools for the inspector.
- ✅ **Hot reload + hot restart** (`restart_debug_session`).
- ✅ `read_debug_log`, `list_debug_sessions`, clean `stop`.

This is the Edit → Hot Reload → Observe loop + logs + lifecycle for web.

### Known limitation — daemon service extensions on web

`dump_widget_tree`, `dump_render_tree`, `toggle_inspector` and the
frame/heap profilers route through the Flutter daemon's
`app.callServiceExtension`. On web that needs the daemon's *debug-service
connection*, which doesn't complete for an automated Chrome launch
(stuck on "Waiting for connection from debug service on Chrome…"), so
they return "method not available". **These tools are mobile-only for
now.** The robust web path is the **direct VM Service WebSocket** (the
`wsUri` we now capture) — planned as a follow-up. `attach_debug_session`
stays a documented no-op.

### Fixed — web VM Service URI timing

`FlutterMachineClient.start(await_vm_service=True)` waits (bounded) for
`app.debugPort` after `app.started`, so web sessions report a populated
`vm_service_uri` instead of `null`. Mobile is unchanged. Tolerates
absence (release mode) rather than hanging.

### Changed

- The repo skips the **adb device-lock** for web ids — real devices
  still require the lock (regression-guarded).
- `FlutterDebugSessionRepository` gained an injectable `client_factory`
  (testability; default unchanged).

### Tests

- `test_dev_session_web.py` (5) — web ids skip the lock + pass
  `await_vm_service`; real devices still require the lock.
- `test_flutter_machine_client_extended.py` (+3) — web debug-port timing:
  start() waits for the late `app.debugPort`, tolerates its absence,
  mobile doesn't wait.
- Contract refreshed. Full suite: **983 passed, 33 skipped.** ruff clean.

## [0.6.0] — 2026-06-06

Field report (web capabilities): "MCP has `ingest_lighthouse_report`
but doesn't *run* Lighthouse — a runner is missing." Fixed. Tool
count: **139 → 140**.

### Added — `run_lighthouse`

Runs the Lighthouse CLI headless against a URL (e.g.
`http://localhost:8080` serving a `flutter build web`) and parses it
in **one call** — category scores, Core Web Vitals (LCP/CLS/TBT), top
opportunities, and the CanvasKit-aware grade. The saved JSON path is
returned so you can re-ingest / diff later.

```python
run_lighthouse(url="http://localhost:8080")              # mobile preset
run_lighthouse(url="http://localhost:8080", preset="desktop")
run_lighthouse(url="...", categories=["performance", "accessibility"])
```

- **Composition, not reinvention.** We run the official Lighthouse CLI
  (resolved as `lighthouse` on PATH, else `npx --yes lighthouse`) — the
  same orchestrate-the-toolchain posture as running `flutter` / `adb` /
  `patrol`. Parsing + grading is **100% reused** from
  `ingest_lighthouse_report` (shared `IngestLighthouseReport`).
- **Clean install hint** when the CLI / Chrome is absent
  (`next_action: install_lighthouse`) — same posture as
  `check_environment` for adb/flutter.
- `run_lighthouse` = runner; `ingest_lighthouse_report` = parser (use
  the parser directly when CI already produced the JSON).

### Not in scope (deliberately)

- **Browser driving** (click/scroll/login before measuring) stays with
  the official **Chrome MCP** — we don't ship a browser driver. See
  `docs/the-stack.md`.
- **Live VM-Service profiling for web** (`flutter run -d chrome` →
  `start_debug_session` / `attach_debug_session`) is the next web
  lever; it reuses the existing daemon machinery but needs live
  verification on a real Flutter+Chrome host before shipping.

### Tests

- `test_run_lighthouse.py` (11 new) — run+parse happy path, option
  pass-through, CLI-not-found / no-report / empty-url failures, and
  `LighthouseCli` argv building + `lighthouse`/`npx` resolution.
- Contract snapshot refreshed (run_lighthouse registered).
- Full suite: **975 passed, 33 skipped.** ruff clean.

## [0.5.2] — 2026-06-06

Bug fix — **test runners couldn't test Flutter web apps**. Field
report: `run_unit_tests` ran `flutter test` on the default VM
platform, so a Flutter **web** app whose code imports `dart:html`
(transitively, via nearly the whole package) errored with:

> Error: Dart library 'dart:html' is not available on this platform.

The repo's own `make runtests` uses `flutter test --platform chrome`,
where the same suite is green. There was no way to pass that through
the MCP — `run_unit_tests` / `run_widget_test` had only `project_path`.

### Added — `platform` param on `run_unit_tests` + `run_widget_test`

`platform` is one of:

- **`auto`** (default) — runs on the VM, then **transparently retries
  on `--platform chrome`** if the run hits the web-only-library marker
  (`"is not available on this platform"`). A Flutter web app now "just
  works" without the agent knowing it's web.
- **`chrome`** — force `flutter test --platform chrome` (skips the VM
  probe).
- **`vm`** — force the default VM, no retry. The error path now carries
  a `hint` pointing at `platform='chrome'`.

Auto-detection is by the **actual compiler error**, not by scanning
imports — so no false positives/negatives from conditional imports.

### Implementation

- `FlutterCli.test_unit` / `test_widget` add `--platform <X>` when set.
- `looks_like_web_platform_error()` (parser module) is the shared
  detector; the `FlutterTestRepository` and `RunWidgetTest` use case
  both use it for the auto-retry.
- `TestRepository.run_unit_tests` protocol gains `platform="auto"`;
  threaded through the composite + Patrol runners.
- An `info`-level `test_platform_autoswitch` log fires on auto-retry.

### Tests

- `test_run_tests_platform.py` (12 new) — CLI argv, marker detection,
  repo auto-retry / force-chrome / force-vm, widget auto-retry.
- Contract snapshot refreshed (platform param on the 2 tools).
- Full suite: **967 passed, 33 skipped.** ruff clean.

## [0.5.1] — 2026-06-06

Bug fix — **strict MCP SDK structured-output rejection**. Tools that
advertise an `outputSchema` (`mcp_ping`, `check_environment`,
`session_summary`, `inspect_project`) failed on clients running a
strict MCP SDK (mcp ≥ ~1.9) with:

> Output validation error: outputSchema defined but no structured
> output returned

`list_devices` and other schema-less tools kept working — which is
exactly how the regression presented (reported in the field after a
client/SDK upgrade).

### Root cause

Two latent mismatches, both triggered the moment a host enforced
MCP 2025-06-18 output validation:

1. **`_call_tool` never returned `structuredContent`.** It returned
   only unstructured `TextContent`. A strict SDK *requires* a tool
   that declares `outputSchema` to also return structured content.
2. **The advertised schema described the bare dataclass, not the
   envelope.** Every tool returns `{"ok": bool, "data"?: ...,
   "error"?: {...}}`, but the schema was `dataclass_to_json_schema(X)`
   — which has `additionalProperties: false` + dataclass `required`,
   so the envelope could never validate against it even once
   structured content *was* returned.

### Fix

- `_call_tool` now returns `(content, structuredContent)` where
  `structuredContent` **is** the dispatcher envelope — gated on an
  SDK capability probe (`CallToolResult.structuredContent`), so older
  SDKs (our `mcp>=1.2.0` floor) still get content-only and don't choke
  on the 2-tuple.
- New `envelope_output_schema(data_cls)` wraps the payload schema in
  the `{ok, data, error}` envelope. `additionalProperties` stays open
  and only `ok` is required, so the **error** branch (no `data`) and
  middleware-enriched envelopes never false-fail validation.

### Tests

- `test_output_schema_envelope.py` (8 new) — the wrapped schema
  validates both success and error envelopes; tripwire that every
  live `outputSchema` is envelope-wrapped, not a bare dataclass.
- `test_mcp_server.py` (+2) — strict-SDK path returns the 2-tuple;
  legacy-SDK path stays content-only.
- Contract snapshot refreshed for the 4 rewrapped schemas.
- Full suite: **957 passed, 33 skipped.** ruff clean.

## [0.5.0] — 2026-06-05

Flutter **web** coverage. The mobile audits never knew about
the `web/` shell or runtime web vitals — this release closes
that gap with two pure-compute tools and extends the composite
to eight domains. Tool count: **137 → 139**.

### Added — `audit_web_app` (static web-shell audit)

Walks `web/index.html`, `web/manifest.json`, and `web/_headers`
to grade Flutter web production-readiness across **12 rules in
4 seniority tiers**:

- **Junior** — `html_no_lang_attr`, `no_viewport_meta`,
  `placeholder_meta_description`, `no_favicon`
- **Mid** — `no_csp`, `manifest_missing_pwa_fields`,
  `manifest_no_maskable_icon`, `no_theme_color`
- **Senior** — `placeholder_app_name`, `no_seo_meta`,
  `no_apple_touch_icon`
- **Staff** — `no_loading_indicator`

Grades: `excellent / acceptable / needs_polish /
not_production_ready / not_web_app`. CSP is detected in either
a `<meta http-equiv>` tag **or** a `web/_headers` line
(Cloudflare Pages / Netlify convention).

**Field-tested** against `bike_news_room/frontend/web` →
exactly **1 finding** (`html_no_lang_attr`) on an otherwise
exemplary web app. Zero false positives.

### Added — `ingest_lighthouse_report` (runtime web vitals)

Parses a Lighthouse JSON report (you run `lighthouse`, we parse
it — same posture as `ingest_maestro_report`). Returns category
scores, Core Web Vitals (LCP/CLS/TBT/FCP/SI/TTI) as typed
numbers, top opportunities, and a grade
(`good / needs_improvement / poor / blocked`).

**CanvasKit-aware:** the default `perf_good_threshold` is **70**,
not Lighthouse's own 90 — a healthy CanvasKit app ships a
~1.5 MB wasm payload and rarely scores above 80 on performance.
Pass `perf_good_threshold=90` for the HTML/wasm renderer.
Grade thresholds follow Google's official Core Web Vitals
boundaries (LCP 2.5/4.0 s, CLS 0.1/0.25, TBT 200/600 ms);
accessibility < 50 is a hard release gate.

### Changed — `audit_release_readiness` is now an 8-domain composite

Added two web domains:

- `web_app` — **auto-runs** when `web/` exists; auto-excluded
  (`ran=False`) on mobile-only projects so it never inflates the
  weighted score.
- `web_vitals` — opt-in via `lighthouse_report_path`.

New params: `include_web_app` (default `True`),
`lighthouse_report_path`, `weight_web_app`, `weight_web_vitals`.

### Docs

- `docs/web-app-rubric.md` — the 12 rules, the CanvasKit
  threshold rationale, Core Web Vitals boundaries, and the full
  web release-loop composition story (audit_web_app → build →
  lighthouse → ingest → composite).

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
