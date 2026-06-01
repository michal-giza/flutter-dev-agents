# Comparison: `flutter-dev-agents` vs the Flutter MCP ecosystem

> Memo originally dated 2026-05-22, **updated 2026-05-23** with
> Maestro MCP (mobile.dev) coverage after the user flagged it as
> a known competitor. Purpose: confirm we're not duplicating
> any of the major Flutter MCP surfaces — Google's official one,
> Arenukvern's flutter-inspector MCP, **Maestro**, or any rising
> third-party — and make explicit where we lead, where we should
> compose, and where to step out of the way.

## TL;DR strategic posture (post-Maestro update)

> The Flutter MCP space has **three established players** plus us:
>
> - **Google** owns SDK plumbing (`pub`, `dart_fix`, `dart_format`,
>   `launch_app`, `hot_reload`, generic `run_tests`).
> - **Maestro** owns **flow authoring + execution** — natural-
>   language → YAML flow → run on device. Cross-platform
>   (Flutter + RN + native + web).
> - **Arenukvern's mcp-flutter-inspector** owns the visual /
>   semantic snapshot niche for in-app debugging.
> - **We own opinionated audit + judgment** — the 7-vertical
>   audit suite, senior-tester loop, multi-device locking, AR
>   tooling, operational fixes.
>
> **The compose-don't-compete play**: when teams adopt Maestro,
> we sit ON TOP of them. They generate + run the flow; we audit
> the flow YAML against the senior-tester discipline + ingest
> the execution report into our release-readiness composite.
> Same for Google's tools and Arenukvern's inspector.
>
> **Action items at the bottom.** Some pivots: deprecate ~14
> commodity tools long-term; add `ingest_maestro_flow` +
> `ingest_maestro_report` for v0.4.0.

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

## Maestro MCP Server (mobile.dev) — added 2026-05-23

Mobile.dev's Maestro is a flow-based cross-platform mobile test
framework (Flutter + React Native + native iOS/Android + web).
Their MCP server launched **February 2026**. **9 tools**:

| Category | Tools |
|---|---|
| **devices** | `list_devices`, `list_cloud_devices` |
| **inspection** | `inspect_screen` (view hierarchy as JSON), `take_screenshot` |
| **flow execution** | `run` (executes inline YAML, files, or directories) |
| **Maestro Cloud** | `run_on_cloud`, `get_cloud_run_status` |
| **viewer** | `open_maestro_viewer` |
| **docs** | `cheat_sheet` (Maestro syntax reference) |

**Their differentiation**: natural language → YAML flow →
execute. The `run` tool both authors AND executes, so the agent
can iterate: describe → run → fix → re-run. Cross-platform
matters — same flow runs on iOS + Android + web.

For Flutter specifically, Maestro uses the Semantics Tree
(same source we use via `dump_widget_tree`), so they're already
Flutter-aware.

**Cloud is a real moat**: `run_on_cloud` + `get_cloud_run_status`
let teams run flows on Maestro Cloud's device farm without
managing their own. We don't ship anything like that.

Sources:
- [Maestro MCP docs](https://docs.maestro.dev/get-started/maestro-mcp)
- [maestro.dev blog: Maestro MCP — an introduction](https://maestro.dev/blog/maestro-mcp-an-introduction)
- [VeryGoodVentures: Maestro MCP + Claude](https://verygood.ventures/blog/maestro-mcp-claude-mobile-ui-test-automation/)

## Side-by-side: ours (135) vs Google's (24) vs Maestro's (9)

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

### Overlap with Maestro MCP — minimal, mostly orthogonal

| Our tool | Maestro tool | Verdict |
|---|---|---|
| `list_devices` | `list_devices` | parity (commodity) |
| `take_screenshot` | `take_screenshot` | parity (commodity) |
| `dump_ui` / `dump_widget_tree` / `extract_ui_graph` | `inspect_screen` | parity-ish; different output shapes (we return structured graph; they return JSON hierarchy) |
| `run_test_plan` (YAML phase walker) | `run` (Maestro YAML) | **different syntaxes, different goals** — ours is phase-state-machine driven (PRE_FLIGHT → CLEAN → UNDER_TEST → VERDICT); theirs is flow-step driven |
| `run_patrol_test` / `run_patrol_suite` | `run` | different frameworks (Patrol vs Maestro) |
| — | `list_cloud_devices`, `run_on_cloud`, `get_cloud_run_status` | **Maestro Cloud — we have no equivalent** |
| — | `cheat_sheet` | Maestro's own docs |
| — | `open_maestro_viewer` | Maestro web viewer |

**Overlap = ~3 tools (commodity)**. Maestro doesn't ship any
audit / grading / discipline tooling. They're a test framework
+ runner; we're an opinionated reviewer.

### The Maestro composition story (the high-leverage play)

Teams that adopt Maestro write YAML flows. Those flows are
test code — and test code has quality smells (no failure-path
assertions, hardcoded English labels that break on Polish-locale
phones, vacuous assertions, etc.).

**We can audit Maestro flows with the senior-tester discipline.**

Two new tools for v0.4.0:

```python
# Audit a Maestro YAML flow against test-quality rules
audit_maestro_flow(
    flow_path="/path/to/flow.yaml",
    min_level="junior",
)
# Returns: same shape as audit_test_quality result, but
# rule names translated for Maestro YAML idioms:
#   - hardcoded_locale_string: tapOn: "Sign in" → use textBy semantic
#   - missing_failure_path: every passing flow needs a paired
#     failing assertion variant
#   - sleep_in_flow: `- wait: 3000` → use `waitForAnimationToEnd`
#   - vacuous_assertion: `- assertVisible: ".*"` is a wildcard pass

# Ingest Maestro test execution report into release_readiness
ingest_maestro_report(
    report_path="/path/to/maestro-report.xml",
)
# Returns: per-flow pass/fail/flaky + signals fed into
# audit_release_readiness composite as a test_execution
# domain (6th domain after test_quality).
```

This is **the most strategic v0.4.0 candidate** — it makes us
the audit layer for the most popular Flutter test framework's
output. Maestro brings the users; we bring the judgment.

### Where we lead — none of them ship this (~120 unique tools)

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

### 4. Compatibility note for users — write the stack-up doc
- Add `docs/the-stack.md` showing how the MCPs compose:
    - **Google's** `dart_mcp_server` (SDK plumbing)
    - **Maestro's** MCP (flow authoring + execution)
    - **Arenukvern's** mcp-flutter-inspector (visual snapshots)
    - **Ours** mcp-phone-controll (audit + judgment + lock + AR)
- All four can register in the same Claude session via
  `claude mcp add`. Each owns its layer.

### 5. v0.4.0 candidate: Maestro composition (the strategic move)
- **`audit_maestro_flow(flow_path)`** — audit a Maestro YAML
  flow with senior-tester discipline. Same rule shape as
  `audit_test_quality` but translated for YAML idioms
  (`tapOn`, `assertVisible`, `runFlow`, etc.).
- **`ingest_maestro_report(report_path)`** — feed Maestro's
  execution report into `audit_release_readiness` as a new
  `test_execution` domain. Tracks flaky-flow rates, per-flow
  pass/fail history.
- This is **the highest-leverage v0.4.0 work**: Maestro brings
  the users (they're growing fast in 2026); we bring the
  judgment layer they don't ship.

### 6. Watch list (re-check quarterly)
- **Google's MCP** — if they ship an audit equivalent →
  deprecate ours and contribute upstream
- **Maestro's MCP** — if they add a `audit_flow` or
  `lint_flow` tool → re-scope our composition story
- **Arenukvern's MCP** — if they expand into our audit space →
  evaluate alignment / cooperation
- **Any newcomer** that ships opinionated rubrics → take a
  hard look at whether to compete or contribute

Historical pattern: none of these teams have shipped
opinionated audits in their first year. The differentiation is
durable for at least the v0.4.x window.

## Bottom line (3-player landscape post-Maestro)

We have **~10% commodity overlap with Google**, **~3% overlap
with Maestro** (mostly `list_devices` + `take_screenshot` +
`inspect_screen`-shape), and **~120 tools nobody else ships**.

The strategic posture stays the same:

> **Lead on opinionated audit-grade tooling. Compose with
> Google + Maestro + Arenukvern rather than compete. Don't pivot.**

The Maestro composition (`audit_maestro_flow` +
`ingest_maestro_report`) is the v0.4.0 candidate that makes
this explicit — we become the audit layer on top of the
fastest-growing Flutter test framework, not a competitor.

Sources:
- [Dart and Flutter MCP server (docs.flutter.dev)](https://docs.flutter.dev/ai/mcp-server)
- [dart-lang/ai/pkgs/dart_mcp_server (GitHub)](https://github.com/dart-lang/ai/tree/main/pkgs/dart_mcp_server)
- [Maestro MCP docs](https://docs.maestro.dev/get-started/maestro-mcp)
- [maestro.dev blog: Maestro MCP — an introduction](https://maestro.dev/blog/maestro-mcp-an-introduction)
- [VeryGoodVentures: Maestro MCP + Claude](https://verygood.ventures/blog/maestro-mcp-claude-mobile-ui-test-automation/)
- [Voxturrlabs: MCP Servers for Dart and Flutter Developers (2026 Guide)](https://voxturrlabs.com/blog/mcp-servers-for-dart-and-flutter-developers-2026/)
- [Very Good Ventures: 7 MCP Servers Every Dart and Flutter Developer Should Know](https://verygood.ventures/blog/7-mcp-servers-every-dart-and-flutter-developer-should-know/)
