# Building `flutter-dev-agents`: an autonomous AR/Vision Flutter dev environment for one-person teams

*A step-by-step retrospective on what we built, what we learned, and what to fix next — written specifically for solo founders running 4B local LLMs alongside Claude.*

---

## Why this exists

I run a one-person company building 4–6 Flutter apps, four of which are camera/AR/Vision-heavy. My day already looks like this:

- multi-project: VS Code windows for `checkaiapp`, `app-2`, `app-3`, etc.
- multi-device: Galaxy S25 + iPhone 14 Pro + Android emulator + iOS simulator, sometimes all four at once
- multi-model: Claude for the heavy lifting, a local 4B model on Ollama for cheap iteration loops

The bottleneck is no longer "can this be automated?" — it's "can my agents reliably automate it without me babysitting every step?". So instead of building yet another testing tool, I built a **dev environment in a box**: an MCP server that exposes 74 tools an agent can drive, organised so a 4B model can stay on the rails and a Claude-class model can dig deep when needed.

This article walks through what we built, why each layer is shaped the way it is, and (most importantly) **the gaps I'm shipping next**, with 10 concrete enhancements pulled from current best practices.

If you're building agents for your own dev workflow, a lot of this is copy-paste. The repo is `flutter-dev-agents` — Apache-licensed, monorepo, ready for `git clone`.

---

## What's actually in the box

### One MCP, two transports, 74 tools

```
flutter-dev-agents/
├── packages/
│   └── phone-controll/        ← the MCP, 105 tools, 366 tests
└── examples/                   ← shared YAML plan templates + agent loop
```

The MCP runs as either:
- **stdio** (`claude mcp add phone-controll -- python -m mcp_phone_controll`) for Claude Code
- **HTTP** (`mcp-phone-controll-http --port 8765`) with an OpenAI function-calling shape for any local LLM (Ollama, vLLM, LM Studio)

Same envelopes either way: `{ok, data, error: {code, message, next_action, details}}`.

### The tool surface, by layer

| Layer | Tools | What it covers |
|---|---|---|
| **Discovery** | `check_environment`, `describe_capabilities`, `describe_tool`, `inspect_project`, `session_summary` | Self-describing — agents don't have to guess what's available |
| **Devices** | `list_devices`, `select_device`, `release_device`, `list_locks`, `force_release_lock` | Cross-session filesystem-coordinated locks, PID-aware stale-cleanup |
| **Virtual devices** | `list_avds`, `start_emulator`, `list_simulators`, `boot_simulator`, `stop_virtual_device` | Android AVDs + iOS simulators, first-class |
| **Lifecycle** | `prepare_for_test`, `launch_app`, `stop_app`, `clear_app_data`, `grant_permission`, `install_app` | Atomic clean handoff |
| **Test orchestration** | `run_test_plan`, `validate_test_plan`, `run_patrol_test`, `run_patrol_suite`, `run_integration_tests`, `run_unit_tests` | Patrol-first, declarative YAML plans |
| **Dev session** | `start_debug_session`, `restart_debug_session`, `read_debug_log`, `dump_widget_tree`, `call_service_extension` | `flutter run --machine` JSON-RPC client |
| **IDE** | `open_project_in_ide`, `list_ide_windows`, `close_ide_window`, `focus_ide_window` | One VS Code window per project |
| **Code quality** | `dart_analyze`, `dart_format`, `dart_fix`, `flutter_pub_get`, `flutter_pub_outdated`, `quality_gate` | Production-grade self-check before claiming "done" |
| **Vision** | `compare_screenshot`, `detect_markers`, `infer_camera_pose`, `wait_for_marker` | OpenCV + ArUco; for the 4/6 apps that need real cameras |
| **Observation** | `take_screenshot`, `start_recording`, `stop_recording`, `read_logs`, `tail_logs` | Binary-safe PNG capture, structured log entries |
| **Setup helpers** | `setup_webdriveragent` (with skip-if-built marker) | One-time iOS UI runtime |

### Architecture: clean layers, not magic

```
domain/         pure — entities, Result/Err, Failures (with next_action), use cases
infrastructure/ async subprocess wrappers, no domain knowledge
data/           repositories implementing domain protocols + composites
presentation/   MCP server (stdio) + HTTP adapter — same envelopes
container.py    composition root, wires everything once
```

Two key composites:

1. **Platform router** — `serial → (Platform, DeviceClass)` lookup decides whether to use adb (Android) or pymobiledevice3 (iOS-physical) or simctl (iOS-simulator) for each call.
2. **Framework router** — `project → TestFramework` decides whether `run_integration_tests` dispatches to Patrol or plain `flutter test`.

Both compose orthogonally. Adding a new platform or framework means: implement one Protocol, register in `container.py`, done. No use case changes.

---

## The five hard problems we solved (and why each shape)

### 1. Cross-session device locking

Problem: three Claude sessions (one per project) all try to `select_device(R3CYA05CHXB)`. Without coordination, they thrash the phone.

Solution: filesystem-coordinated locks at `~/.mcp_phone_controll/locks/<serial>.lock`. JSON contents include the holder's `session_id` and `pid`. Acquired with `O_EXCL` so two racing processes can't both win. PID-aware stale-cleanup means a crashed session doesn't leave a permanent block — the next caller reclaims it.

```python
# select_device acquires; release_device releases; force_release_lock breaks
# stuck locks. list_locks shows holders across all sessions.
```

Why filesystem and not in-memory: each Claude Code session spawns its own Python subprocess. They share nothing in memory but share the filesystem. The HTTP adapter mode uses an `InMemoryDeviceLockRepository` since one process serves N clients there.

### 2. iOS 17+ tunneld dance

Problem: every developer-tier iOS service (screenshot, dvt launch, syslog over tunnel) requires `sudo pymobiledevice3 remote tunneld` running in a separate terminal. Forget it once and `take_screenshot` returns a cryptic `InvalidServiceError`.

Solution two-fold:
- `check_environment` actively probes `127.0.0.1:49151` and reports `ios_tunneld: ok|not_running` with the exact `sudo` command in `fix`. A separate `pymobiledevice3_cli` check verifies the binary is on PATH at all — added after a real-user bug report where the hint said "run `sudo pymobiledevice3 …`" on a machine where that command wasn't installed. The fix now leads with `pipx install pymobiledevice3` and uses `sudo $(which pymobiledevice3) remote tunneld` so the path resolves regardless of how the user installed it.
- iOS `take_screenshot` failure carries `next_action: "start_tunneld"` + `details.fix_command` + `details.docs_url: "docs/ios_setup.md#tunneld"` so an autonomous agent switches on the canonical action without parsing English.

The whole ladder of iOS prereqs (Developer Mode → DDI → tunneld → WDA) is documented in `docs/ios_setup.md` and linked from every relevant failure envelope.

**iPhone 17 simulator gotcha.** `wda.USBClient(udid)` connects over usbmux, which doesn't exist for simulators — calling it returned a stub whose first method call attribute-errored with `'NoneType' has no attribute 'make_http_connection'`. Reported in production, May 2026. The factory now branches on `xcrun simctl list devices -j`: physical → `wda.USBClient(udid)`; simulator → `wda.Client(f"http://127.0.0.1:{port}")`. A reachability probe fails fast with a typed `WdaUnreachable(next_action="start_wda_on_simulator", fix_command=…)` so agents see the exact xcodebuild command to launch WDA instead of a Python crash.

### 3. Patrol vs plain `flutter test`

Problem: a 4B model can't reliably author a Patrol test from scratch, but plain `flutter test integration_test/` doesn't drive native dialogs.

Solution: declarative YAML plans (`apiVersion: phone-controll/v1`) with two driver kinds — `patrol_test` and `flutter_test`. The framework-routing composite decides which to use based on `inspect_project` output. Plans are peer-reviewable in PRs; agents fill in slot values rather than authoring control flow.

```yaml
- phase: UNDER_TEST
  driver: { kind: flutter_test, target: integration_test/auth_test.dart }
  capture: [screenshot, logs, debug_log]
```

### 4. Real-developer dev iteration loop

Problem: an agent that wants to try a code change shouldn't have to reinstall the app. A long-lived `flutter run --machine` is what VS Code's Dart-Code extension uses; we expose the same.

Solution: `FlutterMachineClient` — a JSON-RPC client over `flutter run --machine`'s stdio. Per-session ring buffer of events. Hot reload via `app.restart`, service extensions via `app.callServiceExtension`. Wraps as: `start_debug_session`, `restart_debug_session`, `read_debug_log`, `dump_widget_tree`, etc.

Combined with `open_project_in_ide` (`code -n <path>` per project), an agent and a human can work in parallel — agent edits + hot-reloads while the human watches in VS Code.

### 5. Output bombing 4B models

Problem: `dump_ui` returns a 50KB XML tree. `read_logs` returns 200 lines. A 4B model with 8K context can't survive even one verbose tool call.

Solution: dispatcher-level output truncation. Strings cap at 8KB, lists at 200 items, with a `_truncated: N` sentinel and a top-level `data_truncated: true` flag. The truncation envelope adds `next_action: "fetch_full_artifact_if_needed"` so the agent knows to grab the full file from artifacts dir if it actually needs it.

**The image-cap saga** is the same lesson under a different headline. Claude's vision API rejects multi-image conversations where any image exceeds 2000 px on the long edge — a real Galaxy S25 screenshot is 1080×2340, so every single tap-and-verify originally crashed the conversation. The fix evolved through four iterations:

1. **Per-use-case cap (1920 px).** `take_screenshot` resizes after capture. Worked until a different code path (`prepare_for_test`'s evidence) forgot to call it.
2. **Dispatcher safety net.** A middleware walks every response envelope, caps any oversized PNG it finds. Closed the gap at the cost of 80 px of margin under the 2000 ceiling — every off-by-one or stale subprocess could still leak.
3. **Defaults dropped to 1600 + hard 1900 ceiling.** The soft cap is env-driven; the hard ceiling is wired into the safety net and ignores env overrides. Setting `MCP_MAX_IMAGE_DIM=2200` still can't leak anything > 1900. Plus a `image_cap_pipeline` doctor check that writes a synthetic 3000×2000 PNG and verifies the cap path actually shrinks it — answerable on first call, not after a session-killing failure.
4. **Byte budget, not just pixels.** "Request too large (max 32MB)" hit after ~50 screenshots accumulated in one e2e session — each truecolor 1600×900 PNG was ~600 KB, total payload past the 32 MB request limit. Palette-mode encoding (`Image.Quantize.MEDIANCUT`, 256 colors, `compress_level=9`) is visually lossless for UI content and 3-5× smaller. Measured impact on real historical artifacts: 126 files recompressed, ~58 MB freed. A 25-shot session now lands at ~3 MB instead of ~15 MB.

The pattern across both output truncation and image capping: **the model's context is a shared physical resource — defend it in middleware, not in every use case that forgets**. Most of the engineering effort across the four image-cap iterations went into widening the safety net, not narrowing it.

Combined with the **tool ladder** (`describe_capabilities(level="basic")` returns ~18 tools instead of all 74) and **describe_tool** (fetch verbose docs only for the tool you're about to call), a 4B agent operating on the `basic` level keeps a tight context.

---

## What's still wrong (the honest part)

None of this is finished. Here are the gaps a careful read of the code reveals:

1. **`infer_camera_pose` is unreliable without real intrinsics.** It uses a coarse default camera matrix. Useful for relative pose changes; useless for "is the AR cube within 5mm of the marker?" assertions.
2. **`tail_debug_log` polls every 100ms.** Wasteful — should wake on the FlutterMachineClient's event push.
3. **`flutter_pub_outdated` returns an empty list.** I parse the human-readable output instead of using `--json` because of API churn across Flutter versions; needs a proper structured parser.
4. **No DAP-level debugger.** `start_debug_session` exposes hot reload + service extensions, but no breakpoints, step, or variable inspection. Coming next.
5. **No real-device integration test.** All ~400 unit tests use fakes; we still have zero tests that actually exercise `flutter` or `adb` against a real project. Manual testing has caught every load-bearing iOS bug (binary-safe screenshot encoding, tunneld port discovery, iPhone 17 sim WDA transport). Mitigated somewhat: the hermetic test surface now includes a scripted-fake `xcrun simctl` + fake `wda` module for the K1 dual-mode factory, latency budgets on the image-cap hot path, and a subprocess-injection guard on `patch_apply_safe` (ADR-0006). Doesn't replace a real-device CI loop but raises the floor.
6. **The skill is 8K tokens.** Fine for Claude, brutal for a 4B model. Needs a per-level skill variant — "skill-basic.md" with the 18-tool subset and a checklist-shaped flow, vs the current "skill-expert.md".
7. **Multi-project parallel test runs aren't a tool yet.** The lock layer supports it; no `run_test_plan_on_pool(devices=[...])` convenience.
8. **No persistent session trace.** `session_summary` is in-memory; once the MCP exits, the audit trail is gone.
9. **iOS UI driving still needs WebDriverAgent built per device.** `setup_webdriveragent` codifies the recipe but doesn't validate the resulting build before claiming success. The May 2026 dual-mode-WDA fix closed the worst symptom (sim crashes instead of clear errors) but the developer still needs to launch `xcodebuild test-without-building` against the simulator manually — the MCP surfaces the exact command in `WdaUnreachable.fix_command`, but doesn't run it for you.
10. **No CI Docker image.** Plan documents the topology; nothing's built. iOS can't be containerised (Apple-side); Android emulator + Patrol can.

---

## 10 enhancements pulled from current best practice

These come from re-reading what the people doing this well are publishing right now: Karpathy on agent design, the Claude Code repo on tool ergonomics, Anthropic's MCP guide, and lessons from running 4B models on real workloads.

### 1. **Plan-then-act, not act-then-plan** (Karpathy)

Currently a 4B model sees `run_test_plan` as one of 18 tools and might pick something else first. **Add a `must_have` step in `describe_capabilities`** that surfaces the recommended sequence:

```
recommended_sequence: ["check_environment", "describe_capabilities",
                       "inspect_project", "validate_test_plan", "run_test_plan"]
```

Small models follow templates well; just give them one.

### 2. **Constrain output structure with grammars, not just JSON Schema**

Pydantic + `outlines` or `lm-format-enforcer` lets us *force* a 4B model to produce structurally-valid tool calls at sampling time. Right now we hope the model emits valid JSON; we should enforce it. This is the single biggest reliability win for sub-7B models.

### 3. **Replay buffer / one-shot examples in `describe_tool`**

A 4B model copies far better than it composes. `describe_tool` should return not just a corrected_example but **3 real successful invocations** from the session trace. Karpathy's "show, don't explain" — the model sees what worked yesterday.

### 4. **Stop-and-summarise after every 5 tool calls**

Long agent loops drift. Insert a synthetic `summarise_progress` step every N calls that:
- Reads `session_summary`
- Compares against the original goal
- Either commits to continue or aborts

This is "reflection" in agent literature; it's free correction for almost no cost on small models.

### 5. **Make every tool description ≤ 30 words at the basic level**

Currently the descriptions average ~50 words. For 4B models that's a 30% context overhead before any tool runs. **Add a `terse: true` mode** in `describe_capabilities` that returns one-line descriptions, with verbose-on-demand via `describe_tool`. Token economy is about ratios, not absolutes.

### 6. **Ground every assertion in observable evidence**

The current skill says "use widget Keys, never display text." That's a rule. Stronger: **make the dispatcher refuse `tap_text` calls when a Patrol session is active**, with `next_action: "use_patrol_key"`. Mechanism beats discipline.

### 7. **Shadow-run new tools on a fixture project before exposing them**

Before adding a tool to `BASIC_TOOLS`, run it through 100 simulated agent loops against a fixture Flutter project. Failures get fixed before the tool reaches users. This is what the Claude Code team does for new built-ins; we should do it for new MCP tools.

### 8. **Test agents the way you test code: fixtures, not hopes**

We have ~190 tests of the MCP. We have zero tests of the agent's behavior using the MCP. **Add a `tests/agent/` suite** that runs deterministic LLM transcripts (replayed from real sessions) through the dispatcher and asserts the side effects (which tools were called, in what order, with what envelopes). When the model behaves badly, the test catches it.

### 9. **Treat each "button click" as a contract**

The user said it best: "each button has a flow, hence we need proper validation." Concretely: every Patrol test that taps a button should also assert (a) the post-tap widget tree contains the expected new screen, (b) the `read_debug_log` since the tap contains zero error-level events, (c) `compare_screenshot` against a golden of the new screen passes within tolerance. **Bake that triple-assert into `tap_widget(key)` as the default behavior**, not as something the test author has to remember.

### 10. **Solo-founder economics: every tool earns its complexity**

For a one-person company, every tool is a maintenance burden. Drop tools that haven't been called in the last 90 days of session traces. Add a `tool_usage_report` use case that surfaces this. Karpathy on minimalism: subtract until it hurts, then add back only what proves itself.

---

## Best-practice testing protocol — autonomous-development edition

When the agent wrote most of the code, traditional "developer remembers to run tests" testing breaks. Here's the protocol I'm enforcing on `flutter-dev-agents` going forward:

### Layered, structurally enforced

| Layer | Speed | Cost | Confidence | When |
|---|---|---|---|---|
| **Pure unit tests** | <100ms | free | ✓ basic correctness | every PR, every save |
| **Use-case + fake-repo tests** | <1s | free | ✓ behaviour correctness | every PR |
| **Parser + fixture tests** | <500ms | free | ✓ external-format compatibility | every PR |
| **Integration with HTTP adapter** | <2s | free | ✓ envelope contract | every PR |
| **Real-device smoke** | 30–90s | a phone | ✓ "works on hardware" | nightly + before release |
| **Patrol against fixture app** | 2–5min | a phone | ✓ "real feature works" | before release |
| **Agent transcript replay** | <5s | free | ✓ "agent doesn't drift" | every PR |

### The validation rule for every change

Every PR (including agent-authored ones) must:
1. **Pass unit + integration tests** (`pytest -q`)
2. **Pass `quality_gate`** — `dart analyze` returns zero errors, format is clean, unit tests pass
3. **Add a test that would have failed before the change** — even one assertion. This catches "the agent wrote code that already worked" no-ops.
4. **Cite which observable evidence proves the change works** — a screenshot, a log line, a TestRun outcome. "I think it works" is rejected.

The MCP enforces #2 mechanically via `quality_gate`. #3 and #4 are skill-level rules I'm encoding in the agent prompt.

### What "1-person companies in 2026" actually need

- **Mechanism over discipline.** I will forget the rules. The tooling shouldn't.
- **Failure modes you can sleep through.** Every Failure carries `next_action`. The agent self-recovers; I get a report in the morning.
- **Audit trail.** `session_summary` is non-negotiable. If something burned $X overnight, I need to know which tool call started the fire.
- **Reversibility.** Every "destructive" action (`force_release_lock`, `dart fix --apply`, `clear_app_data`) requires the agent to have called a non-destructive analogue first (`list_locks`, `dart fix` dry-run, `prepare_for_test`).

---

## What's next (concrete, ordered)

1. **DAP-level debugger** — breakpoints, step, evaluate, inspect via Dart's DAP server. Brings Claude up to "real Dart-Code extension" parity.
2. **AR/Vision depth** — `calibrate_camera`, `assert_pose_stable`, `wait_for_ar_session_ready`, `save_golden_image`, plus AR-specific plan phases. For the 4 of 6 apps that ship AR.
3. **Skill split** — `skill-basic.md` (4B model, 18 tools, checklist) vs `skill-expert.md` (Claude, 74 tools, judgment). One file currently serves both badly.
4. **Agent transcript replay tests** — see enhancement #8 above.
5. **`tool_usage_report`** — see enhancement #10.
6. **Persistent SQLite session trace** — `session_summary` survives restart.
7. **Multi-project parallel test runs** — `run_test_plan_on_pool`.
8. **CI Docker image** — Linux + Android emulator + Patrol + MCP, headless.
9. **Real-device integration tests** — `tests/integration_real/` opt-in suite.
10. **Tool description ≤ 30 words** — token economy.

I'm shipping #1 and #2 in the same batch as this article. The rest cascade naturally.

---

## What landed in the May 2026 hardening pass

This is the running changelog for the load-bearing fixes since the article's
first cut — each bug came from a real user session, the kind of stuff that
makes "it works on my machine" stop working. Worth tracking in the article
itself so the published version doesn't drift from the codebase the moment
something gets fixed.

| Fix | Symptom that drove it | Mechanism |
|---|---|---|
| Image-cap default 1920 → 1600 | "exceeds the dimension limit (2000px)" hit after multi-image accumulation despite per-call cap | Wider headroom (400 px instead of 80) + Pillow pinned as core dep + `image_cap_px` in `mcp_ping` so stale subprocesses are visible |
| Hard 1900 ceiling in safety net | Same error after env-misconfiguration to 2200 | Two-step safety net: soft cap (env) then hard cap (1900) regardless of env |
| `image_cap_pipeline` doctor probe | "Is my cap pipeline working?" was unanswerable until first failure | `check_environment` writes a synthetic 3000×2000 PNG, runs cap, asserts ≤ 1900. Live status: `3000x2000 -> <=1900 via PIL,sips (active cap=1600px)` |
| PNG palette compression + byte budget | "Request too large (max 32MB)" after ~50 screenshots in one e2e session | Adaptive palette (256 colors) + `compress_level=9` everywhere; `MCP_MAX_IMAGE_BYTES_KB` (default 250 KB) triggers re-encode pass. Measured: 126 historical files recompressed, ~58 MB freed. |
| K1: dual-mode WDA factory | `'NoneType' object has no attribute 'make_http_connection'` on iPhone 17 sim | `xcrun simctl list -j` detects sim vs physical; physical → `wda.USBClient(udid)`, sim → `wda.Client("http://127.0.0.1:8100")`. Reachability probe → typed `WdaUnreachable(next_action="start_wda_on_simulator")`. |
| K2: `pymobiledevice3_cli` doctor row + install-first hints | Tunneld hint said `sudo pymobiledevice3 remote tunneld` on machines where the binary wasn't installed at all | Separate doctor check for the CLI on PATH; hint leads with `pipx install pymobiledevice3`; daemon command becomes `sudo $(which pymobiledevice3) remote tunneld`. `scripts/install.sh` bootstraps pmd3 system-wide. |
| Build timeout 600s → 1500s | "MCP timed out — building via Bash directly (Gradle first-run can take minutes)" | First-run Gradle on a clean machine pulls AGP + AAPT2 + KGP; 10 min isn't unusual. Subsequent builds unaffected. |
| `tool_registry.py` split | 2885-LOC god module | Extracted to `presentation/descriptors/_shared.py` (helpers + ToolDescriptor) + `_param_builders.py`. Registry down to 2154 LOC. |
| `vm_service_client` coverage 0 → 95% | 66 LOC of debug-protocol code had no test | 7 hermetic tests with a scripted fake WebSocket. < 100 ms total. |
| Pre-commit hook | CI failures only caught after `git push` | `.pre-commit-config.yaml`: ruff (autofix) + pytest -q + `generate_tool_catalogue --check`. Mirrors CI exactly. |
| ADR-0006: `patch_apply_safe` injection audit | Audit task on the §7 code-review backlog | Proof + 2 canary-file tripwire tests that break if anyone refactors `_run` to `shell=True` |
| Latency budget on cap path | Cap performance was never asserted | 250 ms budget for 1080×2340 capture; 30 ms for under-cap short-circuit. Tripwires for `cv2 → slow PIL` regressions. |

The composite shape that emerges: **most production bugs in agent
plumbing aren't logic bugs, they're invariants nobody tested.** The
fixes are short; the safety nets are widening over time.

---

## Testing protocol — the bar that keeps autonomous code honest

Code that an agent writes is only as good as the test the agent can
believe in. We carry four flavours of tests, gated separately:

- **Unit** (`tests/unit/`) — every domain Use Case, every parser, every
  Result/Err contract. ~200 tests, < 0.5s.
- **Integration with fakes** (`tests/integration/`) — every tool round-trips
  through the dispatcher with a fully-faked repo graph. Catches wiring
  drift the moment it lands.
- **Agent transcript replay** (`tests/agent/`) — JSON files that encode
  "this is what a session looks like." Each step asserts envelope
  invariants. If a SKILL ladder or tool description shifts, transcripts
  light up red before a small-LLM agent gets confused.
- **Opt-in real** (`tests/integration_real/`) — slow tests that run
  `flutter`, `dart`, `git` against `tests/fixtures/sample_flutter_app/`.
  Skipped by default; gated by `MCP_REAL=1`.

The default suite is **247 tests in under a second** — fast enough to
run on every save. The full doc lives at
[`docs/testing-procedures.md`](../testing-procedures.md). Four
non-negotiable bars:

1. Every failure carries `next_action`. Tested per Use Case.
2. Every `InvalidArgumentFailure` carries `details.corrected_example`. Tested.
3. BASIC-tier tool descriptions stay ≤ 35 words. Tested.
4. Adding a tool requires updating the integration test's
   `expected_tool_names` set. One fact, hard to forget.

Why this matters: agents don't read READMEs. They read **error envelopes**.
The tests above pin those exact surfaces. Change one, see the test turn
red, fix the agent guidance in the same PR. Drift never accumulates.

## Tier F — five tools that replace repetitive agent work

Late additions; named after the tier they sit in (A through F). These
exist because the agent or Claude was previously chaining 3–5 lower-level
calls every iteration:

- **`scaffold_feature`** — generate Clean-Architecture skeleton (entity,
  failure, repo, use case, BLoC, page, tests) for a feature in
  snake_case. Replaces ~8 boilerplate file writes.
- **`run_quick_check`** — composite "is the working tree healthy?":
  analyzer + format + git status. Skips unit tests; use `quality_gate`
  for the full bar.
- **`grep_logs`** — regex over a saved log artifact with line context.
  Cheaper than `fetch_artifact` + parsing for the common "find the
  stack trace" question.
- **`summarize_session`** — boil the trace down to a 3-line elevator
  pitch (headline / recent successes / recent errors). Different from
  `session_summary` (raw entries) and `tool_usage_report` (per-tool
  stats); this one is for "give me the punchline."
- **`find_flutter_widget`** — scan `lib/` for widget classes whose name
  matches a regex. Returns paths + line numbers. Replaces the agent's
  Glob+Grep+Read dance.

Each Tier-F tool has unit tests under
`tests/unit/test_productivity_tools.py`. Total tool count is now **92**.

## Benchmark — how much faster does this make development?

Honest, anecdotal numbers from the author's daily loop on a Mac (M3 Max,
6 Flutter apps in active development):

| Task                                          | Before MCP | With MCP | Speedup |
| --------------------------------------------- | ---------- | -------- | ------- |
| New feature scaffold (8 boilerplate files)    | ~6 min     | 5 sec    | ~70×    |
| Hot-reload + verify loop (per iteration)      | ~45 sec    | ~8 sec   | ~6×     |
| Multi-project session start (3 apps)          | ~4 min     | ~30 sec  | ~8×     |
| "Why did this test fail?" log archaeology     | ~3 min     | ~20 sec  | ~9×     |
| End-to-end Patrol test (after agent learns it)| ~15 min    | ~5 min   | ~3×     |
| Polish-phone gotcha (locale text in tests)    | catastrophic | not a thing | ∞ |

Where the wins compound:

- **Multi-project parallelism.** Three Claudes can drive three projects
  on three devices simultaneously. Throughput scales roughly linearly
  with locked-down device count.
- **No context-switch cost.** The agent loads `describe_capabilities`
  once and remembers the rest of the session. A human's context-switch
  between "what did I do" and "what's next" is the dominant cost in
  parallel work.
- **Tests replace explanation.** Once a transcript exists, future
  changes can't break the contract silently. The MCP itself becomes
  agent-onboardable in ~2 minutes via `describe_capabilities` +
  `describe_tool`.

Where the wins don't compound:

- One-off CI tasks — the MCP is overkill for "run flutter test once."
- iOS-only flows — limited until iOS 26 DDI lands cleanly. Android is
  the hot path today.
- Real-device emulation in containers — Linux+KVM only; iOS Simulator
  refuses to virtualise. The MCP runs natively on macOS for the
  developer hot loop.

The biggest hidden win: **the MCP itself becomes the standard onboarding
document.** New agent? Point it at `describe_capabilities(level=basic)`
and it has 18 tools; `intermediate` jumps to ~40; `expert` is all 92.
Same tool, three contexts, zero documentation drift.

---

## How to follow along

The repo is at `flutter-dev-agents`. The MCP package is `packages/phone-controll`. For Claude Code:

```bash
git clone https://github.com/michal-giza/flutter-dev-agents ~/Desktop/flutter-dev-agents
cd ~/Desktop/flutter-dev-agents/packages/phone-controll
uv venv --python 3.11 && uv pip install -e ".[dev,ar,http]"
.venv/bin/python -m pytest tests/ -q   # expect: 301 passed, 2 skipped
claude mcp add phone-controll -- $(pwd)/.venv/bin/python -m mcp_phone_controll
```

## Try it yourself — three test scenarios

Paste these into Claude Code (or your local-LLM REPL). Each scenario is
copy-pasteable; the runbook at [`docs/test-runbook.md`](../test-runbook.md)
has expected stdout, pass criteria, and a troubleshooting table per
symptom.

### Scenario A — 4-tool boot sequence (2 min, no device required)

```
> Use phone-controll. Run this 4-tool boot sequence and stop on the
> first ok:false. Show me each envelope's `ok` and (if false)
> `error.next_action`:
>
> 1. describe_capabilities(level="basic")
> 2. check_environment
> 3. list_devices
> 4. inspect_project(project_path=".")
```

**Pass:** all four return `ok: true`. `describe_capabilities` returns
exactly 18 tools in `tool_subset` and a 9-step `recommended_sequence`
starting with `describe_capabilities`.

### Scenario B — Declarative dev loop (5 min, device required)

Edit `examples/templates/dev_iteration.yaml`, replace the two
`REPLACE_*` placeholders, then:

```
> Validate then run examples/templates/dev_iteration.yaml against my
> Flutter project. After it finishes, call summarize_session and
> paste the 3-line headline.
```

**Pass:** A new VS Code window opens on your project. Session
artifacts under `~/.mcp_phone_controll/sessions/<sid>/` include
screenshots + debug logs. The headline reports ≥ 6 successful calls.

### Scenario C — Multi-project parallelism (10 min, 2 devices required)

Two terminals, two `claude` sessions, two different projects + serials.
Both sessions run Scenario B. The second session must **not** acquire
the first session's device.

**Pass:** Each session locks its own serial in
`~/.mcp_phone_controll/locks/`. `release_device` in session 1 doesn't
touch session 2.



For a local 4B model:

```bash
mcp-phone-controll-http --port 8765
ollama pull qwen2.5:7b    # or any tool-calling model
OLLAMA_BASE_URL=http://localhost:11434/v1 \
  MODEL=qwen2.5:7b \
  python examples/agent_loop.py
```

Then in any Claude session:

```
Use phone-controll. Call describe_capabilities(level="basic"), then
inspect_project for /path/to/my/flutter/project, then validate_test_plan
+ run_test_plan against examples/templates/dev_iteration.yaml.
```

Or more honestly: pick one of your projects, plug in your phone, and let an agent try to drive a Patrol test through the full Code → Edit → Hot Reload → Test → Verify loop. When it gets stuck, paste the failure envelope at me and I'll patch the gap.

That's the loop. The MCP isn't the work; the loop *of fixing the MCP via the MCP* is the work. We're building tools to build tools. For one-person companies in 2026, that's the only way the math works.

---

*Source: github.com/<your-handle>/flutter-dev-agents — Apache 2.0. Issues, PRs, and "this broke on my Polish phone" reports all welcome.*
