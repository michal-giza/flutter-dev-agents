# Scenario 2 — Reproduce a Polish-locale bug

**You have**: a Galaxy S25 in Polish locale (`pl-PL`), a Flutter
app that requests Location permission, a bug report that says
"the 'Allow only this time' button doesn't work in Polish."

**You want**: reproduce the bug deterministically, capture the
failure state, file a structured bug report.

## What makes this scenario interesting

Polish localization uses U+00A0 (NO-BREAK SPACE) between words for
typography. So the visible button text "Podczas używania aplikacji"
is byte-encoded as `Podczas używania aplikacji` in the
UI tree. Without the MCP's NBSP-fold (`tap_text` already handles
this since v0.2.1), the tap fails silently — agent and human alike
report "button doesn't work."

This scenario walks through the right way to reproduce it AND the
right way to file the bug.

## Prompt

```
Using phone-controll, reproduce the Polish-locale permission
bug:

1. Confirm we're on a Polish-locale device — run
   check_environment and read me back the device locale.
2. select_device the Polish Galaxy S25.
3. clear_app_data + launch_app for com.example.myapp.
4. Wait for the location permission dialog (system dialog, give
   it 10 seconds).
5. tap_text "Podczas używania aplikacji" with system=true and
   exact=true. This is the OS dialog button.
6. take_screenshot labeled "after-permission-grant".
7. assert_no_errors_since 10 — should be clean.
8. dump_ui — I want to see the full tree so I can verify the
   permission state propagated.
9. release_device.

If step 5 returns ok=false, tell me exactly what next_action it
surfaced and dump the UI before the tap so I can see what label
the OS actually showed.
```

## Expected — happy path (post v0.2.1)

```
check_environment    0.50s  locale=pl_PL, all green
select_device        0.12s  R3CYA05CHXB locked
clear_app_data       1.40s  ok=true
launch_app           1.20s  ok=true
wait_for_element     2.10s  dialog appeared (text contains "Podczas")
tap_text             0.30s  ok=true (used loose-match path; NBSP-fold)
take_screenshot      0.42s  /sessions/<sid>/screenshot-after-permission-grant-001.png
assert_no_errors_since 0.30s ok=true
dump_ui              0.55s  <node ... visible elements ...>
release_device       0.05s  ok=true
```

## Expected — failure mode you might still hit

If the OS version changed the dialog wording — e.g., upgrading
Android 14 → 15 changed "Podczas używania aplikacji" to
"Tylko podczas używania" — the tap_text returns:

```json
{
  "ok": false,
  "error": {
    "code": "UiElementNotFoundFailure",
    "message": "Text not found via selector or UI scan: 'Podczas używania aplikacji'",
    "next_action": "check_text_or_use_dump_ui",
    "details": {
      "requested": "Podczas używania aplikacji",
      "normalised": "Podczas używania aplikacji",
      "exact": true
    }
  }
}
```

The follow-up to **the agent** is in `next_action`:
`check_text_or_use_dump_ui` — call `dump_ui` to see the real
label, then re-issue `tap_text` with the corrected string.

## What to file as a bug report

Include all 9 of these artifacts (the MCP gives you 7 for free):

1. **MCP version + git_sha** from `mcp_ping`.
2. **Device locale + OS version** from `check_environment`.
3. **Screenshot of the failing state** from `take_screenshot`.
4. **UI tree at the moment of failure** from `dump_ui`.
5. **Last 30 seconds of logs** from `read_logs(since_s=30)`.
6. **The exact agent prompt** that reproduces the bug.
7. **The exact `next_action` surfaced by the failing tool.**
8. **What you expected to happen** (you provide).
9. **What actually happened, frame-by-frame** (you provide).

Bug reports with 1–7 are immediately actionable. Bug reports with
just "tap didn't work" are not.

## Bonus — why this works after the v0.2.1 fix

`tap_text`'s fallback path (the XML-dump scan) normalizes both
the agent's input AND the dump-XML text via `_normalise_loose`:

- NFC normalization (collapses combining-accents → precomposed).
- Fold NBSP (U+00A0), NNBSP (U+202F), thin space (U+2009) → ASCII space.
- Strip ZWSP (U+200B), word-joiner (U+2060), BOM (U+FEFF).
- Collapse whitespace runs to single space.
- Case-fold in substring mode (preserves casing in `exact=True`).

So `tap_text(text="Podczas używania aplikacji", system=True,
exact=True)` works whether the device shows ASCII spaces, NBSP, or
NBSP + an invisible BOM from a translation tool. See
`docs/operational-gotchas.md#3` for the full disambiguation
playbook.
