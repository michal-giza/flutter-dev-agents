# Exploratory session — AVD UIAutomator2 respawn loop

> Date: 2026-05-22 (retroactively documented same day)
> Tester: Michal Giza
> Time-box: ~45 minutes
> Status: complete

## Charter

### Mission

Characterise the AVD respawn-loop where `com.wetest.uia2.Main`
(the openatx uiautomator2 helper) keeps grabbing foreground and
re-launching BoardFlow during deep-screen capture passes.

### Areas explored

1. Process listing during a capture pass (`adb shell ps -A`)
2. Which of OUR MCP tools were keeping the helper alive
3. Kill behaviour: does `am force-stop` actually stop it?
4. `pm disable-user` as a stronger primitive
5. Whether the same APK on a real S25 has the same issue
6. The screenshot capture path (`screencap` vs uiautomator2)

### Hypothesis

The helper was being respawned by an external thing —
probably the IDE or Appium. (Hypothesis wrong: it was us.)

### Explicitly NOT testing

- Performance of the AVD itself
- Other AVD-vs-real-device differences

---

## Session log

### `10:14` — Reproducing the respawn

- **Trigger**: take three consecutive screenshots of BoardFlow's
  deeper screens (Inbox, Premium upsell, Settings) on the AVD
- **Observed**: after the first screenshot, BoardFlow loses
  foreground; screenshot 2 captures the helper's UI briefly;
  screenshot 3 captures the relaunched BoardFlow at its home
  screen (state lost)
- **Expected**: three clean captures
- **Reproducible?**: yes, every run on the AVD
- **Notes**: same APK on the Galaxy S25 → three clean captures
  every time

### `10:25` — Process pursuit

- **Trigger**: `adb shell ps -A | grep uia`
- **Observed**: `com.wetest.uia2.Main` PID 3719/3721 alive and
  cycling
- **Killed**: `adb shell am force-stop com.github.uiautomator` —
  PID gone for ~2 seconds, then back
- **Tracked the respawn source**: our own
  `UiAutomator2UiRepository`'s init does a health-ping; when the
  ping fails (because we just killed the helper), it reinstalls
  + restarts it

### `10:38` — The stronger primitive

- **Trigger**: `adb shell pm disable-user --user 0
  com.github.uiautomator`
- **Observed**: helper stays dead. Health-pings now return
  "package disabled"; our init no-ops instead of reinstalling.
- **Screenshots after disable**: three clean captures of all
  three deep screens. State preserved across.
- **Re-enable**: `adb shell pm enable com.github.uiautomator` —
  ~800ms later the helper is responsive again
- **Conclusion**: `pm disable-user` is the right primitive.
  Need a paired bracket tool.

### `10:50` — Validating on real device

- **Trigger**: same screenshot pass on the S25
- **Observed**: no respawn loop. The Samsung process governor
  backgrounds the helper aggressively; it doesn't pop forward
  between captures.
- **Conclusion**: the fix is AVD-specific. Skip on real device.

---

## Findings

### Automated cases that landed

1. **Tool: `pause_ui_automation`** (phase 8.5, blocker tier
   primitive — bracket-paired)
   - Slug: `should_disable_helper_packages_via_pm_disable_user`
   - File:
     `packages/phone-controll/src/mcp_phone_controll/domain/usecases/ui_automation_pause.py`
   - Behaviour: `pm disable-user --user 0` on both helper
     packages, records prior state for resume

2. **Tool: `resume_ui_automation`** (phase 8.5, paired)
   - Slug: `should_re_enable_helper_packages_with_settle_delay`
   - Re-enables and waits 800ms for the package manager to
     settle before next uiautomator2 init

3. **Bracket invariant test**:
   `test_pause_resume_round_trip_restores_state` — explicitly
   asserts the round-trip leaves device state identical to before

### Findings NOT becoming automated cases

- "Real Samsung devices don't have this problem" — observation,
  not testable rule (we can't test absence of a flake on a
  device class without running on every device class)
- "OUR client is what respawns the helper" — root cause but
  fixing the client itself would slow down legitimate
  uiautomator2 use. The bracket-tool was the right fix because
  it's opt-in.

### Charter health check

- Mission was sharp. The "characterise the trigger" framing was
  what made us look at process listings instead of randomly
  blaming Appium.
- 45 minutes was just right. The first 15 minutes were
  reproducing the bug; the middle 15 were finding the cause;
  the last 15 were testing `pm disable-user` and rollback.
- Highest-value area: the cross-check on the S25. Confirmed the
  fix shouldn't apply universally — only on AVDs. That shape
  drives the bracket-pairing design.

---

## Follow-up

- [x] Phase 8.5 `pause_ui_automation` + `resume_ui_automation`
  shipped (PR #29)
- [x] `docs/test-quality-rubric.md` updated to flag
  uiautomator-fight as a known AVD failure mode
- [x] `ui_automation_pause.py` docstring opens with this story
  verbatim so future readers know WHY the tool exists
