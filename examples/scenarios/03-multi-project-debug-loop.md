# Scenario 3 — Multi-project debug loop (15 minutes)

**You have**: 2–4 Flutter projects open, 2–4 devices available,
and a complex bug that spans projects (e.g., a shared package's
breaking change broke 3 apps).

**You want**: drive all of them in parallel from separate Claude
sessions, with per-project debug sessions, hot reload, and
cross-session visibility.

## Why this is the headline feature

Most "AI for mobile testing" tools assume one device, one
session, one app. The MCP's filesystem-based device locks let N
concurrent agents drive N phones safely. This scenario walks
through a real day-in-the-life.

## The setup

Three Claude Code windows in three projects:

```
Window 1 (in ~/Desktop/checkaiapp)   — Galaxy S25 R3CYA05CHXB
Window 2 (in ~/Desktop/another_app)  — emulator-5554 (Pixel 8)
Window 3 (in ~/Desktop/third_app)    — iPhone 15 (UDID 00008120-...)
Window 4 — orchestrator (no project, watches everyone)
```

Each Claude session uses `MCP_TOOL_TIER=intermediate` because
debug-session tools (start_debug_session, restart_debug_session,
read_debug_log) live there.

## Window 1 prompt

```
Using phone-controll, work in /Users/me/Desktop/checkaiapp:

1. select_device serial R3CYA05CHXB.
2. open_project_in_ide for this project in a new VS Code window.
3. start_debug_session with mode=debug.
4. Wait for the app to render (wait_for_element with text
   "Sign in", timeout 20s).
5. read_debug_log since_s=30 — I want to see startup logs.

DO NOT release the device. DO NOT stop the debug session. Leave
it running so I can iterate. When you're ready, prompt me for
the next action.
```

## Window 2 prompt — same shape, different device

```
Using phone-controll, work in /Users/me/Desktop/another_app:

1. select_device serial emulator-5554.
2. open_project_in_ide for this project.
3. start_debug_session.
4. Wait for the app, read startup logs.

Stay open.
```

## Window 3 prompt — iOS path

```
Using phone-controll, work in /Users/me/Desktop/third_app:

1. check_environment first — confirm tunneld is running and
   pymobiledevice3 is on PATH. If not, tell me the exact fix
   command.
2. select_device UDID 00008120-001A42542E30201E.
3. setup_webdriveragent for this UDID (it should be cached so
   this should skip with skipped_existing=true).
4. open_project_in_ide.
5. start_debug_session with mode=debug.
6. Wait for the app, read startup logs.

Stay open.
```

## Window 4 — orchestrator

```
Using phone-controll, run an orchestration check:

1. list_locks — show me every device lock across this machine.
2. list_debug_sessions — every active flutter run --machine.
3. list_ide_windows — every VS Code window the MCP spawned.

Format the output as a single table.
```

Expected output:

```
Session          | Device       | Project        | IDE win | Debug | Lock age
---------------- | ------------ | -------------- | ------- | ----- | --------
window-1-…       | R3CYA05CHXB  | checkaiapp     | win-A   | dbg-A | 2m 14s
window-2-…       | emulator-5554| another_app    | win-B   | dbg-B | 1m 50s
window-3-…       | 00008120-...| third_app      | win-C   | dbg-C | 1m 32s
```

Now you can see what everyone is doing without leaving Window 4.

## The iteration loop (in any of windows 1–3)

```
restart_debug_session — hot reload after I just saved a fix.
Then read_debug_log since_s=5 — show me any new errors.
If clean, take_screenshot labeled "after-fix-attempt-1".
```

Each iteration is ~3 seconds. You can do this 20 times in 15
minutes across 3 projects.

## Cleanup

```
Using phone-controll, end my multi-project session:

1. stop_debug_session for this window's dbg-* id.
2. release_device.
3. close_ide_window for the VS Code window we opened.
4. summarize_session — give me a final report of every tool
   I called today, sorted by frequency.
```

Run this in each window. Window 4's orchestrator should then show
empty lists.

## What the data captures

After this scenario completes, you have:

- 3 session dirs under `~/.mcp_phone_controll/sessions/` —
  one per Claude window.
- Each session dir contains: screenshots taken, debug-log
  snapshots, the session trace SQLite (every tool call with
  timestamp + duration + envelope).
- The orchestrator's view shows the cross-session intersection.

For an end-of-week summary across multiple multi-project days,
the case-study journal in `docs/internal/case-study-journal/`
captures the qualitative side; the session SQLite captures the
quantitative side.

## What goes wrong + how to recover

| Symptom | Cause | Fix |
|---|---|---|
| `select_device DeviceBusyFailure` | Window 1's previous session crashed without releasing | Window 4: `list_locks` then `force_release_lock` for the stale one |
| Window 3 iPhone refuses tap | WDA wasn't running — setup ran but `xcodebuild test-without-building` didn't start | Re-run `setup_webdriveragent`, or for sim: `start_wda_on_simulator` |
| Window 2 debug log empty | `flutter run --machine` died silently | `list_debug_sessions` to confirm; restart via `start_debug_session` |
| Hot-reload times out | App crashed and the daemon doesn't know | `stop_debug_session` then `start_debug_session` from scratch |

## Make it repeatable

Save the four prompts as a markdown file you re-open every
morning. Once the team grows past you, this becomes the onboarding
exercise for new contributors — "spend 30 minutes running scenario
3, then you've seen everything important."
