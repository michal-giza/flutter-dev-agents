# Localization Rubric

> Companion to `audit_localization` (v0.3.0 phase 9).

A Polish-locale phone broke `tap_text('Settings')` earlier this
year because the visible label was `Ustawienia`, not 'Settings'.
The user's test code looked clean. The app's `lib/` looked clean.
The breakage was in a hardcoded `Text('Settings')` two layers
deep that nobody had migrated to `AppLocalizations`. That's the
story this tool exists to prevent.

## What this answers

`flutter analyze` won't tell you:

- Which `Text('...')` calls in `lib/` are user-facing strings
  that should have been keyed
- Whether `intl_pl.arb` is missing translations that `intl_en.arb`
  defines
- Whether your `MaterialApp.supportedLocales` actually matches
  the `.arb` files you ship
- Whether your app supports Arabic on paper but has no RTL
  plumbing anywhere

This tool does.

## Result fields

| Field | What it means |
|---|---|
| `grade` | `well_localized` / `acceptable` / `single_locale` / `missing_l10n` |
| `score` | weighted findings per KLOC (blocker=10, serious=4, minor=1) |
| `locales_detected` | locales found from arb filenames |
| `keys_total` | keys in the default arb |
| `keys_used` | keys referenced via `AppLocalizations.of(c)!.foo` or `context.l10n.foo` |
| `keys_unused` | keys in arb but never used in code |
| `hardcoded_strings` | unique hardcoded user-facing strings detected |
| `top_actions` | 5 highest-impact remediations |
| `advice` | one-line PR-comment summary |

## Decision tree

```
Project state...
├── No .arb files + 10+ hardcoded user strings
│   └── grade=missing_l10n → set up flutter_localizations + arb
│
├── 1 locale, lots of hardcoded strings
│   └── grade=single_locale → migrate Text(...) → AppLocalizations
│
├── Multi-locale, some keys missing in some .arb
│   └── grade=acceptable → fill the gaps
│
└── Multi-locale, no missing keys, no hardcoded strings
    └── grade=well_localized → ship internationally
```

## The 16 rules

### Tier 1 — Junior (hardcoded strings)

These are the obvious smells. AI agents (and juniors) reach for
`Text('Save changes')` because it's the shortest path to a
working screen.

#### `hardcoded_user_text` — **serious**
A literal string inside `Text(...)`, `Tooltip(message:...)`,
`AppBar(title: Text(...))`, `ElevatedButton(child: Text(...))`,
`SnackBar(content: Text(...))`, `AlertDialog(title:/content:)`,
`hintText:`, `labelText:`, `helperText:`, `errorText:`.

Excluded by the heuristic (not flagged): asset paths
(`assets/...`), URLs, MIME types, snake_case identifiers, hex
codes, single-character strings.

**Standard:** Flutter i18n docs.

### Tier 2 — Mid (key catalog drift)

These catch divergence between code and arb files.

#### `missing_l10n_key` — **blocker**
Code references `AppLocalizations.of(c)!.someKey` but `someKey`
isn't in the default `.arb` file. The Flutter `gen-l10n` output
will be broken or the call will throw at runtime.

#### `unused_l10n_key` — **minor**
A key defined in `.arb` but never used in code. Either delete
it or wire it. Capped at 20 findings per scan to keep output
bounded.

#### `missing_translation_for_locale` — **serious**
A key is in `intl_en.arb` (default) but missing from
`intl_pl.arb`. The Polish user sees the English fallback
silently. Catch this BEFORE shipping.

#### `direct_text_concatenation` — **serious**
`Text('Hello ' + name + '!')`. Word order varies by language —
in Hungarian, the name goes after a postposition. Use
`Intl.message('Hello {name}!', args: [name])`.

### Tier 3 — Senior (plumbing)

These catch wiring mistakes in the app shell.

#### `missing_flutter_localizations` — **blocker**
You have `.arb` files but no `flutter_localizations: sdk:
flutter` in `pubspec.yaml`. The generated code won't compile.

#### `supported_locales_mismatch` — **serious**
Either direction:
- `supportedLocales:` declares `Locale('pl')` but no `pl.arb` exists → runtime falls back, user gets English on a Polish phone
- An orphan `de.arb` exists but `Locale('de')` isn't in `supportedLocales` → never loaded

#### `missing_localizations_delegates` — **blocker**
Multiple locales configured but `localizationsDelegates:` not
set on `MaterialApp`. Material widgets won't translate.

### Tier 4 — Staff (architecture)

These are the architectural gaps.

#### `pluralization_via_if` — **serious**
`count == 1 ? 'item' : 'items'`. Catastrophic on languages with
multiple plural forms — **Polish has 3** (1, few, many), **Arabic
has 6** (zero, one, two, few, many, other). Use `Intl.plural`.

#### `right_to_left_unsupported` — **serious**
Project declares an RTL locale (`ar`, `he`, `fa`, `ur`, `yi`,
`sd`, `ps`) but no `Directionality` widget or `TextDirection`
usage anywhere in `lib/`. The UI will read left-to-right for
RTL users. Audit with logical insets (`startPadding`,
`endPadding`) instead of `left`/`right`.

## What this is NOT

- **Not a translator.** We flag missing translations; we don't
  fill them.
- **Not a runtime checker.** Static config vs arb files only.
- **Not RTL-perfect.** Absence of plumbing only; can't verify
  any given layout mirrors correctly.
- **Not project-agnostic.** Encodes Flutter ecosystem
  conventions (`AppLocalizations.of(c)!.key`, `intl_*.arb`
  filenames, `flutter_localizations` package). Other stacks
  would tune.

## How to use

```python
# Full audit on a multi-locale project
result = audit_localization(
    project_path="/path/to/project",
    min_level="junior",  # catch everything
)
print(result.grade)               # 'acceptable'
print(result.locales_detected)    # ('en', 'pl')
print(result.advice)              # paste into PR
```

Override the arb directory if you don't use the default:

```python
audit_localization(
    project_path="/path/to/project",
    arb_dir="lib/src/i18n",  # non-default location
)
```

## Composition with the rest of v0.3.0

```python
audit_code_seniority(...)    # architecture
audit_security(...)          # OWASP MASVS
audit_localization(...)      # i18n hygiene  ← new
audit_accessibility(...)     # WCAG 2.2
audit_app_size(...)          # binary size
```

All five compose into `audit_release_readiness` (phase 11). Each
is pure compute, sub-second on a typical app, safe to run on a
developer's daily device.

## Tuning for your team

If your team uses a non-standard pattern (e.g. a custom
`Strings` class instead of `AppLocalizations`), the hardcoded-
string detector will fire incorrectly. Options:

1. Raise `min_level="senior"` to skip the junior tier
2. Move your `Strings.signIn` references into the same shape
   `AppLocalizations.of(c)!.signIn` so the used-keys collector
   picks them up
3. Wrap the tool in your own MCP adapter that filters specific
   `rule` names

The rubric is opinionated on purpose — it encodes the canonical
Flutter i18n setup, which is what makes the grade meaningful.
