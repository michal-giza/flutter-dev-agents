# Web debug sessions — verification results (v0.7.0)

> **Status: live-verified 2026-06-08** against `flutter run -d chrome`
> on `bike_news_room/frontend` and a stock `flutter create` app
> (Flutter 3.41.7, Chrome 148).

## Results matrix

| Capability | Web (`serial="chrome"`) | Notes |
|---|---|---|
| Session boot, lock-free | ✅ | no device lock required |
| `vm_service_uri` captured | ✅ | DWDS `app.debugPort`/`wsUri` (v0.7.0 timing fix) |
| Hot reload / hot restart | ✅ | `restart_debug_session` |
| `read_debug_log` / `list` / `stop` | ✅ | full lifecycle |
| `dump_widget_tree` / `dump_render_tree` | ✅ (v0.8.0) | direct VM Service + readiness retry |
| `toggle_inspector` / `call_service_extension` | ✅ (v0.8.0) | direct VM Service |
| frame / heap timeline profiling | ❌ | DWDS lacks `getVMTimeline` (platform limit) |

## v0.8.0 — service extensions on web (direct VM Service)

The daemon's `app.callServiceExtension` proxy doesn't reach the app on
web (its debug-service connection never completes for an automated Chrome
launch — `"Waiting for connection from debug service on Chrome..."`). So
v0.8.0 routes service extensions through the **direct VM Service
WebSocket** (the `wsUri`) instead: `getVM` → isolate →
`callServiceExtension`.

**Empirically measured** (stock app): `ext.flutter.*` register ~3s after
the web app loads (t+0s: 1 extension → t+3s: 61, `debugDumpApp` works,
74,497-char tree). The web path retries on `-32601` until they register
(≤20s). Live-verified: `dump_widget_tree`, `dump_render_tree`,
`toggle_inspector`, generic `call_service_extension` all return on web.

`bike_news_room` returns "not registered after 20s" — its frontend
doesn't reach first frame without its backend, so `ext.flutter.*` never
register. The stock app working in the same run proves this is
app-state, not plumbing.

## Frame/heap timeline — not possible on web

`start_frame_profile`/`stop_frame_profile` need `getVMTimeline`, which
**DWDS doesn't implement** (`-32601 Unknown method "getVMTimeline"`).
dart2js/DWDS platform limit; mobile-only.

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
