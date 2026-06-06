# Flutter Web Rubric

> Companion to `audit_web_app` + `ingest_lighthouse_report`
> (v0.5.0 phases 15 + 16).

The mobile audits (`audit_security`, `audit_accessibility`) don't
know about web-specific concerns. These two tools fill the gap —
one static (walks `web/`), one runtime (parses Lighthouse).

## The two tools

| Tool | Layer | Input | Answers |
|---|---|---|---|
| `audit_web_app` | static | `web/index.html` + `manifest.json` + `_headers` | Is the web shell production-ready? |
| `ingest_lighthouse_report` | runtime | Lighthouse JSON | Are the live web vitals good? |

They compose with `audit_release_readiness`, which now has two
optional web domains (phase 16.5):
- `web_app` — auto-runs if `web/` exists, auto-excluded otherwise
- `web_vitals` — opt-in via `lighthouse_report_path`

## `audit_web_app` — the 12 rules

### Tier 1 — Junior (immediate smells)

| Rule | Severity | What |
|---|---|---|
| `html_no_lang_attr` | serious | `<html>` without `lang="..."` — screen readers can't announce language, SEO can't classify. **The Flutter default template ships a bare `<html>`.** |
| `no_viewport_meta` | serious | No `<meta name="viewport">` — mobile browsers render at desktop width |
| `placeholder_meta_description` | minor | The scaffolded "A new Flutter project." description still present |
| `no_favicon` | minor | No favicon in `web/` — blank tab icon |

### Tier 2 — Mid (config hygiene)

| Rule | Severity | What |
|---|---|---|
| `no_csp` | serious | No Content-Security-Policy (meta tag OR `_headers` entry) — XSS runs unrestricted |
| `manifest_missing_pwa_fields` | serious | `manifest.json` missing name/short_name/start_url/display/icons — install prompt won't fire |
| `manifest_no_maskable_icon` | minor | Icons present but none with `purpose:maskable` — Android letterboxes the icon |
| `no_theme_color` | minor | No `<meta name="theme-color">` — browser chrome won't match brand |

### Tier 3 — Senior (production-readiness)

| Rule | Severity | What |
|---|---|---|
| `placeholder_app_name` | serious | manifest `name` is the scaffold default — this is the PWA install title |
| `no_seo_meta` | serious | No Open-Graph tags — shared links render as a blank grey card |
| `no_apple_touch_icon` | minor | No `apple-touch-icon` — blurry iOS home-screen icon |

### Tier 4 — Staff (UX architecture)

| Rule | Severity | What |
|---|---|---|
| `no_loading_indicator` | minor | No splash/loading element before Flutter boots — blank white page during the CanvasKit/wasm download (1–3s cold load) |

### Grade

```
ANY blocker                         → not_production_ready
3+ serious                          → not_production_ready
1-2 serious                         → needs_polish
0 serious, some minor               → acceptable
0 findings                          → excellent
no web/ dir                         → not_web_app (excluded from composite)
```

### CSP detection

CSP can live in two places — we check both:
1. `<meta http-equiv="Content-Security-Policy">` in index.html
2. A `Content-Security-Policy:` line in `web/_headers`
   (Cloudflare Pages / Netlify convention)

## `ingest_lighthouse_report` — web vitals

You generate the report:

```bash
lighthouse https://your-app.pages.dev \
  --output=json --output-path=lighthouse.json --quiet
```

Then we parse it:

```python
ingest_lighthouse_report(report_path="lighthouse.json")
```

### Returns

- `grade` — good / needs_improvement / poor / blocked
- `overall_score` — mean of the category scores
- `categories[]` — performance / accessibility / best-practices / seo / pwa, each with a score + grade
- `web_vitals[]` — LCP, CLS, TBT, FCP, SI, TTI with numeric values + grades
- `lcp_s`, `cls`, `tbt_ms` — the headline Core Web Vitals as typed numbers
- `top_opportunities[]` — top 5 perf opportunities by potential savings
- `advice` — paste-ready summary

### The CanvasKit-aware threshold

**A "perfect" Lighthouse perf score is rare for Flutter web.** The
CanvasKit renderer ships a ~1.5MB wasm payload, so even a
well-built CanvasKit app often scores 65–80 on performance. We
account for this:

- Default `perf_good_threshold = 70` (not Lighthouse's own 90)
- A perf score of 72 with good Core Web Vitals → **good**, not penalised
- Pass `perf_good_threshold=90` if you ship the HTML/wasm renderer (which scores higher)

### Grade thresholds (Google's official Core Web Vitals boundaries)

| Metric | Good | Needs improvement | Poor (→ blocked) |
|---|---|---|---|
| LCP (Largest Contentful Paint) | < 2.5s | 2.5–4.0s | ≥ 4.0s |
| CLS (Cumulative Layout Shift) | < 0.1 | 0.1–0.25 | ≥ 0.25 |
| TBT (Total Blocking Time) | < 200ms | 200–600ms | ≥ 600ms |

Plus: **accessibility < 50 → blocked** (a11y is a release gate for us).

## The composition story

The full Flutter-web release loop, composing our tools with
Lighthouse + (optionally) Chrome MCP / Maestro:

```
1. audit_web_app                  ← static: is web/ shell ready?
       ↓ (fix CSP, SEO, lang, manifest)
2. flutter build web              ← (Google's dart_mcp or shell)
       ↓
3. lighthouse <url> --output=json ← you run it (or CI does)
       ↓
4. ingest_lighthouse_report       ← parse vitals
       ↓
5. audit_release_readiness        ← composite, now 8 domains:
   project_path=...                  seniority/security/l10n/deps/
   lighthouse_report_path=...        test_quality/test_execution/
                                     web_app/web_vitals
       ↓
   verdict == ship → deploy
```

For actual browser interaction (clicking through the running web
app), compose with:
- **Chrome MCP** (`mcp__claude-in-chrome__*`) — DOM-aware driving
- **Maestro** — Maestro runs Flutter web flows; then
  `ingest_maestro_report` parses results

We don't ship a browser driver — that's the layer the others own.
See `docs/the-stack.md`.

## Running tests for a web app

Flutter web apps whose code imports `dart:html` (directly or
transitively — which is most of them) **won't compile on the default
VM test platform**. `flutter test` errors with:

```
Error: Dart library 'dart:html' is not available on this platform.
```

`run_unit_tests` and `run_widget_test` handle this (v0.5.2):

```python
run_unit_tests(project_path="...")                    # platform="auto"
```

- **`platform="auto"` (default)** — runs on the VM, then transparently
  retries on `--platform chrome` if it hits the web-only-library marker.
  So a web app "just works" without you flagging it.
- **`platform="chrome"`** — force Flutter web (skips the VM probe).
- **`platform="vm"`** — force the default VM, no retry.

This mirrors the convention web repos already use
(`flutter test --platform chrome`).

## What this is NOT

- **Not a Lighthouse runner.** You (or CI) run `lighthouse`; we
  parse the JSON. Same posture as `ingest_maestro_report`.
- **Not a browser driver.** Compose with Chrome MCP / Maestro.
- **Not opinionated about renderer.** CanvasKit vs dart2wasm is a
  build flag; we tune the perf threshold for it but don't enforce
  a choice.

## Field-test result (bike_news_room/frontend)

The first real web app we ran `audit_web_app` against:

```
grade: needs_polish
has_csp: True | has_pwa: True | locales_hint: en
findings: 1
  [serious] html_no_lang_attr (web/index.html:1)
```

Exactly one real finding — the `<html>` tag with no `lang`
attribute — on an otherwise exemplary web app (CSP present, full
PWA manifest, SEO/OG meta, maskable icons, splash). Zero false
positives. The fix is one attribute: `<html lang="en">`.
