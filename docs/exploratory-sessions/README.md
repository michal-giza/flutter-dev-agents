# Exploratory sessions

> Charter-format notes from real exploratory testing sessions
> that drove design changes in this MCP. See
> `docs/senior-tester-discipline.md` principle 6 for the why.

Each session follows `TEMPLATE.md`. File name format:
`YYYY-MM-DD-<topic-slug>.md` — chronological sort.

## Sessions

| Date | Topic | What landed |
|---|---|---|
| 2026-05-21 | [Polish-locale tap_text](2026-05-21-polish-locale-tap-text.md) | `audit_localization` rule `hardcoded_user_text` (phase 9); `audit_test_quality` rule `hardcoded_locale_string` (phase 12) |
| 2026-05-22 | [AVD UIAutomator2 respawn loop](2026-05-22-avd-uiautomator-respawn.md) | `pause_ui_automation` + `resume_ui_automation` paired tools (phase 8.5) |

## When to write one

- Any time real-device testing surfaces something the test
  suite didn't catch
- Before reaching for a new audit rule, ask: did this come from
  a charter, or is it speculation?
- After a flaky-test investigation that yields a real fix
- After a "this works on X but not Y" debugging session

## When NOT to write one

- Trivial fixes ("forgot to await") — these go straight to a PR
- Speculative ideas — write a draft note in
  `private/scratch/`, not here. This directory is for sessions
  that already happened.

## How to use the template

```bash
cp docs/exploratory-sessions/TEMPLATE.md \
   docs/exploratory-sessions/$(date +%Y-%m-%d)-<topic>.md
$EDITOR docs/exploratory-sessions/$(date +%Y-%m-%d)-<topic>.md
```

Fill in the charter section **before** starting. Fill in the
session log **during**. Fill in the findings **after** the
time-box ends. Resist the urge to retroactively edit the log
to make it look tidier — the messy thinking process is the
value.
