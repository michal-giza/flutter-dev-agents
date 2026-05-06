# Walkthrough: testing `phone-controll` from VS Code on a real phone

A linear, copy-pasteable script for one Claude Code session, one Galaxy
S25 (or any USB-attached Android), and one Flutter project. By the end
you will have exercised every tool that shipped tonight — including
`tap_and_verify`, `assert_no_errors_since`, `run_quick_check`,
`patch_apply_safe`, `summarize_session`, and `write_vscode_launch_config`.

Total wall-clock: **≈ 30 minutes**, of which 15 are one-time setup.

---

## Section 1 — One-time setup (≈ 15 min)

The repo ships a single bootstrap script that handles every prerequisite.
From a fresh terminal:

```bash
cd ~/Desktop/flutter-dev-agents
./scripts/install.sh
```

What that does (verbatim from `scripts/install.sh`):

1. Verifies Homebrew, installs `android-platform-tools` if missing.
2. Installs Xcode Command Line Tools if missing (interactive).
3. Installs `uv` (Python package manager).
4. Creates `.venv` under `packages/phone-controll/`, installs
   `phone-controll` with `[dev,ar,http]` extras.
5. Runs the unit-test suite — must be green before continuing.
6. If your Galaxy is plugged in and `adb devices` sees it, runs
   `python -m uiautomator2 init` to push the device-side agent.
7. Asks `register MCP with Claude Code? (yes/no)`. Say **yes**. Under
   the hood that runs:

```bash
claude mcp add phone-controll -- \
  ~/Desktop/flutter-dev-agents/packages/phone-controll/.venv/bin/python \
  -m mcp_phone_controll
```

Verify the registration:

```bash
claude mcp list
# expect:  phone-controll  ...  ✓ connected
```

The Claude skill (`SKILL.md` + `SKILL-BASIC.md`) lives at
`~/Desktop/claude_skills/skills/mcp-phone-controll-testing/`. Claude
Code picks it up automatically — no extra wiring.

Plug the Galaxy in via USB, accept the "trust this computer" dialog,
then open VS Code in your Flutter project's root:

```bash
code ~/Desktop/<your-flutter-project>
```

Inside that VS Code window, open the Claude Code panel (`⌘+Esc`).
Everything below runs as user prompts to that Claude session.

---

## Section 2 — Sanity check (≈ 2 min)

Paste this prompt verbatim into Claude Code:

```
Use phone-controll. Run this 4-tool boot sequence and stop on the first
ok:false:

1. describe_capabilities(level="basic")
2. check_environment
3. list_devices
4. inspect_project(project_path=".")

Show me each envelope's `ok` and (if false) `error.next_action`.
```

**What you should see:**

| Step | Expected `data` shape | If `ok: false` |
|---|---|---|
| 1 | `tool_subset` length 18 | (won't fail — pure read) |
| 2 | `EnvironmentReport` with `adb`, `flutter`, `patrol` all green | follow `next_action` (e.g. `start_tunneld` for iOS) |
| 3 | list of devices; your Galaxy serial present | check USB cable; `adb devices` from terminal |
| 4 | project name, dependencies, Patrol present | `next_action: "check_pubspec"` — wrong path |

If step 1 reports fewer than 18 BASIC tools, the install didn't pick up
the Tier-A/B/C/E/F changes. Re-run `./scripts/install.sh`.

---

## Section 3 — The dev iteration loop (≈ 5 min)

Two paths produce the same artifact tree under
`~/.mcp_phone_controll/sessions/<sid>/`. Pick whichever feels right
today.

### Path A — declarative (let the plan walker drive)

Edit `examples/templates/dev_iteration.yaml`: replace the two
`REPLACE_*` placeholders with your `package_id` and a real
`integration_test/<file>.dart`. Then prompt Claude:

```
Validate then run examples/templates/dev_iteration.yaml against my
project. After it finishes, call summarize_session and paste the
3-line headline.
```

Tools called, in order: `validate_test_plan` → `run_test_plan`
(walks `OPEN_IDE` → `PRE_FLIGHT` → `CLEAN` → `DEV_SESSION_START` →
`HOT_RELOAD` → `UNDER_TEST` → `DEV_SESSION_STOP`) → `summarize_session`.

Expected envelope from `validate_test_plan`: `{"ok": true, "data": {...}}`.
If you see `next_action: "fix_plan"`, the new semantic checks caught
something — read `error.details.errors` and edit the YAML.

### Path B — interactive (Claude drives, you steer)

Paste verbatim:

```
Step by step, using phone-controll:
  1. open_project_in_ide for this project, new_window=true
  2. write_vscode_launch_config so F5 mirrors what you'll start
  3. select_device — pick the Galaxy
  4. new_session(label="walkthrough")
  5. start_debug_session(project_path=".", mode="debug")
  6. restart_debug_session(full_restart=false)   # hot reload
  7. restart_debug_session(full_restart=false)   # again
  8. read_debug_log(since_s=30, level="all")
  9. stop_debug_session
 10. release_device

Stop on the first ok:false. After step 8, narrate the latest envelope
in one line.
```

A new VS Code window will spawn (Claude *opened* it, your original
window stays). Press F5 in the new window — it now picks up the
launch.json the agent just wrote, and the agent's debug session will
keep running independently because `flutter run --machine` is one
process per session.

---

## Section 4 — Exercise the new guards (≈ 5 min)

With the debug session still running from Path B (or after restarting
it for Path A users), run each of these as a separate prompt:

### 4.1 — `tap_and_verify` replaces three tool calls

```
tap_and_verify(text="Sign in", expect_text="Welcome", timeout_s=5)
```

Expected envelope on success:
```json
{"ok": true, "data": {"text": "Welcome", "bounds": [...]}}
```

On failure: `next_action: "capture_diagnostics"` — that's your cue to
take a screenshot and read logs, **not before**.

If you see `code: "TapTextRefused"` instead, that means a Patrol
session is active and you should call `run_patrol_test` instead. Pass
`system=true` only for OS-level dialogs (permissions, etc.).

### 4.2 — `assert_no_errors_since` is your post-action checkpoint

```
assert_no_errors_since(since_s=30)
```

Expected: `{"ok": true, "data": []}`. If anything ERROR-level surfaced
in the last 30 s, you'll get `next_action: "capture_diagnostics"` plus
`details.first` containing the first 200 chars of the offending log.

### 4.3 — `run_quick_check` after every Edit

```
run_quick_check(project_path=".")
```

Expected: `{"ok": true|false, "data": {analyzer_errors, analyzer_warnings,
format_clean, git_dirty, summary}}`. Skips unit tests deliberately — use
`quality_gate` before committing for the full bar.

### 4.4 — `summarize_session` to close the loop

```
summarize_session()
```

Expected: a 3-tuple `{headline, facts, errors}`. Paste `headline` into
your standup or the PR description. The transcript at
`tests/agent/transcripts/03_dev_session_loop.json` shows the canonical
shape if you need a reference.

---

## Section 5 — Teardown + troubleshooting

Always end with:

```
release_device
```

Otherwise the lock file under `~/.mcp_phone_controll/locks/<serial>` stays
held until the MCP process exits. (`atexit` cleans up — but explicit
release is the discipline.)

Artifacts land at `~/.mcp_phone_controll/sessions/<session_id>/` —
screenshots, logs, JUnit XML if your plan asked for it. Use
`get_artifacts_dir` to print the path inline.

### Three real failure modes and their fixes

1. **iOS 26 + stale DDI** — `start_debug_session` returns a
   `DebugSessionFailure` with `next_action: "start_tunneld"`. Run
   `sudo pymobiledevice3 remote tunneld` in a separate terminal, then
   re-run. Underlying issue: iOS 26 needs a newer Developer Disk Image
   than older Xcode versions ship; tracked separately.

2. **Polish-locale phone breaks `tap_text("Settings")`** — never call
   raw `tap_text` for app UI. Two correct paths:
   - Patrol-based: `run_patrol_test` against an integration test that
     uses `patrol_finders` (locale-independent by `Key`).
   - The Tier-A composite: `tap_and_verify(text="…", expect_text="…")`
     and let the verify step do the language-aware assertion.

3. **`tap_text` refused after `prepare_for_test`** — the dispatcher
   blocks raw `tap_text` once a Patrol session is active. Envelope:
   `code: "TapTextRefused"`, `next_action: "use_patrol"`. Either switch
   to `run_patrol_test`, or — for a true OS dialog like
   `Allow camera?` — pass `system=true`:
   ```
   tap_text(text="Allow", system=true)
   ```

---

## See also

- `docs/testing-procedures.md` — the four testing tiers and the bars
  that make autonomous-agent code trustworthy.
- `docs/article/building-flutter-dev-agents.md` — the why behind the
  what, including the benchmark table.
- `tests/agent/transcripts/03_dev_session_loop.json` — the same dev
  loop as Path B, expressed as an executable replay test.
- `~/Desktop/claude_skills/skills/mcp-phone-controll-testing/SKILL.md`
  — the long-form phase-state-machine skill (auto-loaded by Claude).
