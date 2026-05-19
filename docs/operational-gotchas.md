# Operational gotchas

Tight reference for the small handful of "I burned an hour on this"
issues that surface during real testing sessions. Each entry is a
single concrete fact plus the minimal fix.

Read this before your first overnight automated run. The agent does
**not** rediscover any of these from the runbook or the schema; they
have to be told.

## 1. iOS UI driving requires WebDriverAgent

`tap`, `swipe`, `type_text`, `press_key`, `dump_ui` and every
selector-based UI assertion on a real iPhone go through WDA. Without
it, those tools return `WdaUnreachable(next_action="…")` and **the
app on screen will not be touched**.

```bash
# Canonical location after `setup_webdriveragent`:
~/.mcp_phone_controll/WebDriverAgent/

# Default port WDA listens on (USB-tunneled for physical, host for sim):
127.0.0.1:8100
```

For a physical iPhone the test runner must be **kept running**
(`xcodebuild test-without-building` keeps WDA alive for the lifetime
of the xcodebuild process). For a simulator, `start_wda_on_simulator`
spawns it detached.

**Symptom if missing**: every `tap` returns `next_action:
"setup_webdriveragent"` or `next_action: "start_wda_on_simulator"`.
The fix is one tool call — but the agent often loops without it
because `take_screenshot` and `read_logs` keep working (those don't
need WDA), so the agent thinks the device is healthy.

**Discipline**: on iOS, run `mcp_ping` + `dump_ui` at the start of
every session. If `dump_ui` returns a tree, WDA is alive. If it
returns `WdaUnreachable`, run `setup_webdriveragent` or
`start_wda_on_simulator` *before* touching the rest of the suite.

## 2. Coordinates are LOGICAL device points, not screenshot pixels

This one bit overnight bots three sessions in a row.

When `take_screenshot` returns a PNG, the file dimensions are the
screenshot pixels (often capped at 1600 px long-edge by our pipeline)
which are **not** what `tap(x, y)` expects.

`tap`, `swipe`, and every coordinate-taking tool use the device's
**logical point** coordinate system — what Flutter/SwiftUI/Compose
calls the "logical" or "DP" coordinate space.

| Device | Logical points | Pixels (native) | Cap-pipeline PNG |
|---|---|---|---|
| iPhone 17 Pro | 402 × 874 | 1290 × 2796 | 1600 × 738 (capped) |
| iPhone 15 | 393 × 852 | 1179 × 2556 | 1600 × 738 (capped) |
| Galaxy S25 | 384 × 854 | 1080 × 2400 | 1600 × 711 (capped) |
| Pixel 8 emulator | 412 × 915 | 1080 × 2400 | 1600 × 711 (capped) |

**The trap**: agent looks at the 1600 × 738 PNG, sees a button at
"around pixel (640, 600)" in the image, calls `tap(640, 600)`. The
device's logical space is only 402 wide — so 640 lands somewhere off
the right edge of the screen. **Nothing happens, no error.**

**Discipline**:

- Prefer `tap_text(text="Sign in")` or `tap_text(text="Allow",
  system=True)`. These resolve targets in logical-space directly.
- When you *must* tap by coordinates (e.g. canvas / map / image
  hit-area), call `dump_ui` first, find the element, and tap the
  *center of its `bounds` rectangle* — those bounds are already in
  logical points.
- The `tap_and_verify` tool is the safest pattern: it taps, captures
  a screenshot, and asserts a follow-up text appeared. If the tap
  missed, you get a structured failure instead of silent drift.

## 3. `tap_text` matches multiple labels — disambiguate or use coords

`tap_text("Settings")` taps the first node whose `text` or
`content-desc` contains `"Settings"` — but real apps frequently have
**multiple** matching nodes (a hamburger label and a settings
button; a section header and a row item with the same word).

```python
# Risky on a settings-heavy screen:
tap_text(text="Settings")

# Better — exact match removes substring collisions:
tap_text(text="Settings", exact=True)

# Best when text is shared across nodes — use the accessibility id
# or resource-id via find_element + tap by bounds.center:
elem = find_element(text="Settings", class_name="Button")
tap(x=elem.bounds.center.x, y=elem.bounds.center.y)
```

**Discipline**:

- Default to `exact=True` for known-canonical strings (button
  labels, dialog options).
- For OS dialogs (permission prompts, system sheets), pass
  `system=True` — that path uses Springboard's accessibility tree on
  iOS / `com.android.permissioncontroller` on Android, and skips the
  current app's UI tree (which would otherwise add false matches).
- If two real matches exist in the same scene, fall back to
  `find_element(...)` + `tap(x, y)` against the deliberate element's
  bounds.

## 4. Localhost differs between iOS sim and Android emulator

If your app under test talks to a local development backend
(e.g. `python -m http.server 8000` on your laptop, a local Firebase
emulator, a Postgres on `localhost`), the address inside the
virtual device is **not** `localhost` for both platforms.

| Platform | What "your laptop's localhost" looks like from inside |
|---|---|
| iOS Simulator (macOS) | `127.0.0.1` (sim shares the host loopback) |
| Android Emulator | `10.0.2.2` (the emulator's host-loopback alias) |
| Physical iPhone (USB) | `127.0.0.1` if you set up `usbmuxd` port forwarding; otherwise the laptop's LAN IP |
| Physical Android (USB) | `localhost` with `adb reverse tcp:N tcp:N`; otherwise the laptop's LAN IP |

**Configuration pattern that works on both**:

```dart
// Flutter — pass at build time via --dart-define so the same
// binary runs on both sim and emulator without recompiling.
const backendBase = String.fromEnvironment(
  'BACKEND_BASE',
  defaultValue: 'http://127.0.0.1:8000',
);
```

```bash
# iOS sim build:
flutter run --dart-define=BACKEND_BASE=http://127.0.0.1:8000

# Android emulator build:
flutter run --dart-define=BACKEND_BASE=http://10.0.2.2:8000

# Physical Android with adb-reverse:
adb reverse tcp:8000 tcp:8000
flutter run --dart-define=BACKEND_BASE=http://127.0.0.1:8000
```

**Symptom if wrong**: app launches, connect to "localhost", silent
network failure or hang. Crashlytics fills with `SocketException` /
`ConnectionRefusedError`. `read_logs` shows the request fired but
nothing came back.

**Discipline**: include this mapping in any plan-template that
talks to a local backend. The plan-walker preflight should set
`BACKEND_BASE` via env per device class.

## See also

- `docs/runbook.md` — operational failures (the *what just broke* doc).
- `docs/ios_setup.md` — the prerequisite chain for iOS device control.
- `docs/walkthrough-vscode-test.md` — a clean end-to-end happy-path script.
- `INTEGRATIONS.md` — how to use this MCP from agents that have
  their own quirks (Claude Desktop, Claude Code, Cursor, n8n, raw
  curl).
