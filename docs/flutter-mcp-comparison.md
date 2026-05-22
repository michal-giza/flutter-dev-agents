# Comparison: `flutter-dev-agents` vs the official Dart/Flutter MCP Server

> Memo dated 2026-05-22. Purpose: confirm we're not duplicating
> Google's surface before continuing to build, and make explicit
> where we lead, where we're at parity, and where we should
> deprecate or step out of the way.

## TL;DR strategic posture

> **We will lose** if we compete with the Dart/Flutter team on
> commodity plumbing — `pub`, `dart_fix`, `dart_format`, basic
> `launch_app` / `hot_reload`, generic `run_tests`. They own the
> SDK and ship those for free.
>
> **We will win** by leading on opinionated, audit-grade,
> AI-judgment tooling that requires real Flutter taste: the
> seven-domain audit suite (seniority, security, localization,
> dependencies, accessibility, test-quality, app-size), the
> senior-tester loop (design + audit), Patrol integration,
> multi-device orchestration, plan-walker, AR/vision, and the
> operational tools nobody else ships (`pause_ui_automation`,
> bracket-paired profiling, multi-app IDE-window control).

**Action items at the bottom.** No build pivots needed.

## The official Dart/Flutter MCP Server

Maintained by Google's Dart/Flutter team at
`dart-lang/ai/pkgs/dart_mcp_server`. **24 tools** (as of
2026-05-22). Categories:

| Category | Tools |
|---|---|
| **analysis** | `analyze_files`, `lsp` |
| **dev session** | `launch_app`, `stop_app`, `hot_reload`, `hot_restart`, `list_running_apps`, `dtd` |
| **observability** | `get_app_logs`, `get_runtime_errors` |
| **inspector / VM** | `widget_inspector`, `call_vm_service_method` |
| **devices** | `list_devices`, `flutter_driver_command` |
| **code quality** | `dart_fix`, `dart_format` |
| **testing** | `run_tests` |
| **dependencies** | `pub`, `pub_dev_search` |
| **source** | `read_package_uris`, `rip_grep_packages` |
| **scaffolding** | `create_project` |
| **editor** | `get_active_location` |
| **workspace** | `roots` |

Sources:
- [docs.flutter.dev/ai/mcp-server](https://docs.flutter.dev/ai/mcp-server)
- [GitHub: dart-lang/ai/pkgs/dart_mcp_server](https://github.com/dart-lang/ai/tree/main/pkgs/dart_mcp_server)

## Side-by-side: ours (135) vs theirs (24)

### Direct overlap — they likely win long-term (12 tools we have)

| Our tool | Their tool | Verdict |
|---|---|---|
| `dart_analyze` | `analyze_files` | parity; their `lsp` is richer |
| `dart_fix` | `dart_fix` | exact match — defer to them |
| `dart_format` | `dart_format` | exact match — defer to them |
| `flutter_pub_get` | `pub` | their `pub` is more complete |
| `flutter_pub_outdated` | `pub` (with subcommand) | theirs subsumes ours |
| `start_debug_session` | `launch_app` | parity; ours has lock integration |
| `stop_debug_session` | `stop_app` | parity |
| `restart_debug_session` | `hot_reload` + `hot_restart` | parity (theirs cleaner) |
| `list_debug_sessions` | `list_running_apps` | parity |
| `read_debug_log` / `tail_debug_log` | `get_app_logs` | parity (ours has filtering) |
| `call_service_extension` / `vm_evaluate` / `vm_list_isolates` | `call_vm_service_method` | parity |
| `dump_widget_tree` / `dump_render_tree` / `toggle_inspector` | `widget_inspector` | parity |
| `run_unit_tests` / `run_integration_tests` / `run_widget_test` | `run_tests` | parity (ours framework-aware) |
| `list_devices` | `list_devices` | exact match |

**~14 of our 135 tools are commodity overlap. ~10% surface area.**

### Where we lead — they don't ship this (121 unique tools)

#### 🔑 The audit suite (7 verticals + composite) — our killer differentiator
| Tool | What | Their offering |
|---|---|---|
| `audit_code_seniority` (24 rules) | architecture grade A-F | **none** |
| `audit_security` (20 rules) | OWASP MASVS scanner | **none** |
| `audit_localization` (16 rules) | i18n hygiene | **none** |
| `audit_dependencies` (14 rules) | supply-chain audit | **none** |
| `audit_accessibility` | WCAG 2.2 on running UI | **none** |
| `audit_test_quality` (28 rules) | post-write test audit | **none** |
| `audit_release_readiness` | 5-domain composite verdict | **none** |

This is the moat. Building it requires Flutter taste encoded as
rules; Google's official MCP is generic-purpose and won't ship
opinionated rubrics.

#### 🔑 The senior-tester loop
| Tool | What | Their offering |
|---|---|---|
| `propose_test_scenarios` | research-grounded scenarios | partial via `run_tests` |
| `recommend_test_path` | 7 canonical strategies | **none** |
| `design_test_plan` | pre-write discipline | **none** |
| `audit_test_quality` | post-write audit | **none** |

#### 🔑 Device-touching UI driving (the whole pyramid)
- `tap`, `tap_text`, `tap_and_verify`, `swipe`, `type_text`, `press_key`
- `take_screenshot`, `start_recording`, `stop_recording`
- `dump_ui`, `find_element`, `wait_for_element`, `extract_ui_graph`
- `prepare_for_test`, `clear_app_data`, `grant_permission`
- iOS: `setup_webdriveragent`, `start_wda_on_simulator`
- **`pause_ui_automation` / `resume_ui_automation`** (the AVD operational fix nobody else will ship)

Their `flutter_driver_command` exposes generic flutter_driver. We
go much deeper: real-device tap-with-OCR-verify, multi-platform
device pools, locking, capture/record.

#### 🔑 Profiling + diagnostics
- Memory: `memory_summary`, `allocation_profile`,
  `detect_undisposed_controllers`, `find_retaining_path`,
  `take_heap_snapshot`
- Frames: `start_frame_profile` / `stop_frame_profile` (bracket-paired)
- App size: `analyze_app_size`, `compress_png`, `prune_originals`

They have raw VM-service access; we have curated rubrics + bracket
discipline + size-baseline diff.

#### 🔑 Patrol integration
- `run_patrol_test`, `run_patrol_suite`, `list_patrol_tests`

Patrol is the Flutter community's premier integration-test
framework. They don't integrate it; we do.

#### 🔑 Plan walker (YAML test plans)
- `run_test_plan`, `validate_test_plan`

Declarative test plans with phase state machines (`PRE_FLIGHT`,
`DEV_SESSION_START`, `HOT_RELOAD`, etc.). Composable, validatable,
agent-driven.

#### 🔑 Multi-device orchestration
- `select_device`, `release_device`, `force_release_lock`, `list_locks`

When N Claude sessions run in parallel against M devices, our lock
layer prevents collisions. Their MCP has no concept of locking.

#### 🔑 IDE multi-window orchestration
- `open_project_in_ide`, `close_ide_window`, `focus_ide_window`,
  `list_ide_windows`, `is_ide_available`, `write_vscode_launch_config`

We can drive multiple VS Code windows in parallel for the
factory loop. They don't touch IDE process management.

#### 🔑 Skill library / CRAG
- `index_project`, `recall`, `recall_corrective`, `promote_sequence`,
  `replay_skill`, `list_skills`

Corrective Retrieval-Augmented Generation over project history.
Lets the agent learn from prior sessions. Their MCP is stateless.

#### 🔑 AR / vision
- `calibrate_camera`, `detect_markers`, `wait_for_marker`,
  `infer_camera_pose`, `assert_pose_stable`,
  `wait_for_ar_session_ready`, `compare_screenshot`,
  `save_golden_image`, `inspect_image_safety`

For ARCore + Filament apps. Their MCP has no AR awareness.

#### 🔑 Virtual devices (broader than `list_devices`)
- `boot_simulator`, `list_simulators`, `start_emulator`,
  `list_avds`, `stop_virtual_device`

Full lifecycle for iOS sims + Android AVDs.

#### 🔑 Misc differentiators
- `notify_webhook` — outbound notifications
- `describe_capabilities` / `describe_tool` — meta-introspection
- `test_deep_link` — Android `am start -W` / iOS `simctl openurl`
- `mcp_ping` / `check_environment` / `disk_usage` — self-checks
- `patch_apply_safe` — safe code patches with rollback
- `ocr_screenshot` — OCR over screenshots
- `narrate`, `tool_usage_report`, `session_summary`,
  `summarize_session` — session observability
- `recall_corrective`, `promote_sequence` — learning loop

### Where they lead (or have something we don't)

| Their tool | Gap | Our response |
|---|---|---|
| `pub_dev_search` | No pub.dev search in ours | **Low priority** — their official one beats anything we'd ship |
| `lsp` | No LSP integration | **Skip** — out of scope; we focus on running-app intelligence, not editor symbol-lookup |
| `get_active_location` | No editor cursor awareness | **Skip** — IDE-coupling we don't want |
| `rip_grep_packages` | We don't grep over packages | **Worth considering** — could add `grep_packages` for source search; ~½ day |
| `create_project` | We scaffold features not whole projects | **Worth considering** — `scaffold_project` would round out our scaffold story; ~½ day |
| `dtd` | Direct DTD connection | **Skip** — we go via `flutter run --machine` which is sufficient |

**Total gap: ~3 small tools we could optionally add. None blocking.**

## Action items

### 1. Stop shipping commodity dupes
- **No new tools** that overlap with their `dart_fix` / `dart_format`
  / `pub` / `analyze_files`. The 4 we already have stay, marked
  in docs as "commodity — defer to dart_mcp_server when their
  surface stabilizes."

### 2. Lead harder on the differentiated layer
- The audit suite + senior-tester loop **is the product**.
- Our portfolio dogfooding signal is the moat. The official MCP
  team won't ship opinionated rubrics; we will.

### 3. Optional small fills (~1 day total)
- `grep_project_sources` — wrap ripgrep over our project (we
  already index it; this is a 1-hour add)
- `scaffold_project` — `flutter create` wrapper with sensible
  defaults
- `pub_dev_search` — don't bother; theirs is better

### 4. Compatibility note for users
- Add a section to `README.md` clarifying that our MCP **stacks
  with** the official Dart/Flutter MCP. Both can run in the same
  Claude session via `claude mcp add`. Ours adds the audit /
  device-driving / Patrol / multi-device layer on top of their
  pure-SDK surface.

### 5. Watch list (re-check quarterly)
- If the official MCP ships an audit equivalent → deprecate
  ours and contribute upstream
- If they ship Patrol integration → deprecate ours
- If they ship multi-device locking → deprecate ours

History suggests they ship infrastructure, not opinionated audits.
The differentiation is durable.

## Bottom line

We have **~10% commodity overlap** (14 of 135 tools) and **~90%
unique surface** (121 tools the official MCP doesn't ship). The
strategic posture from before the memo holds:

> **Lead on opinionated audit-grade tooling. Defer to Google on
> SDK plumbing. Don't pivot.**

Sources:
- [Dart and Flutter MCP server (docs.flutter.dev)](https://docs.flutter.dev/ai/mcp-server)
- [dart-lang/ai/pkgs/dart_mcp_server (GitHub)](https://github.com/dart-lang/ai/tree/main/pkgs/dart_mcp_server)
- [Voxturrlabs: MCP Servers for Dart and Flutter Developers (2026 Guide)](https://voxturrlabs.com/blog/mcp-servers-for-dart-and-flutter-developers-2026/)
- [Very Good Ventures: 7 MCP Servers Every Dart and Flutter Developer Should Know](https://verygood.ventures/blog/7-mcp-servers-every-dart-and-flutter-developer-should-know/)
