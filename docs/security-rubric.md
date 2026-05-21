# Security Rubric — `audit_security`

> Companion document to the **`audit_security`** MCP tool shipped
> in `mcp-phone-controll` v0.3.0 phase 8. Aligned to the OWASP
> Mobile Application Security Verification Standard
> ([MASVS v2.0](https://mas.owasp.org/MASVS/)).

## What the tool answers

`flutter analyze` answers: *does this compile?*
`audit_code_seniority` answers: *does this look senior?*
`audit_security` answers: *will this leak secrets or weaken
transport security?*

It's a regex-over-text scanner, not a SAST. It catches the
**20 patterns most likely to ship to production and cause real
incidents** — hardcoded keys, cleartext HTTP, debug-signed
release builds, SharedPreferences for tokens. The kinds of
things a senior reviewer spots in 30 seconds.

## Critical principle: secrets are REDACTED in findings

The audit must not leak its own findings into PR comments. Every
finding that includes a literal secret (AWS key, JWT, etc.) has
the secret value masked in the `snippet` field. Only the first
and last 4 characters survive; everything in between is
asterisks. The fix_hint says *what* to do; the snippet shows
*where*.

## Grade thresholds

| Grade | Condition |
|---|---|
| `secure` | No findings, or only suppressed lower-severity ones. |
| `acceptable` | One or more `high` findings, no `critical`. Score < 15. |
| `at_risk` | 5+ `high` findings OR score ≥ 15. No `critical`. |
| `critical` | **Any** `critical` finding. Ship-blocker. |

Severity weights: critical = 20, high = 6, medium = 1. Score =
weighted findings per KLOC.

A single AWS key literal pushes the grade to `critical` no
matter how clean the rest of the codebase is. That's intentional
— one leaked key ends careers.

## The 20 rules

### Tier — CRITICAL (5 rules)

**`hardcoded_api_key`** — AWS/Stripe/SendGrid/Slack key patterns
in source. Catches the wire formats: `AKIA[A-Z0-9]{16}`,
`sk_live_*`, `SG.*.*`, `xox[abps]-*`. Move to `--dart-define` or
a secret manager; rotate the leaked key.

**`hardcoded_firebase_key`** — Google API key (`AIza...`) in
source. Firebase web keys are sometimes legitimately public, but
they should still come from `firebase_options.dart` via
`flutterfire configure`, not be bare strings.

**`hardcoded_jwt`** — JWT literal (3-part base64) in source.
Tokens belong in `flutter_secure_storage`, not source.

**`hardcoded_pem`** — `-----BEGIN PRIVATE KEY-----` block in
source. Private keys must live in hardware-backed keystores
(Android Keystore / iOS Keychain).

**`committed_env_file`** — `.env*` file present at repo root
without being in `.gitignore`. The mere presence is the smell;
contents don't need to be secrets for the rule to fire.

### Tier — HIGH (9 rules)

**`cleartext_http`** — `http://` URL in non-test source
(excluding `localhost`, `127.0.0.1`, `10.0.2.2`, `0.0.0.0`).
Suppress per-line with `// allow-http` if intentional.

**`prefs_for_secrets`** — `SharedPreferences.setString('token',
...)` etc. Sensitive key names: token, password, secret, api_key,
bearer, refresh_token, jwt, session.

**`missing_secure_storage`** — token-shaped variable stored
without going through `flutter_secure_storage`. (Heuristic;
narrow.)

**`webview_js_unguarded`** — `WebView` with
`JavaScriptMode.unrestricted` but no `NavigationDelegate` in the
same file. JS can hit the device's network freely once loaded.

**`cleartext_traffic_allow`** — `android:usesCleartextTraffic="true"`
in `AndroidManifest.xml`. All HTTP is allowed app-wide.

**`ats_disabled`** — iOS `NSAllowsArbitraryLoads = true` in
`Info.plist`. ATS fully disabled.

**`debug_signing_in_release`** — Gradle release buildType uses
`signingConfigs.debug`. Production builds shipped under the
debug keystore.

**`exported_component`** — Android Activity/Service/Provider with
`android:exported="true"` and no `android:permission` attribute.
Other apps can invoke it directly.

**`biometric_no_fallback`** — `LocalAuthentication` used without
`biometricOnly: true`. App falls back to device PIN even when
the developer expected biometric-only.

### Tier — MEDIUM (6 rules)

**`missing_cert_pinning`** — `Dio()` / `http.Client()` used for
auth-shaped endpoints (`/auth`, `/login`, `/token`, `/oauth`)
without any visible certificate-pinning setup
(`BadCertificateCallback`, `http_certificate_pinning`,
`SecurityContext`).

**`print_leaks_pii`** — `print(...)` of a sensitive variable
(token, password, email, jwt, bearer, api_key). PII reaches
logcat / device logs.

**`debug_only_unguarded`** — a `// DEBUG ONLY` comment present
in a file with no `kDebugMode` / `kReleaseMode` / `kProfileMode`
import. Likely a debug surface that ships to release.

**`root_detection_missing`** — *(reserved; not yet implemented
in the scanner — listed for forward-compatibility)*

**`screenshot_not_blocked`** — *(reserved; not yet implemented)*

**`clipboard_for_secrets`** — `Clipboard.setData` with a
sensitive-looking variable. System clipboard is world-readable
on Android; other apps can poll it.

## What the tool is NOT

- **Not a SAST product.** A real SAST tool runs taint analysis
  across function boundaries. This is regex over text. False
  negatives expected on dynamic string composition (e.g.
  building a URL from parts at runtime).
- **Not a guarantee.** A `secure` grade means *no known patterns
  fired*, not *this app is secure*. Independent security review
  remains necessary for production apps that handle money,
  health data, or auth.
- **Not a certificate-validation checker.** Cert pinning happens
  at runtime; we can only flag the absence of obvious pinning
  setup in the HTTP client.
- **Not project-agnostic.** Rules like `prefs_for_secrets`
  expect `flutter_secure_storage` as the alternative. Teams on
  different stacks tune the rule set.

## Using the tool

```python
# Full scan
result = audit_security(project_path="/path/to/project")
print(result.grade)            # "secure" | "acceptable" | "at_risk" | "critical"
print(result.advice)           # paste-ready PR comment
print(result.top_actions)      # 5 highest-impact remediations

# CI gate: only fail on critical/high
result = audit_security(
    project_path="...",
    min_severity="high",       # suppress medium-tier noise
)
assert result.grade != "critical"
```

## Suppression conventions

- Per-line: append `// allow-http` to suppress `cleartext_http`
  on a specific line (e.g. an internal staging URL).
- Per-rule: filter `result.findings` by `rule` in the caller.
- Per-project: raise `min_severity` to `"high"` or `"critical"`
  to silence the lower tiers entirely.

## Integration with the v0.3.0 audit suite

`audit_security` is one of the four pre-PR audits:

```python
seniority  = audit_code_seniority(project_path="...")   # style + design
security   = audit_security(project_path="...")         # OWASP MASVS
accessibility = audit_accessibility(serial="...")       # WCAG 2.2 (needs device)
size_delta = analyze_app_size(project_path="...")       # release size
```

Phase 11's `audit_release_readiness` will compose all four into
a single ship/hold/block verdict.

## OWASP MASVS control mapping

| Rule | MASVS control |
|---|---|
| hardcoded_api_key | MSTG-CRYPTO-1 |
| hardcoded_jwt | MSTG-AUTH-1 |
| hardcoded_pem | MSTG-CRYPTO-1 |
| hardcoded_firebase_key | MSTG-STORAGE-1 |
| committed_env_file | MSTG-STORAGE-1 |
| cleartext_http | MSTG-NETWORK-1 |
| cleartext_traffic_allow | MSTG-NETWORK-1 |
| ats_disabled | MSTG-NETWORK-1 |
| missing_cert_pinning | MSTG-NETWORK-2 |
| prefs_for_secrets | MSTG-STORAGE-1 |
| clipboard_for_secrets | MSTG-STORAGE-2 |
| print_leaks_pii | MSTG-CODE-4 |
| webview_js_unguarded | MSTG-PLATFORM-2 |
| exported_component | MSTG-PLATFORM-1 |
| debug_signing_in_release | MSTG-RESILIENCE-1 |
| debug_only_unguarded | MSTG-RESILIENCE-3 |
| biometric_no_fallback | MSTG-AUTH-2 |
