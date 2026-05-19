# Changelog

All notable changes to `flutter-dev-agents` / `mcp-phone-controll`.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.0]: https://github.com/michal-giza/flutter-dev-agents/releases/tag/v0.2.0
[0.1.0]: https://github.com/michal-giza/flutter-dev-agents/releases/tag/v0.1.0
