# Changelog

All notable changes to `flutter-dev-agents` / `mcp-phone-controll`.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
