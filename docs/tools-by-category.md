# Tools, by what you're trying to do

`docs/tools.md` is auto-generated and lists all 110 tools
alphabetically — useful for reference, useless for discovery.
This page groups them by user goal so you can find the right one
without reading 110 entries.

If you're new, the BASIC tier (★) is enough for 90% of workflows.

| Tier | Visible at |
|---|---|
| ★ BASIC | every host, 26 tools |
| ◆ INTERMEDIATE | `MCP_TOOL_TIER=intermediate`, ~40 tools |
| ◇ EXPERT | unset / `expert` / `all`, all 110 tools |

---

## "I just installed this — confirm it works"

| Tool | Tier | What it does |
|---|---|---|
| `mcp_ping` | ★ | Returns version, git SHA, tool count, image-cap value, available backends. ALWAYS call this first when something feels off. |
| `set_agent_profile` | ★ | Switch behavior between "human-in-loop" and "autonomous" agent profiles. |
| `describe_capabilities` | ★ | Schema for the plan-walker (phases, drivers). Use when authoring YAML test plans. |
| `describe_tool` | ★ | Per-tool detail — args, return shape, examples. Use mid-session when the LLM forgets a signature. |
| `check_environment` | ★ | Doctor report: adb, flutter, patrol, pymobiledevice3 status. Returns red items with concrete fix commands. |
| `inspect_project` | ★ | Detects pubspec, Flutter version, package_id, flavor configs. Run when entering a new project dir. |

## "I want to drive a real phone"

| Tool | Tier | What it does |
|---|---|---|
| `list_devices` | ★ | All connected/visible devices (USB + WiFi + emulator + sim) with serial/UDID, platform, model. |
| `select_device` | ★ | Acquire the per-device filesystem lock. Required before any device-targeting tool in this session. |
| `get_selected_device` | ★ | Current session's locked device. Useful for confirming "am I about to drive the right one". |
| `release_device` | ★ | Free the lock. Run at session end. Idempotent. |
| `list_locks` | ◆ | Who holds what across ALL sessions on this machine. Cross-session visibility. |
| `force_release_lock` | ◇ | Break a stale lock when the holder process is gone. Use after `list_locks`. |

## "I want to see what's on screen"

| Tool | Tier | What it does |
|---|---|---|
| `take_screenshot` | ★ | PNG into the session dir. Auto-caps at 1600 px long-edge. Original preserved at `<path>.orig.png`. |
| `inspect_image_safety` | ★ | PRE-Read probe for any PNG. Returns `long_edge_px`, `mcp_produced`, `next_action`. Call before reading any image you didn't get from `take_screenshot`. |
| `compress_png` | ★ | Recompress arbitrary PNG with palette + zlib. Use when an external screenshot (computer-use, raw adb) is too big. |
| `dump_ui` | ◆ | UI hierarchy as XML. Use when `tap_text` can't find the element. |
| `find_element` | ◆ | Single element by text/resource-id/class. Returns bounds + clickability. |
| `extract_ui_graph` | ◇ | UI tree as a graph (nodes + edges). For ML-assisted layout analysis. |
| `ocr_screenshot` | ◇ | Tesseract OCR on a screenshot. Use when the UI tree doesn't expose text (canvas-rendered content). |

## "I want to tap, swipe, type"

| Tool | Tier | What it does |
|---|---|---|
| `tap` | ◆ | Tap by logical-point coordinates. NB: NOT pixel coordinates — see `operational-gotchas.md`. |
| `tap_text` | ◆ | Tap by visible text. NFC + NBSP fold, case-fold fallback. Use `exact=True` for canonical labels, `system=True` for OS dialogs. |
| `tap_and_verify` | ★ | Tap + capture + assert follow-up text. The "verify-after-action" discipline tool. |
| `swipe` | ◆ | x1,y1 → x2,y2 with duration. Logical points. |
| `type_text` | ◆ | Send keystrokes to the focused field. |
| `press_key` | ◆ | Hardware/system keys (home, back, recent, vol up/down). |
| `wait_for_element` | ◆ | Block until an element appears, with timeout. |
| `assert_visible` | ◆ | Pass/fail check that an element is on screen NOW. |
| `assert_no_errors_since` | ★ | Confirm no error logs in the last N seconds. Use right after a tap to catch silent failures. |

## "I want to manage app lifecycle"

| Tool | Tier | What it does |
|---|---|---|
| `launch_app` | ★ | Start an app by package_id (Android) or bundle_id (iOS). |
| `stop_app` | ◆ | Force-stop a running app. |
| `clear_app_data` | ◆ | Wipe app data + cache. Use for clean-slate test runs. |
| `grant_permission` | ◆ | adb-grant a runtime permission (Android) or set TCC (iOS). Bypasses the dialog. |
| `prepare_for_test` | ★ | Composite: clear data → grant common permissions → launch with proper flags. The "begin a test from a known state" tool. |
| `install_app` | ◆ | Push an APK / IPA / .app bundle. Path-traversal guarded. |
| `uninstall_app` | ◆ | Remove an installed package. |
| `build_app` | ◆ | `flutter build` with mode/platform/flavor. Background process; returns when done. |

## "I want to run tests"

| Tool | Tier | What it does |
|---|---|---|
| `run_patrol_test` | ◆ | Single Patrol integration test against the locked device. Captures pass/fail per `testWidgets` block. |
| `run_patrol_suite` | ◆ | All Patrol tests in `integration_test/`. |
| `run_unit_tests` | ◆ | `flutter test` for unit/widget tests. No device needed. |
| `run_integration_tests` | ◆ | `flutter test integration_test/`. |
| `list_patrol_tests` | ◆ | Discover available `testWidgets` blocks without running them. |
| `run_test_plan` | ★ | Execute a YAML test plan (phases + drivers + capture). The declarative entry point. |
| `validate_test_plan` | ★ | Pre-flight check on a plan: schema validation, semantic warnings. Run before `run_test_plan`. |
| `run_quick_check` | ◇ | analyzer + format + git-status — pre-commit-grade health check. |

## "I want a debug session (hot-reload, etc.)"

| Tool | Tier | What it does |
|---|---|---|
| `start_debug_session` | ◆ | `flutter run --machine`. Returns `vm_service_uri`, `app_id`, `session_id`. |
| `restart_debug_session` | ◆ | Hot reload (default) or hot restart (`full_restart=True`). |
| `stop_debug_session` | ◆ | Clean shutdown of the running app and the daemon. |
| `list_debug_sessions` | ◆ | Multiple concurrent debug sessions visible across this process. |
| `read_debug_log` | ◆ | Recent N seconds of debug-log output, filtered by level. |
| `tail_debug_log` | ◇ | Stream until a pattern matches or timeout. |
| `call_service_extension` | ◇ | Generic `ext.flutter.*` invocation. |
| `dump_widget_tree` | ◇ | Convenience wrapper for `ext.flutter.debugDumpApp`. |
| `dump_render_tree` | ◇ | Same, for the render tree. |
| `toggle_inspector` | ◇ | Turn Flutter Inspector on/off remotely. |
| `vm_list_isolates` | ◇ | DAP-lite: list running isolates by ID. |
| `vm_evaluate` | ◇ | DAP-lite: evaluate a Dart expression in a running isolate. |

## "I want to drive my IDE"

| Tool | Tier | What it does |
|---|---|---|
| `open_project_in_ide` | ◆ | `code -n <path>` — opens a fresh VS Code window. Tracks PID. |
| `list_ide_windows` | ◆ | Windows this MCP process owns. |
| `close_ide_window` | ◆ | Best-effort close by project path or window id. |
| `focus_ide_window` | ◇ | Raise a window to front (macOS osascript). |
| `is_ide_available` | ◇ | Health check + version string. |
| `write_vscode_launch_config` | ◇ | Generate `.vscode/launch.json` for a Flutter project. |

## "I want to read logs"

| Tool | Tier | What it does |
|---|---|---|
| `read_logs` | ★ | Last N seconds of logcat / NSLog, filtered by level + tag. |
| `tail_logs` | ◆ | Block until a pattern appears in logs. |
| `grep_logs` | ◇ | Pattern-match over a saved log file. |
| `assert_no_errors_since` | ★ | Pass/fail: no `level=error` since timestamp T. |

## "I want to manage emulators / simulators"

| Tool | Tier | What it does |
|---|---|---|
| `list_avds` | ◆ | Android Virtual Devices on this machine. |
| `start_emulator` | ◆ | Boot an Android emulator by AVD name. |
| `list_simulators` | ◆ | iOS Simulators (xcrun simctl list). |
| `boot_simulator` | ◆ | Start an iOS sim by UDID. |
| `stop_virtual_device` | ◆ | Shutdown emulator or simulator. |
| `setup_webdriveragent` | ◆ | One-time WDA build for an iPhone. Requires `team_id` for physical devices. |
| `start_wda_on_simulator` | ◆ | Spawn `xcodebuild test-without-building` against a sim, wait for WDA to listen. |

## "I want code-quality gates"

| Tool | Tier | What it does |
|---|---|---|
| `dart_analyze` | ◆ | `dart analyze` with severity filtering. |
| `dart_fix` | ◇ | `dart fix --apply`. |
| `dart_format` | ◆ | `dart format`. |
| `flutter_pub_get` | ◇ | `flutter pub get`. |
| `flutter_pub_outdated` | ◇ | `flutter pub outdated`, structured. |
| `quality_gate` | ◆ | Composite: analyze + format + tests. The pre-PR check. |
| `patch_apply_safe` | ◇ | Apply a unified diff with `--check` first, no shell escape. Subprocess-injection audited. |

## "I want to capture release-mode artifacts"

| Tool | Tier | What it does |
|---|---|---|
| `capture_release_screenshot` | ◇ | Build release flavor, install, launch, screenshot at multiple device classes. For App Store / Play Store store listings. |
| `save_golden_image` | ◇ | Snapshot a known-good frame for visual-diff regression. |
| `compare_screenshot` | ◇ | Pixel-diff vs a saved golden, returns SSIM + per-region delta. |

## "I want to manage sessions + artifacts"

| Tool | Tier | What it does |
|---|---|---|
| `new_session` | ★ | Start a fresh session dir. Use when switching projects or hard-resetting. |
| `session_summary` | ★ | Audit trail of every tool call in the current session. The "what did I just do" tool. |
| `summarize_session` | ★ | One-paragraph narrative summary. Better for end-of-session reports than raw trace. |
| `tool_usage_report` | ◇ | Aggregate usage stats. "Which tools earn their tier" analysis. |
| `get_artifacts_dir` | ★ | Path to current session's artifacts dir. |
| `fetch_artifact` | ◇ | Read a file from the session dir. Path-traversal guarded. |
| `disk_usage` | ◇ | Breakdown of session-dir bytes by bucket (screenshots, originals, logs, recordings, goldens, release). |
| `prune_originals` | ◇ | Delete `.orig.png` files older than N days. Default `MCP_ORIG_RETENTION_DAYS=14`. |
| `start_recording` / `stop_recording` | ◇ | Screen recording. |

## "I want skills / promotion / replay"

| Tool | Tier | What it does |
|---|---|---|
| `list_skills` | ◇ | Voyager-style skill library: previously-promoted tool sequences. |
| `promote_sequence` | ◇ | Save a successful flow as a named skill (params + tool order + verification). |
| `replay_skill` | ◇ | Re-run a saved skill against the current device. Idempotent. |

## "I want retrieval (codebase search)"

| Tool | Tier | What it does |
|---|---|---|
| `index_project` | ◇ | Build the vector index of a project's files. Requires `[rag]` extra (Qdrant + fastembed). |
| `recall` | ★ | Query the index. Lighter than reading 8 KB of code. |
| `recall_corrective` | ◇ | CRAG-style query: tries top-k, evaluates relevance, falls back to web search if low confidence. |

## "I want UI exploration / authoring help"

| Tool | Tier | What it does |
|---|---|---|
| `find_flutter_widget` | ◇ | Search project source for widget patterns (Button + key, GestureDetector + onTap, etc.). |
| `list_missing_widget_keys` | ◇ | Scan `lib/` for tap-target widgets missing a `key:` param. The highest-leverage selector-hygiene diagnostic. |
| `scaffold_feature` | ◇ | Generate the Clean-Architecture skeleton for a new feature (entity / use case / bloc / page). |

## "I want vision / AR"

| Tool | Tier | What it does |
|---|---|---|
| `detect_markers` | ◇ | ArUco/QR detection in a captured frame. Requires `[ar]` extra (OpenCV). |
| `infer_camera_pose` | ◇ | 6DoF pose estimation from detected markers. |
| `calibrate_camera` | ◇ | Multi-frame calibration to recover intrinsics. |
| `wait_for_marker` | ◇ | Block until a marker appears (or timeout). |
| `wait_for_ar_session_ready` | ◆ | Block until the app's AR session reports `isReady=true`. |
| `assert_pose_stable` | ◆ | Pass/fail: pose hasn't drifted past threshold in N frames. |

## "I want orchestration / chaining"

| Tool | Tier | What it does |
|---|---|---|
| `narrate` | ◇ | Emit a structured "I'm about to do X because Y" event. For long autonomous loops where post-hoc tracing matters. |
| `notify_webhook` | ◇ | Slack / Discord / generic POST. Off by default; require `MCP_WEBHOOK_ALLOWLIST`. |
| `attach_debug_session` | ◇ | Connect to a `flutter run` started outside the MCP, by VM service URI. |

---

## How to find a tool fast in your editor

```bash
# Search all tool names from the live registry:
python3 -c "
from mcp_phone_controll.container import build_runtime
_, d = build_runtime()
for t in d.descriptors:
    print(f'{t.name:35s} {t.description[:80]}')
" | grep -i <keyword>
```

Or in a Claude session:

```
Using phone-controll, run describe_capabilities and filter the tool
list for ones matching "screenshot". Tell me what each returns.
```

---

## Tier discipline

If you're authoring a new tool, the placement decision is:

- **BASIC** if (a) it's part of the canonical happy path OR (b) it's
  a recovery tool the agent MUST be able to reach when something
  goes wrong. Cap is ~30 tools; keep it lean.
- **INTERMEDIATE** if it's part of a routine workflow (build,
  install, debug, IDE) that small-LLM agents shouldn't have to
  reason about until they're ready.
- **EXPERT** for everything else. Anything specialized, anything
  destructive, anything that requires composition of multiple
  prior steps.

See `packages/phone-controll/src/mcp_phone_controll/domain/tool_levels.py`
for the canonical source. The test
`test_basic_tool_descriptions_within_word_limit` (35-word cap) and
`test_basic_subset_is_reasonable_for_host_ceilings` (30-tool cap)
pin the invariants.
