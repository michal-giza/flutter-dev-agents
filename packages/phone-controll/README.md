# mcp-phone-controll

A local MCP server for **building, deploying, testing, and visually verifying** Android and iOS apps on real devices — Patrol-first for Flutter, framework-routing for everything else, with **autonomous-agent and AR/Vision support** out of the box.

## Two audiences, one server

### A. Claude Code users (human-in-the-loop)

Stdio MCP, register once, talk in natural language:

```bash
claude mcp add phone-controll -- /path/to/.venv/bin/python -m mcp_phone_controll
```

Then tell Claude: *"check_environment, list_devices, run the Patrol auth test on my Galaxy."* The accompanying skill (`mcp-phone-controll-testing`) keeps Claude on a state machine: phase-gated, decline-aware, screenshot-disciplined.

### B. Autonomous agents (any local LLM)

OpenAI-compat HTTP adapter — runs alongside the stdio MCP, exposes the same 41 tools as OpenAI function-calls:

```bash
mcp-phone-controll-http --port 8765
# GET  http://localhost:8765/tools          → OpenAI function schemas
# POST http://localhost:8765/tools/{name}   → MCP envelope
# GET  http://localhost:8765/openapi.json   → OpenAPI 3.0 spec
# POST http://localhost:8765/agent/chat     → optional LLM proxy + tool loop
```

Works with **Ollama, vLLM, LM Studio, llama.cpp, or any OpenAI-compat endpoint**. Point your agent framework at `/tools` and dispatch via `/tools/{name}`. See `examples/agent_loop.py` for a reference loop.

## Why this is shipped this way

Three problems agents kept hitting before:
- **Locale-coupled tests** — hardcoded display text broke in Polish. → Patrol-first with widget Keys; raw `tap_text` is "system UI only" by description.
- **State drift** — agents took screenshots after a flow had already aborted. → Explicit PHASE state machine in the skill, declarative YAML plans in `run_test_plan`, audit trail via `session_summary`.
- **Tooling fragility** — agents wandered into "let me just retry" loops on missing binaries. → `check_environment` returns a structured doctor report with `next_action` fix commands; every `Failure` carries a canonical `next_action` field.

## Tools (41 total)

**Preflight & introspection**
- `check_environment` — DOCTOR. Run first. Reports adb/flutter/patrol/pymobiledevice3 status with fixes.
- `describe_capabilities` — what platforms, frameworks, gates, vision ops are supported.
- `inspect_project` — what kind of project lives at a path, which test frameworks apply.
- `list_devices` / `select_device` / `get_selected_device`
- `new_session` / `get_artifacts_dir`
- `session_summary` — audit trail of every tool call this session.

**Build & install**
- `build_app` (Flutter APK or IPA, branched by platform)
- `install_app` / `uninstall_app`

**Lifecycle**
- `prepare_for_test` — atomic CLEAN handoff: stop + clear + home + evidence screenshot.
- `launch_app` / `stop_app` / `clear_app_data` / `grant_permission`

**Patrol (Flutter, locale-independent)**
- `list_patrol_tests` / `run_patrol_test` / `run_patrol_suite`

**Test plans (declarative, peer-reviewable)**
- `run_test_plan(plan_path | plan_yaml)` — interprets a v1 YAML plan, walks phases, enforces decline branches, captures artifacts.

**Generic test orchestration**
- `run_unit_tests` / `run_integration_tests` (auto-routes to Patrol when available)

**Observation**
- `take_screenshot` (binary-safe; PNG signature verified) / `start_recording` / `stop_recording`
- `read_logs` / `tail_logs`

**AR / Vision** (requires `[ar]` extra)
- `compare_screenshot(actual, golden, tolerance)` — pixel diff for AR overlay regression.
- `detect_markers(image, dictionary="DICT_4X4_50")` — ArUco fiducials.
- `infer_camera_pose(image, marker_id, marker_size_m)` — pose from a known marker.
- `wait_for_marker(marker_id, timeout_s)` — scene-readiness gate for AR phases.

**Raw UI driving — system UI only**
- `tap` / `tap_text` / `swipe` / `type_text` / `press_key`
- `find_element` / `wait_for_element` / `dump_ui` / `assert_visible`

## Architecture

Clean Architecture, three layers, presentation shell:

```
domain/         pure — entities, Result, Failures (with next_action), repository protocols, use cases
infrastructure/ outbound adapters — adb, flutter, patrol, pymobiledevice3, uiautomator2, WDA, OpenCV, YAML
data/           parsers + repository implementations + composites
presentation/   MCP stdio server — tool registry maps tool names to use cases
adapters/       OpenAI-compat HTTP adapter (FastAPI), agent loop proxy
container.py    composition root
```

Composites route by:
- **Platform** (`CompositeDeviceRepository` + `CachingPlatformResolver`) for device/UI/lifecycle/observation calls.
- **Test framework** (`CompositeTestRepository` + `ProjectInspector`) for test execution.

Errors are returned, not thrown. Every use case returns `Result[T]` with a typed `Failure` carrying a canonical `next_action`. The MCP layer translates that into a uniform `{ok, data, error: {code, message, next_action, details}}` envelope — both stdio and HTTP.

## Setup

External prerequisites:

**Android:** `adb` (`brew install --cask android-platform-tools`), USB debugging, `python -m uiautomator2 init` once per device.

**iOS:** Xcode + CLT, trusted device, `pymobiledevice3 amfi enable-developer-mode` + `mounter auto-mount` + `sudo pymobiledevice3 remote tunneld` running. WebDriverAgent built once per device for UI driving.

**Flutter:** `flutter` on PATH. For Patrol: `dart pub global activate patrol_cli`.

**AR (optional):** `uv pip install -e ".[ar]"` for OpenCV.

**HTTP adapter (optional):** `uv pip install -e ".[http]"`.

Install:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev,ar,http]"   # everything
pytest                               # full suite, no device, no toolchain needed
```

Run `check_environment` from Claude (or `curl http://localhost:8765/tools/check_environment -X POST`) to verify the toolchain in one call.

## Concurrent sessions (multi-Claude / device farm)

Each Claude Code conversation spawns its own MCP subprocess. To prevent two sessions from driving the same physical device simultaneously, **`select_device` acquires a cross-process device lock**. Locks live under `~/.mcp_phone_controll/locks/<serial>.lock` and include the holding session's PID.

- `select_device(serial)` — acquires the lock. Returns `DeviceBusyFailure` (with `next_action: wait_or_force`) if another session holds it.
- `select_device(serial, force=true)` — overrides another session's lock (use sparingly).
- `release_device()` — releases the lock for the currently selected device. **Always call this at end of session.**
- `list_locks` — see who's holding what across all sessions.
- `force_release_lock(serial)` — admin tool for stuck locks (e.g. a session crashed).

**Stale-lock recovery:** if the holder PID is gone (process killed, OOM, kernel panic), the next `acquire` for that serial automatically reclaims it. `list_locks` filters out stale ones.

**Process-exit cleanup:** the container registers an `atexit` hook that releases this session's locks on graceful shutdown. The PID-staleness check is the safety net for non-graceful exits.

Example three-session factory layout:

| Session | Device | Lock |
|---|---|---|
| Claude #1 (in `checkaiapp/`) | `R3CYA05CHXB` (Galaxy, physical) | `~/.mcp_phone_controll/locks/R3CYA05CHXB.lock` |
| Claude #2 (in CI runner) | `emulator-5554` (Android AVD) | `~/.mcp_phone_controll/locks/emulator-5554.lock` |
| Claude #3 (in `another_app/`) | `00008120-...` (iPhone simulator UDID) | `~/.mcp_phone_controll/locks/00008120-....lock` |

All three run in parallel without conflict. If Claude #2 calls `select_device("R3CYA05CHXB")`, it gets `DeviceBusyFailure` with the holder's session id and PID in `details`.

## Virtual devices (emulators + simulators)

Both Android emulators (AVDs) and iOS simulators are first-class — same MCP tools, same Patrol tests, same artifacts. `Device.device_class` is one of `physical | emulator | simulator | unknown`; the resolver caches the kind so lifecycle/observation routes correctly per call.

Tools:
- `list_avds`, `start_emulator(avd_name, headless?)`, `stop_virtual_device(serial)`
- `list_simulators(include_shutdown?)`, `boot_simulator(name_or_udid)`

What works on each device class:

|                         | Physical Android | Android Emulator | Physical iOS | iOS Simulator |
|-------------------------|:----------------:|:----------------:|:------------:|:-------------:|
| Patrol UI tests         | ✅               | ✅               | ✅           | ✅            |
| Build/install/launch    | ✅               | ✅               | ✅           | ✅ (.app)     |
| `tap_text` / `find_*`   | ✅               | ✅               | via WDA      | via Patrol    |
| `take_screenshot`       | ✅               | ✅               | via tunneld  | ✅ simctl     |
| `read_logs`/`tail_logs` | ✅ logcat        | ✅ logcat        | via tunneld  | ✅ log stream |
| `clear_app_data`        | ✅               | ✅               | ❌           | ✅ (uninstall)|
| `grant_permission`      | ✅ pm grant      | ✅ pm grant      | ❌           | ✅ simctl privacy |
| Real **camera/AR**      | ✅               | ❌               | ✅           | ❌            |
| Vision / ML Kit on real frames | ✅       | ❌               | ✅           | ❌            |
| Locale matrix coverage  | ✅               | ✅               | ✅           | ✅            |
| **Use for AR/Vision**   | YES              | NO               | YES          | NO            |
| **Use for CI smoke**    | OK               | YES              | OK           | YES           |

Recommended split:
- **Physical** (Galaxy + iPhone) — AR, Vision, ML Kit, anything camera-driven, real ad SDKs (UMP/ATT).
- **Emulator + Simulator** — fast CI smoke, locale matrix, business-logic Patrol tests, screenshot regression for non-AR screens.

## iOS simulator: install build hint

`flutter build ios --simulator` produces `build/ios/iphonesimulator/Runner.app`. Pass that path to `install_app(bundle_path=...)` after `boot_simulator(...)` and `select_device(<udid>)`. Note: simulator builds don't need code-signing; physical iOS builds do.

## AR stand setup convention

For repeatable AR/Vision testing across operators:

- **Marker dictionary:** ArUco `DICT_4X4_50` — small, robust, low false positives.
- **Markers:** ≥ 3 markers at known positions; sizes recorded in `tests/fixtures/stand_layout.yaml`.
- **Coordinate frame:** marker id=0 origin; +X right, +Y up, +Z away from device.
- **Scene control:** matte stand, consistent overhead diffuser lighting.

This convention lets `infer_camera_pose` produce comparable results across sessions and `wait_for_marker` deterministically gate AR test phases.

## Adding a new test framework

1. Add a `TestFramework` enum value (e.g. `XCUITEST`).
2. Implement `TestRepository` for that framework.
3. Add a `ProjectInspector` that recognises projects of that type.
4. Append the inspector to the list in `container.py`.
5. Register the runner in `framework_runners` keyed by your enum value.

No use-case changes, no MCP tool changes. The composite layer routes automatically.

## Layout

```
src/mcp_phone_controll/
  domain/
    result.py / failures.py / entities.py / repositories.py
    usecases/
      base.py / devices.py / build_install.py / lifecycle.py
      ui_input.py / ui_query.py / observation.py / artifacts.py
      testing.py / patrol.py / projects.py / doctor.py
      discovery.py / preparation.py / plan.py / vision.py
  infrastructure/
    process_runner.py
    adb_client.py / flutter_cli.py / patrol_cli.py / pymobiledevice3_cli.py
    uiautomator2_factory.py / wda_factory.py
    yaml_plan_loader.py
  data/
    parsers/
    repositories/
      adb_*.py / ios_*.py / wda_*.py / flutter_*.py
      patrol_repository.py
      flutter_project_inspector.py / composite_project_inspector.py
      system_environment_repository.py
      static_capabilities_provider.py
      in_memory_session_state_repository.py / in_memory_session_trace_repository.py
      opencv_vision_repository.py
      yaml_plan_executor.py
      composite/                   platform-routing composites
  presentation/
    serialization.py / tool_registry.py / mcp_server.py
  adapters/
    openai_compat.py / schemas.py / __main__.py
  container.py
  __main__.py

examples/
  templates/                        ready-to-fill plan YAMLs
  agent_loop.py                     reference autonomous loop

tests/
  unit/                             fast, no toolchain
  integration/                      dispatcher + adapter
  integration_real/                 opt-in, needs device + flutter
  fixtures/                         golden images, sample app, stand layout
```

## Testing strategy

- Use cases tested against fake repositories — no subprocess, no phone.
- Parsers (adb-devices, logcat, flutter test JSON, pymobiledevice3 usbmux, YAML plans) are pure functions with fixture tests.
- Composite routing tested with fakes (platform + framework).
- HTTP adapter tested via FastAPI TestClient — `/tools`, `/tools/{name}`, `/openapi.json`, error envelopes.
- Vision tested with on-the-fly OpenCV-generated fixture images (skips cleanly if `cv2` not installed).
- 84 tests run in under a second.

## What's deferred (not blockers)

- iOS 26 developer-services workaround — needs Xcode iOS-26 DDI; revisit when it lands.
- Multi-device parallel runs (architecture supports; not built).
- Native frameworks (XCUITest / Espresso / Detox / Playwright) — extension recipe documented.
- Network conditioning, persistent agent memory across sessions, shared device-farm model.
