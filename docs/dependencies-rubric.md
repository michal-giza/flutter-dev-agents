# Dependencies Rubric

> Companion to `audit_dependencies` (v0.3.0 phase 10).

`flutter pub outdated` tells you which packages have newer
versions on pub.dev. This tool answers a different question:
**is your dependency tree healthy and shippable?**

Healthy means:

- No floating pins on security-sensitive code paths
- No git/path overrides leaking into a published app
- No dev tools accidentally landed in `dependencies:`
- No imports of packages you didn't declare
- No declarations you don't import
- No deprecated `package_info` / `connectivity` / etc.

## What this answers

| Question | Tool |
|---|---|
| What's newer on pub.dev? | `flutter pub outdated` |
| Are my pins healthy? | `audit_dependencies` |
| Are there known CVEs? | Dependabot / pub.dev advisory |
| Is my license stack compatible? | A real legal tool (this gives hints only) |

## Result fields

| Field | Meaning |
|---|---|
| `grade` | `clean` / `acceptable` / `at_risk` / `blocked` |
| `score` | weighted findings per declared dependency |
| `deps_total` | direct dependencies count |
| `dev_deps_total` | dev_dependencies count |
| `deps_unused` | declared but never imported under `lib/` |
| `deps_undeclared` | imported under `lib/` but not in pubspec (transitive promotion risk) |
| `top_actions` | 5 highest-impact remediations |

## The 14 rules

### Tier 1 — Junior

#### `dev_dep_in_dependencies` — **serious**
A build/test tool (`build_runner`, `mockito`, `flutter_test`,
`patrol`, `flutter_lints`, `freezed`, `json_serializable`,
etc.) declared under `dependencies:` instead of
`dev_dependencies:`. Inflates the shipped binary with code
only the build needs.

#### `git_or_path_override` — **serious** (only when `is_published=True`)
A nested-map dependency value, which typically means
`git:` / `path:` / `hosted:` override. Fine for in-house tools;
a smell for apps you ship to production via pub.

Set `is_published=False` if your project is internal-only —
the rule then stays silent.

### Tier 2 — Mid

#### `pinned_to_caret_only` — **minor**
A security-sensitive package (`firebase_auth`, `firebase_core`,
`firebase_messaging`, `dio`, `http`, `flutter_secure_storage`,
`webview_flutter`, `google_sign_in`, `sign_in_with_apple`,
`local_auth`, `jwt_decoder`, `encrypt`, `pointycastle`,
`shared_preferences`, etc.) uses a caret range (`^1.0.0`).
Caret lets minor versions float — a critical auth change can
land without you noticing. Pin tightly for these.

#### `wide_version_range` — **serious**
A constraint like `'>=1.0.0 <4.0.0'` spans 2+ major versions.
Breaking changes can slip in silently. Tighten the upper
bound.

#### `outdated_majors` — **minor**
A drift between the pubspec constraint and the lockfile pin
(usually indicating bad data or that you need to
`flutter pub upgrade --major-versions`).

### Tier 3 — Senior

#### `unused_dependency` — **minor** (capped at 20)
Declared in pubspec but no `import 'package:X/...';` anywhere
under `lib/`. Either remove it or move to `dev_dependencies`
if only tests use it.

#### `transitive_used_as_direct` — **serious** (capped at 20)
Code under `lib/` imports a package that isn't declared in
`dependencies:` or `dev_dependencies:`. Works only as long as
some other package brings it in transitively — silent breakage
the day that other package drops the transitive.

#### `duplicated_dependency` — **serious**
The same package name in both `dependencies:` and
`dev_dependencies:`. Ambiguous resolution; pick one.

### Tier 4 — Staff

#### `known_vulnerable_package` — **serious**
A curated short list of packages with well-publicized issues:

| Package | Issue |
|---|---|
| `flutter_html` | Frequent CVE history; use allowlist renderer |
| `package_info` | Discontinued → `package_info_plus` |
| `connectivity` | Discontinued → `connectivity_plus` |
| `device_info` | Discontinued → `device_info_plus` |
| `battery` | Discontinued → `battery_plus` |
| `android_intent` | Discontinued → `android_intent_plus` |
| `share` | Discontinued → `share_plus` |
| `sensors` | Discontinued → `sensors_plus` |

Kept intentionally short — false positives are worse than
false negatives here.

#### `flutter_sdk_constraint_loose` — **minor**
`flutter: '>=3.0.0'` in `environment:` with no upper bound.
Future SDK changes can silently break the app. Use
`'>=3.16.0 <4.0.0'` style.

#### `license_blocklist` — **minor**
Package name contains `gpl`, `agpl`, or `lgpl` — possible
copyleft license. We don't read LICENSE files (offline tool),
just surface the hint for human review.

## Grade thresholds

```
ANY blocker     → blocked    (do not merge)
score ≥ 4 OR
  5+ serious    → at_risk
score ≥ 1 OR
  1+ serious    → acceptable
otherwise       → clean
```

`score = weighted findings / direct dependencies` where
blocker=10, serious=4, minor=1.

## Composition with the rest of v0.3.0

```python
audit_code_seniority(...)    # architecture
audit_security(...)          # OWASP MASVS — the runtime side
audit_localization(...)      # i18n hygiene
audit_dependencies(...)      # supply chain  ← new
audit_accessibility(...)     # WCAG 2.2
analyze_app_size(...)        # binary
```

All six compose into `audit_release_readiness` (phase 11) for
one ship/hold/block verdict.

## What this is NOT

- **Not a CVE scanner.** Use Dependabot / `flutter pub
  outdated` / pub.dev advisories for real CVEs.
- **Not a license auditor.** We hint; real compliance needs a
  legal tool.
- **Not a transitive scanner.** We only check declared deps,
  not their transitive trees.
- **Pure offline.** No network, no pub.dev API calls. Runs in
  any sandboxed CI.
