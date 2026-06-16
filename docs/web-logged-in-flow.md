# Logged-in web before/after — browser MCP × phone-controll

> The automated, **logged-in** before/after loop for a Flutter **web**
> app (login → action → measure), composing a **model-agnostic browser
> MCP** (drive + observe) with phone-controll (grade). We don't ship a
> browser driver — this is the seam where the two compose. Works with
> Claude AND local/SLM models (see the browser-MCP table below). See
> `docs/the-stack.md` for why.

## Who owns what

| Layer | Tool | Does |
|---|---|---|
| Drive the DOM | a **browser MCP** (see below) | navigate, login, click, scroll, import |
| Observe network | browser MCP's network tool | Firestore reads/latency/payload per action |
| Observe console | browser MCP's console tool | runtime errors (RenderFlex, exceptions) |
| Capture frames | browser MCP's performance trace | jank during scroll/virtualization |
| Grade static shell | `phone-controll.audit_web_app` | index.html / manifest / headers |
| Grade load vitals | `phone-controll.run_lighthouse` | LCP/CLS/TBT, CanvasKit-aware |

phone-controll grades; the browser MCP drives and observes. Neither
reimplements the other.

## Prerequisite — connect a browser MCP (model-agnostic)

Pick the browser-driving MCP that fits your model and add it **alongside**
phone-controll. All are model-agnostic (any MCP client) — this is the
fix for the SLM gap: Claude-in-Chrome is Claude-only, but these work with
local/open-source models too.

| Browser MCP | Best for | Notes |
|---|---|---|
| **Chrome DevTools MCP** (`npx chrome-devtools-mcp`) | full before/after | CDP-based; Input/Navigation + **Performance traces** (frames) + **Network** (Firestore reads) + console + `lighthouse_audit`. Uses system Chrome; connects to a running Chrome via `--browser-url`. |
| **Playwright MCP** (`npx @playwright/mcp`) | **SLMs / local models** | vision-free **accessibility-tree** snapshots (~200–400 tokens, deterministic refs) — drivable by small models without vision. Network + console + CDP-endpoint connect. |
| **Claude-in-Chrome** | Claude clients | the built-in option when you're on Claude; same role. |

> **We deliberately don't ship a web driver in phone-controll** — these
> are official, maintained, model-agnostic browser MCPs. Building our own
> (CDP/Playwright) would reinvent Chrome DevTools MCP. We compose; we
> grade. Tool names below use a `browser.*` shorthand — substitute your
> chosen server's actual tool names.

Until a browser MCP is connected (its `list_*`/`tabs` tool shows your
tab), the web-drive steps below can't run.

## Credentials — never commit them

The login below uses a placeholder. **Do not** put real credentials
(`demo@…`, passwords, tokens) in any committed file, plan, or script.
Provide them at run time (paste into the session, or an env var the
client reads). This repo's security rules forbid committing secrets.

## The loop

### 0. Static + load baseline (no login needed) — phone-controll
```
audit_web_app(project_path="…")                  # shell readiness
run_lighthouse(url="http://localhost:8080")      # load vitals (LCP/CLS/TBT)
```

### 1. Log in — browser MCP
```
browser.navigate(url="http://localhost:8080")
browser.find("email field")  →  browser.form_input(<EMAIL_PLACEHOLDER>)
browser.find("password field") → browser.form_input(<PASSWORD_PLACEHOLDER>)
browser.computer(click "Sign in")
browser.read_console_messages()                   # catch login-time errors
```

### 2. Reach the screen under test — browser MCP
```
browser.find("Urządzenia")  →  browser.computer(click)
browser.get_page_text()                           # confirm you're there
```

### 3. "Before" snapshot — browser MCP observes
```
browser.read_network_requests()                   # baseline request set
# (start a performance trace if you'll measure frames — DevTools
#  Performance record, or the browser MCP's tracing)
```

### 4. Perform the action (import / virtualization scroll) — browser MCP
```
browser.computer(click "Import")        # or scroll the virtualized list
# … let it complete …
```

### 5. "After" — browser MCP observes
```
browser.read_network_requests()                   # delta vs step 3
browser.read_console_messages()                   # errors during the action
# stop + export the performance trace
```

### 6. Grade

- **Firestore cost/latency**: export the Network panel as a **HAR** and
  run **`ingest_har`** (v0.10.0) — it grades per-host reads/writes,
  p50/p95 latency, payload, and errors with your backend host
  highlighted (`backend_host="firestore.googleapis.com"` or your REST
  API). Or read it ad-hoc by diffing the `read_network_requests` sets
  from steps 3 and 5.
- **Frames/jank**: read the trace's long tasks (>50ms) and dropped
  frames during the scroll/import window.
- **Load vitals**: `run_lighthouse` (step 0) for LCP/CLS/TBT.
- **Correctness**: `run_unit_tests(platform="chrome")` /
  `run_widget_test(platform="chrome")` for the logic behind the action.

## Driving caveat — CanvasKit scroll (field-verified 2026-06-08)

On a **CanvasKit** Flutter web build, the virtualized list does **not**
respond to synthetic mouse-wheel **or** keyboard (Page Down) input from
Claude-in-Chrome — the Flutter `ScrollView` doesn't consume those DOM
events. Verified live on bike_news_room: 3 wheel scrolls + 5 Page Downs
produced byte-identical frames and **no pagination fetch**.

Route scroll / virtualization driving to:
- **Chrome DevTools MCP** — CDP `Input.dispatchMouseEvent` wheel events
  reach the canvas; pairs with its performance trace for the frame data.
- **Playwright MCP** — `mouse.wheel` / programmatic scroll.

Onboarding clicks, form fills, and navigation work fine via any of them
(verified). It's specifically wheel/keyboard *scroll* over the canvas
that needs the CDP/Playwright path.

## What's NOT achievable on web (platform limits)

- **VM-timeline frame profiling** (`start_frame_profile`) — DWDS has no
  `getVMTimeline`. Use the Chrome trace (step 3–5) instead; that's the
  browser-native frame source.
- **Daemon-proxied debugging** — use the v0.8.0 web debug session
  (`start_debug_session(serial="chrome")` → `dump_widget_tree` /
  `toggle_inspector`) for inspector data via the direct VM Service.

## Want it graded, not eyeballed?

phone-controll turns the raw browser-MCP exports into audit-grade
verdicts (pure-compute, "you capture, we grade"):

- **`ingest_har`** (v0.10.0) — per-host reads/writes + p50/p95 latency +
  payload + errors from a Network-panel **HAR** export, backend host
  highlighted.
- **`ingest_frame_timeline`** (v0.10.x) — % janky frames / worst frame /
  build-vs-raster from a captured frame timeline (mobile VM Timeline or
  a Chrome DevTools web trace).

Both follow the `ingest_maestro_report` / `ingest_lighthouse_report`
posture.
