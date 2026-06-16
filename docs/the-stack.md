# The Stack

> How `mcp-phone-controll` composes with the other Flutter MCP
> servers in your Claude session. Updated for v0.5.0.

## TL;DR

```
   ┌────────────────────────────────────────────────────────────────┐
   │  Your Claude Code / Claude Desktop / Cursor session            │
   │                                                                │
   │  ┌──────────────────────────────────────────────────────────┐  │
   │  │  Google's dart mcp-server          SDK plumbing          │  │
   │  │  (24 tools)                        — pub, dart_fix,      │  │
   │  │                                      hot_reload, lsp     │  │
   │  └──────────────────────────────────────────────────────────┘  │
   │  ┌──────────────────────────────────────────────────────────┐  │
   │  │  Maestro MCP (mobile.dev)          flow auth + execute   │  │
   │  │  (9 tools)                         — YAML flows, run,    │  │
   │  │                                      Maestro Cloud       │  │
   │  └──────────────────────────────────────────────────────────┘  │
   │  ┌──────────────────────────────────────────────────────────┐  │
   │  │  Arenukvern's mcp-flutter-inspector  visual + semantic   │  │
   │  │  (n tools)                           snapshots           │  │
   │  └──────────────────────────────────────────────────────────┘  │
   │  ┌──────────────────────────────────────────────────────────┐  │
   │  │  Chrome MCP (official, claude-in-chrome)  browser drive  │  │
   │  │                                      — DOM nav, click,   │  │
   │  │                                        eval, console     │  │
   │  └──────────────────────────────────────────────────────────┘  │
   │  ┌──────────────────────────────────────────────────────────┐  │
   │  │  mcp-phone-controll (us)           opinionated audit +   │  │
   │  │  (140 tools)                       judgment + on-device  │  │
   │  │                                    ─────────────────     │  │
   │  │   • 9-vertical audit suite (+ web shell, v0.5.0)         │  │
   │  │   • senior-tester discipline (design + audit)            │  │
   │  │   • multi-device locking + Patrol                        │  │
   │  │   • Maestro flow lint + report ingest (v0.4.0)           │  │
   │  │   • Lighthouse web-vitals ingest (v0.5.0)               │  │
   │  │   • AR/vision + operational fixes                        │  │
   │  └──────────────────────────────────────────────────────────┘  │
   └────────────────────────────────────────────────────────────────┘
```

**Each MCP owns its layer.** They don't conflict; they compose.
You add the ones you need.

## Why four MCPs and not one

Different teams ship different layers because each requires
different judgment + maintenance velocity:

| Layer | Who owns it | Why |
|---|---|---|
| **SDK plumbing** | Google | They own the Dart/Flutter SDK |
| **Flow auth + execution** | Maestro | Cross-platform mobile testing is their product |
| **Visual snapshots** | Arenukvern | Visual debugging is their niche |
| **Browser driving** (web) | a browser MCP (official) | DOM-aware drivers exist for every model class; we don't re-build one |
| **Opinionated audit + judgment** | Us | Encoding senior Flutter taste as 100+ rules requires real Flutter experience |

> **We deliberately do not ship a browser driver.** For driving a
> running Flutter **web** build, compose with a **model-agnostic
> browser MCP** — and there's one for every model class, so this works
> beyond Claude:
> - **Chrome DevTools MCP** (`npx chrome-devtools-mcp`) — CDP-based;
>   drive + performance traces (frames) + network (Firestore reads) +
>   console. Best for full before/after.
> - **Playwright MCP** (`npx @playwright/mcp`) — vision-free
>   accessibility-tree snapshots (~200–400 tokens); best for **SLMs /
>   local models** without vision.
> - **Claude-in-Chrome** (`mcp__claude-in-chrome__*`) — the built-in
>   option on Claude clients.
>
> Our web layer is **audit-grade and pure-compute**: `audit_web_app`
> grades the `web/` shell, `run_lighthouse` measures vitals,
> `ingest_lighthouse_report` parses them. We grade; the browser MCP
> drives. Re-shipping a driver (CDP/Playwright) would duplicate
> Chrome DevTools MCP — a first-party, model-agnostic, better-maintained
> tool — for no differentiation, even for SLMs. See
> `docs/web-app-rubric.md`.

Trying to put all of this in one MCP would mean either huge
surface area or shallow coverage everywhere. The composition
keeps each focused.

## Installing the stack

### Claude Code (CLI)

```bash
# Google's official Dart/Flutter MCP — now BUILT INTO the SDK (Dart 3.9+);
# the old `dart pub global run dart_mcp_server` package is superseded.
claude mcp add dart -- dart mcp-server

# Maestro MCP (mobile.dev)
claude mcp add maestro -- maestro mcp

# us
claude mcp add phone-controll -- python -m mcp_phone_controll

# (Optional) Arenukvern's flutter-inspector
# See https://github.com/Arenukvern/mcp_flutter for setup

# (Optional, for Flutter web) a model-agnostic browser MCP, routed by
# purpose — works with Claude AND local/SLM models:
#   visual / interaction (SLM-friendly, vision-free a11y tree):
claude mcp add playwright --scope user -- npx -y @playwright/mcp@latest
#   debugging / tooling (perf traces=frames, network=Firestore reads, console):
claude mcp add chrome-devtools --scope user -- npx -y chrome-devtools-mcp@latest
# (On Claude clients you can instead use the built-in "Claude in Chrome".)
```

After adding, `claude mcp list` should show all of them. They
register independently; no coordination needed.

### Claude Desktop

Open **Settings → MCP Servers** → **Add Server** for each, with
the same commands above. Or import via `.json` config files
(see each project's docs).

### Cursor / Windsurf / others

Refer to the host's MCP configuration — same commands apply.

## The end-to-end loop

What composing these MCPs actually enables a Claude session
to do:

```
1. dart_mcp.analyze_files                 ← compile errors first
       ↓
2. phone-controll.design_test_plan         ← what tests to write
       ↓ (agent writes Dart tests)
3. phone-controll.audit_test_quality       ← are they good tests?
       ↓
4. dart_mcp.run_tests                      ← run them
       ↓
5. maestro.run flow.yaml                   ← run UI flow
       ↓
6. phone-controll.ingest_maestro_report    ← parse run results
       ↓
7. phone-controll.audit_maestro_flow       ← lint the YAML
       ↓
8. phone-controll.audit_release_readiness  ← composite verdict
       ↓
   verdict == "ship" → merge
   verdict == "hold" → resolve top_actions
   verdict == "block" → STOP
```

That's the full loop. Each step belongs to the right tool.

## Per-layer guidance

### When to invoke Google's `dart mcp-server`

> Now **built into the Dart SDK** (3.9+) — run as `dart mcp-server`
> (register: `claude mcp add dart -- dart mcp-server`). The old
> `dart_mcp_server` pub package is superseded. Tool names shown below as
> `dart_mcp.*` are illustrative; the prefix follows your `claude mcp add`
> alias.

- **Type / syntax errors**: `dart_mcp.analyze_files`
- **Auto-fix lint issues**: `dart_mcp.dart_fix`
- **Format code**: `dart_mcp.dart_format`
- **Manage dependencies**: `dart_mcp.pub`
- **Search pub.dev**: `dart_mcp.pub_dev_search`
- **Hot reload during dev**: `dart_mcp.hot_reload` /
  `dart_mcp.hot_restart`
- **List devices**: `dart_mcp.list_devices` (both servers
  expose this — preference is yours)

**We deprecated our own** `dart_analyze`/`dart_fix`/
`dart_format`/`flutter_pub_get`/`flutter_pub_outdated`
in favor of Google's. They stay for backward compat but
defer to Google's tools when both are registered.

### When to invoke Maestro MCP

- **Author a flow from natural language**: `maestro.run` with
  inline YAML the agent generates
- **Execute existing flows**: `maestro.run` with a file/dir path
- **Inspect live view hierarchy**: `maestro.inspect_screen`
- **Cloud execution**: `maestro.run_on_cloud` +
  `maestro.get_cloud_run_status`
- **Reference Maestro syntax**: `maestro.cheat_sheet`

### When to invoke Chrome MCP (Flutter web)

The official browser driver — use it to *drive* a running
Flutter web build; use **our** tools to *grade* it.

- **Navigate to the running web app**: `navigate`
- **Click / type in the DOM**: `computer`, `form_input`
- **Read console / network**: `read_console_messages`,
  `read_network_requests`
- **Run JS in the page**: `javascript_tool`

We intentionally expose **none** of these — they're first-party
and well-maintained. Our seam is `audit_web_app` (static) +
`ingest_lighthouse_report` (vitals).

### When to invoke our MCP

- **Audit code architecture**: `audit_code_seniority`
- **Audit security**: `audit_security`
- **Audit i18n**: `audit_localization`
- **Audit supply chain**: `audit_dependencies`
- **Audit test code**: `audit_test_quality`
- **Audit Maestro YAML flows**: `audit_maestro_flow` (v0.4.0)
- **Parse Maestro reports**: `ingest_maestro_report` (v0.4.0)
- **Audit the web shell**: `audit_web_app` (v0.5.0) — `web/`
  index.html + manifest + headers, 12 rules
- **Run + parse Lighthouse**: `run_lighthouse` (v0.6.0) — runs the
  lighthouse CLI headless, then parses it (Core Web Vitals)
- **Parse an existing Lighthouse report**: `ingest_lighthouse_report`
  (v0.5.0) — when CI already produced the JSON
- **Composite verdict**: `audit_release_readiness`
- **Plan tests with discipline**: `design_test_plan`
- **Real-device UI driving**: `tap`, `swipe`, `take_screenshot`,
  Patrol integration, AR/vision
- **Multi-device factory loop**: `select_device`,
  `release_device`, `force_release_lock`
- **AVD operational fix**: `pause_ui_automation` +
  `resume_ui_automation`
- **Plan-walker for YAML test plans**: `run_test_plan` (our own
  phase-state-machine syntax, distinct from Maestro flows)

## Composition examples

### Example 1 — Build + audit a new feature

```
> dart_mcp.analyze_files paths=["lib/features/auth/"]
> phone-controll.design_test_plan user_story="..." feature_kind="auth"
> (agent writes tests in test/features/auth/)
> phone-controll.audit_test_quality project_path="..."
> dart_mcp.run_tests
> phone-controll.audit_release_readiness project_path="..."
```

### Example 2 — Maestro-driven E2E flow

```
> maestro.run inline_yaml="appId: com.example.app
                          ---
                          - launchApp
                          - tapOn: 'Sign in'
                          - inputText: '${USERNAME}'
                          - assertVisible: 'Welcome'"
> phone-controll.ingest_maestro_report report_path="./maestro/report.xml"
> phone-controll.audit_maestro_flow project_path="./"
> phone-controll.audit_release_readiness \
    project_path="./" \
    maestro_report_path="./maestro/report.xml"
```

### Example 3 — Multi-device parallel factory

```
> phone-controll.select_device serial="R3CYA05CHXB"     # Galaxy S25
> phone-controll.start_debug_session project_path="/path/to/app"
> dart_mcp.hot_reload
> phone-controll.tap_and_verify text="Sign in" expect_text="Welcome"
> phone-controll.read_debug_log session_id="..."
> phone-controll.stop_debug_session
> phone-controll.release_device
```

Run that flow in 4 Claude windows pointed at 4 different
devices simultaneously — our device-lock layer prevents
collisions.

### Example 4 — Flutter web release loop (v0.5.0)

We grade the shell + vitals; Chrome MCP drives the browser.

```
> phone-controll.audit_web_app project_path="./"        # static: web/ shell ready?
> dart_mcp.pub  (flutter build web)                      # build
> phone-controll.run_lighthouse url="http://localhost:8080"  # run + parse vitals (v0.6.0)
> chrome.navigate url="http://localhost:8080"            # ← official driver
> chrome.computer  (click through the running app)        # ← official driver
> phone-controll.audit_release_readiness \
    project_path="./" \
    lighthouse_report_path="./lighthouse.json"           # 8-domain verdict
```

The two `chrome.*` steps are the **only** place a browser driver
appears — and it's the official one. We never re-implement it.

## Where the layers conflict (and why they don't)

Some surface overlap exists but it's narrow and handled:

| Capability | Google | Maestro | Us |
|---|---|---|---|
| `list_devices` | ✓ | ✓ | ✓ |
| `take_screenshot` | — | ✓ | ✓ |
| `dump_ui` / view hierarchy | (via inspector) | ✓ (inspect_screen) | ✓ (multiple variants) |
| Hot reload / restart | ✓ | — | ✓ (lock-aware variant) |
| Run tests | ✓ (`run_tests`) | ✓ (`run`) | ✓ (Patrol + YAML plan-walker) |
| Source analysis | ✓ (`analyze_files`) | — | (deprecated `dart_analyze`) |

When multiple MCPs expose the same capability, the agent picks
the one whose surface fits the task. The audit suite is **only
in our MCP** — that's the durable differentiation.

## When NOT to add all four

You probably don't need all of them simultaneously. Common
shapes:

- **Solo Flutter dev, no Maestro yet**: Google + us
- **Team adopting Maestro for E2E**: Google + Maestro + us
- **Heavy visual / inspector debugging**: Add Arenukvern
- **Shipping a Flutter web app**: us (audit shell + vitals) +
  official Chrome MCP (drive the browser)
- **Factory loop (multiple devices in parallel)**: us +
  whichever others you need

The lightest-weight shape (our MCP alone) is still useful —
you get the audit suite + on-device driving + Patrol
integration. Adding Google + Maestro is the high-ROI
extension when you need it.

## See also

- `docs/flutter-mcp-comparison.md` — full 3-player landscape
  analysis, tool-by-tool diff
- `docs/web-app-rubric.md` — the web layer: `audit_web_app` 12
  rules, CanvasKit threshold, and why we compose with Chrome MCP
  instead of shipping a browser driver
- `docs/web-logged-in-flow.md` — the logged-in before/after playbook:
  Chrome MCP drives (login/scroll/import) + observes (Network/console/
  trace), phone-controll grades
- `docs/slm-setup.md` — running the stack with small / local models:
  tool-surface budgeting (`MCP_TOOL_TIER` / `?tier=`), `dart mcp-server
  --force-roots-fallback`, the commodity-tool fallback, and which MCP to
  compose per task
- `docs/senior-tester-discipline.md` — the 8 principles encoded
  by `design_test_plan` + `audit_test_quality`
- `docs/release-readiness-rubric.md` — composite verdict logic
  + weighting
- `CHANGELOG.md` — what changed in each release of our MCP
