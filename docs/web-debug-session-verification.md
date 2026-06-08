# Web debug sessions — verification results (v0.7.0)

> **Status: live-verified 2026-06-08** against `flutter run -d chrome`
> on `bike_news_room/frontend` and a stock `flutter create` app
> (Flutter 3.41.7, Chrome 148).

## Results matrix

| Capability | Web (`serial="chrome"`) | Notes |
|---|---|---|
| Session boot, lock-free | ✅ | no device lock required |
| `vm_service_uri` captured | ✅ | DWDS `app.debugPort`/`wsUri`, after the timing fix |
| Hot reload / hot restart | ✅ | `restart_debug_session` |
| `read_debug_log` / `list` / `stop` | ✅ | full lifecycle |
| `dump_widget_tree` / inspector | ❌ | daemon service extension — see limitation |
| frame / heap profiling | ❌ | same daemon path |

## The limitation (why service extensions fail on web)

`dump_widget_tree`, `toggle_inspector`, frame/heap profilers call the
Flutter daemon's `app.callServiceExtension`. On web that requires the
daemon's **debug-service connection** to the running app, which never
completed for our automated Chrome launch — the daemon log stayed on
`"Waiting for connection from debug service on Chrome..."` and the call
returned `method not available: ext.flutter.debugDumpApp` even on a
stock app that renders immediately. So it's **not app-specific** and not
a timing-of-first-frame issue.

The robust fix is to talk to the **direct VM Service WebSocket** (the
`wsUri` we now capture via DWDS) using `vm_service_client.py`, instead
of the daemon proxy. That's the planned **v0.8.0 follow-up**.

## Original verification recipe (kept for re-runs)

## Why this needs a human-in-the-loop

Everything else in the stack is faked in CI. But the DWDS daemon for web
*could* differ from a phone's in one place: which event carries the VM
Service URI (`app.started` vs `app.debugPort`, field `wsUri` vs `uri`).
The parser already handles all four, but only a live run proves it.

## Install the branch

```bash
# from a local checkout of the branch:
git fetch origin feat/v070-web-debug-session
git checkout feat/v070-web-debug-session
uv sync   # or: pip install -e packages/phone-controll

# then point your MCP client at THIS checkout's venv, or:
pip install "git+https://github.com/michal-giza/flutter-dev-agents@feat/v070-web-debug-session#subdirectory=packages/phone-controll"
```

Restart the MCP after installing.

## The verification sequence (in your Claude session)

Run against `flow_meter` (or any Flutter web app):

```
1. start_debug_session(project_path="…/flow_meter", serial="chrome")
   ✅ EXPECT ok:true, data.vm_service_uri is a ws:// URL, data.device_serial == "chrome".
   ❌ If next_action == "select_device_first" → the lock skip didn't apply (BUG).
   ❌ If it times out on app.started → the daemon didn't signal ready (report the raw log).

2. dump_widget_tree()
   ✅ EXPECT the widget tree JSON (proves service extensions work over DWDS).

3. start_frame_profile()  →  (interact)  →  stop_frame_profile()
   ✅ EXPECT frame timings (use mode="profile" in step 1 for honest numbers:
      start_debug_session(..., serial="chrome", mode="profile")).

4. take_heap_snapshot()
   ✅ EXPECT a heap summary (proves VM Service memory APIs work on web).

5. read_debug_log(since_s=60)
   ✅ EXPECT recent app/daemon log lines.

6. stop_debug_session()
   ✅ EXPECT ok:true.
```

## What "pass" means

Steps 1, 2, and 6 are the load-bearing ones:
- **1** proves the lock is skipped and the session boots with a VM Service URI.
- **2** proves service extensions dispatch over the web daemon.
- **6** proves clean teardown.

If 3/4 behave differently on web (some VM Service APIs are renderer- or
DWDS-dependent), note exactly which call returned what — that's a
follow-up, not a blocker for the core "web session attaches" claim.

## If it works

Reply "verified" and the release ships:
`gh pr merge --rebase` → tag `v0.7.0` → PyPI → GitHub Release.

## If it doesn't

Paste the failing tool's full envelope (esp. the raw daemon log from
`read_debug_log` or the `start_debug_session` error details). The most
likely fix is a one-line tweak to `vm_service_uri_from_started` /
`app_id_from_started` in
`data/parsers/flutter_machine_event_parser.py` for a web-specific field
name — cheap to patch once we see the real event.
