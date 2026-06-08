# Logged-in web before/after — Chrome MCP × phone-controll

> The automated, **logged-in** before/after loop for a Flutter **web**
> app (login → action → measure), composing the official **Chrome MCP**
> (drive + observe) with phone-controll (grade). We don't ship a browser
> driver — this is the seam where the two compose. See
> `docs/the-stack.md` for why.

## Who owns what

| Layer | Tool | Does |
|---|---|---|
| Drive the DOM | `mcp__claude-in-chrome__*` | navigate, login, click, scroll, import |
| Observe network | `mcp__claude-in-chrome__read_network_requests` | Firestore reads/latency/payload per action |
| Observe console | `mcp__claude-in-chrome__read_console_messages` | runtime errors (RenderFlex, exceptions) |
| Capture frames | Chrome trace via Chrome MCP / DevTools Performance | jank during scroll/virtualization |
| Grade static shell | `phone-controll.audit_web_app` | index.html / manifest / headers |
| Grade load vitals | `phone-controll.run_lighthouse` | LCP/CLS/TBT, CanvasKit-aware |

phone-controll grades; Chrome MCP drives and observes. Neither
reimplements the other.

## Prerequisite — connect Claude-in-Chrome (one time)

The recurring blocker. In your client (Claude Desktop / Code), enable the
**"Claude in Chrome"** connector/extension, open the app's tab, then the
`mcp__claude-in-chrome__*` tools become available (`list_connected_browsers`
should show the tab). Until then, `switch_browser` returns "none" and none
of the web-drive steps below work.

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

### 1. Log in — Chrome MCP
```
chrome.navigate(url="http://localhost:8080")
chrome.find("email field")  →  chrome.form_input(<EMAIL_PLACEHOLDER>)
chrome.find("password field") → chrome.form_input(<PASSWORD_PLACEHOLDER>)
chrome.computer(click "Sign in")
chrome.read_console_messages()                   # catch login-time errors
```

### 2. Reach the screen under test — Chrome MCP
```
chrome.find("Urządzenia")  →  chrome.computer(click)
chrome.get_page_text()                           # confirm you're there
```

### 3. "Before" snapshot — Chrome MCP observes
```
chrome.read_network_requests()                   # baseline request set
# (start a performance trace if you'll measure frames — DevTools
#  Performance record, or Chrome MCP's CDP tracing)
```

### 4. Perform the action (import / virtualization scroll) — Chrome MCP
```
chrome.computer(click "Import")        # or scroll the virtualized list
# … let it complete …
```

### 5. "After" — Chrome MCP observes
```
chrome.read_network_requests()                   # delta vs step 3
chrome.read_console_messages()                   # errors during the action
# stop + export the performance trace
```

### 6. Grade

- **Firestore cost/latency**: diff the `read_network_requests` sets from
  steps 3 and 5; filter `firestore.googleapis.com` — count reads/writes,
  sum latency + payload. (This is the per-action telemetry your report
  asked for — it comes straight from the Network panel.)
- **Frames/jank**: read the trace's long tasks (>50ms) and dropped
  frames during the scroll/import window.
- **Load vitals**: `run_lighthouse` (step 0) for LCP/CLS/TBT.
- **Correctness**: `run_unit_tests(platform="chrome")` /
  `run_widget_test(platform="chrome")` for the logic behind the action.

## What's NOT achievable on web (platform limits)

- **VM-timeline frame profiling** (`start_frame_profile`) — DWDS has no
  `getVMTimeline`. Use the Chrome trace (step 3–5) instead; that's the
  browser-native frame source.
- **Daemon-proxied debugging** — use the v0.8.0 web debug session
  (`start_debug_session(serial="chrome")` → `dump_widget_tree` /
  `toggle_inspector`) for inspector data via the direct VM Service.

## Want it graded, not eyeballed?

The Network diff (step 6) and trace analysis are manual reads of Chrome
MCP output today. If you want phone-controll to turn those raw exports
into audit-grade verdicts, two in-lane tools are ready to build on
request (pure-compute, "you capture, we grade"):

- `ingest_har` — Firestore reads/writes + latency + payload per action
  from a Network-panel HAR export.
- `ingest_chrome_trace` — long tasks / main-thread blocking / dropped
  frames from a DevTools performance trace.

Both follow the `ingest_maestro_report` / `ingest_lighthouse_report`
posture. Say the word.
