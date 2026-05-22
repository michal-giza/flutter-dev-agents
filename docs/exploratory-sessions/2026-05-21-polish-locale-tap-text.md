# Exploratory session — Polish-locale tap_text behaviour

> Date: 2026-05-21 (retroactively documented 2026-05-22)
> Tester: Michal Giza
> Time-box: ~30 minutes (informal — formalised after the fact)
> Status: complete

## Charter

### Mission

Confirm that `tap_text("Settings")` works on a Samsung Galaxy S25
running with system locale set to Polish (pl-PL), where the
visible system Settings label reads "Ustawienia".

### Areas explored

1. Stock Android Settings app (system UI text)
2. Our test fixtures using `tap_text` for in-app navigation
3. The dev_session plan walker stepping through a YAML plan
   that referenced "Settings" in `tap_text:` calls

### Hypothesis

The tool would gracefully fall back from exact-text match to
fuzzy / id-based selection. (Hypothesis turned out wrong.)

---

## Session log

### Early — Settings app target

- **Trigger**: `tap_text("Settings", system=true)` against the
  Samsung Settings home from a fresh boot, phone locale = Polish
- **Observed**: `UiElementNotFoundFailure` with
  `next_action="tap_text"`
- **Expected**: should land on Settings (it's a system app)
- **Reproducible?**: yes, every time on this locale
- **Notes**: changed locale to English → worked first try.
  Confirms the issue is locale-specific.

### Later — in-app `tap_text("Save changes")` flow

- **Trigger**: Patrol-style plan that taps "Save changes" inside
  a feature flow, app in Polish
- **Observed**: same failure — the button label was actually
  "Zapisz zmiany" in Polish
- **The deeper find**: when we audited the source, two layers
  deep there was `Text('Save changes')` instead of
  `AppLocalizations.of(c)!.saveChanges`. The string was never
  going to translate — the app shipped it as a literal.

### Reading the source

- Confirmed by grep: 12 hardcoded `Text('...')` strings in lib/
- Confirmed by grep: 0 `find.text('...')` usages in widget tests
  that would have caught this at CI time

---

## Findings

### Automated cases that landed

1. **`audit_localization` rule: `hardcoded_user_text`** (junior tier)
   - Slug: `should_flag_hardcoded_user_text_in_Text_widget`
   - Tool: `audit_localization` (phase 9)
   - Severity: serious
   - Catches `Text('Save changes')` and the 6 sibling widget
     constructors (Tooltip, AppBar, Button, SnackBar, AlertDialog,
     hint/label/helper/error text)

2. **`audit_test_quality` rule: `hardcoded_locale_string`** (junior tier)
   - Slug: `should_flag_find_text_with_hardcoded_english_label`
   - Tool: `audit_test_quality` (phase 12)
   - Severity: minor
   - Catches `find.text('Sign in')` in widget tests that aren't
     wrapped with `AppLocalizations`-aware setup

3. **Documentation entry**: `docs/localization-rubric.md` opens
   with the "Settings → Ustawienia" lesson verbatim so the next
   reader understands WHY the rule exists

### Findings NOT yet automated

- Tap-by-resource-id fallback when text-based selectors fail —
  would be nice but requires changing `tap_text` itself, not just
  audit rules. Deferred.
- Locale-aware test fixtures that swap context.l10n at boot —
  belongs in `design_test_plan`'s factory recommendations.
  Implicitly addressed in phase 11.5 but no automated case.

### Charter health check

- Mission was tight and correct
- 30 minutes was about right; the surface was small
- Highest-value area: walking the source after the test failed.
  The audit chain that came out of it is the entire reason phase
  9 exists.

---

## Follow-up

- [x] Phase 9 `audit_localization` shipped (PR #30)
- [x] Phase 12 `audit_test_quality` shipped (PR #34) with the
  `hardcoded_locale_string` rule
- [x] `docs/localization-rubric.md` opens with this story
