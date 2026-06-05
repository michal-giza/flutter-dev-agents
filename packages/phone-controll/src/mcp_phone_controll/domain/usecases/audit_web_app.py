"""Flutter web audit — production-readiness rules for the web/
directory.

The mobile-focused audits (`audit_security`, `audit_accessibility`)
don't know about web-specific concerns: Content-Security-Policy,
the PWA manifest, SEO/Open-Graph meta, the `html lang` attribute,
apple-touch-icons, the white-screen-of-load problem.

This use case fills that gap. It walks `web/index.html` +
`web/manifest.json` + the `web/` file listing + `web/_headers`
(Cloudflare Pages / Netlify convention) and applies 12 rules
across 4 tiers.

What it catches:

  **JUNIOR — immediate smells (4 rules)**
    • no_favicon                  — no favicon file in web/
    • html_no_lang_attr           — `<html>` without lang="..."
                                     (a11y + SEO). The Flutter
                                     default template ships
                                     a bare `<html>`.
    • no_viewport_meta            — no `<meta name="viewport">`
    • placeholder_meta_description — the scaffolded
                                     "A new Flutter project."
                                     description still present

  **MID — config hygiene (4 rules)**
    • no_csp                      — no Content-Security-Policy
                                     (meta tag OR _headers entry)
    • manifest_missing_pwa_fields — manifest.json missing one of
                                     name/short_name/start_url/
                                     display/icons
    • manifest_no_maskable_icon   — icons present but none with
                                     purpose:maskable (Android
                                     adaptive-icon requirement)
    • no_theme_color              — no `<meta name="theme-color">`
                                     (PWA chrome theming)

  **SENIOR — production-readiness (3 rules)**
    • placeholder_app_name        — manifest "name" is the
                                     scaffold default
    • no_seo_meta                 — no og:title / og:description
                                     Open-Graph tags (social
                                     sharing renders blank)
    • no_apple_touch_icon         — no apple-touch-icon link
                                     (blurry iOS home-screen icon)

  **STAFF — UX architecture (1 rule)**
    • no_loading_indicator        — no splash/loading element
                                     before Flutter boots
                                     (white-screen-of-load: blank
                                     page during the CanvasKit /
                                     wasm download)

What this is NOT:

  • Not a runtime checker — we read the static web/ files, not
    the served page. For runtime web vitals use
    `ingest_lighthouse_report` (phase 16).
  • Not a browser driver — composes with Chrome MCP / Maestro
    for actual page interaction.
  • Not opinionated about renderer choice — CanvasKit vs
    dart2wasm is a build flag, not statically reliable.

Pure compute. Stdlib only (regex over HTML text + JSON parse of
manifest). No HTML-parser dependency — Flutter's generated
index.html is regular enough for targeted regex.

Citations:
  Flutter web deployment docs, web.dev PWA checklist,
  WCAG 3.1.1 (Language of Page), Open Graph protocol.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from .base import BaseUseCase


class Severity(str, Enum):
    BLOCKER = "blocker"   # ships broken UX / breaks PWA install
    SERIOUS = "serious"   # production-readiness gap
    MINOR = "minor"       # polish


class WebQualityLevel(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"


@dataclass(frozen=True, slots=True)
class WebAppFinding:
    rule: str
    description: str
    severity: Severity
    level: WebQualityLevel
    file: str
    line: int                # 1-indexed; 0 if file-level
    snippet: str
    fix_hint: str | None
    standard: str | None


@dataclass(frozen=True, slots=True)
class AuditWebAppParams:
    project_path: Path
    # Override the web directory; default tries 'web'.
    web_dir: str | None = None
    min_level: str = "junior"
    max_findings: int = 200


@dataclass(frozen=True, slots=True)
class AuditWebAppResult:
    # excellent / acceptable / needs_polish / not_production_ready / not_web_app
    grade: str
    score: float                                # weighted findings (capped)
    has_index_html: bool
    has_manifest: bool
    has_csp: bool
    has_pwa_manifest: bool                      # all required fields present
    locales_hint: str | None                   # manifest "lang" if present
    findings: tuple[WebAppFinding, ...]
    findings_by_level: dict[str, int]
    findings_by_severity: dict[str, int]
    top_actions: tuple[str, ...]
    advice: str


_SEVERITY_WEIGHT = {
    Severity.BLOCKER: 10,
    Severity.SERIOUS: 4,
    Severity.MINOR: 1,
}

_REQUIRED_MANIFEST_FIELDS = (
    "name", "short_name", "start_url", "display", "icons",
)

# Scaffold defaults that signal "never customised"
_SCAFFOLD_DESCRIPTIONS = (
    "A new Flutter project.",
)


class AuditWebApp(BaseUseCase[AuditWebAppParams, AuditWebAppResult]):
    """Audits a Flutter web app's web/ directory.

    Pure compute. No browser, no network. Regex over index.html +
    JSON parse of manifest.json + file listing.
    """

    async def execute(
        self, params: AuditWebAppParams
    ) -> Result[AuditWebAppResult]:
        if not params.project_path.is_dir():
            return err(FilesystemFailure(
                message=f"project_path not found: {params.project_path}",
                next_action="fix_arguments",
            ))
        try:
            min_level = WebQualityLevel(params.min_level)
        except ValueError:
            return err(FilesystemFailure(
                message=(
                    f"unknown min_level {params.min_level!r}. "
                    "Valid: junior, mid, senior, staff"
                ),
                next_action="fix_arguments",
            ))

        web_dir = (
            params.project_path / params.web_dir
            if params.web_dir
            else params.project_path / "web"
        )
        index_html = web_dir / "index.html"

        if not web_dir.is_dir() or not index_html.is_file():
            return ok(_not_web_app_result())

        try:
            html = index_html.read_text(encoding="utf-8", errors="replace")
        except OSError:
            html = ""

        manifest_path = web_dir / "manifest.json"
        manifest: dict | None = None
        if manifest_path.is_file():
            try:
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8", errors="replace")
                )
            except (json.JSONDecodeError, OSError):
                manifest = None

        headers_text = ""
        headers_path = web_dir / "_headers"
        if headers_path.is_file():
            headers_text = headers_path.read_text(
                encoding="utf-8", errors="replace"
            )

        web_files = {f.name.lower() for f in web_dir.iterdir() if f.is_file()}
        web_subdirs = {d.name.lower() for d in web_dir.iterdir() if d.is_dir()}

        all_findings: list[WebAppFinding] = []
        has_csp = _has_csp(html, headers_text)
        has_pwa = _manifest_has_all_required(manifest)

        all_findings.extend(_scan_index_html(html, has_csp))
        all_findings.extend(
            _scan_manifest(manifest, manifest_path.is_file())
        )
        all_findings.extend(
            _scan_web_dir(web_files, web_subdirs, html)
        )

        # Filter by min_level
        order = [
            WebQualityLevel.JUNIOR, WebQualityLevel.MID,
            WebQualityLevel.SENIOR, WebQualityLevel.STAFF,
        ]
        kept = set(order[order.index(min_level):])
        all_findings = [f for f in all_findings if f.level in kept]

        sev_idx = {
            Severity.BLOCKER: 0, Severity.SERIOUS: 1, Severity.MINOR: 2,
        }
        all_findings.sort(
            key=lambda x: (sev_idx[x.severity], x.file, x.line)
        )
        all_findings_t = tuple(all_findings[: params.max_findings])

        by_level: dict[str, int] = {}
        by_sev: dict[str, int] = {}
        for f in all_findings_t:
            by_level[f.level.value] = by_level.get(f.level.value, 0) + 1
            by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1

        weighted = sum(_SEVERITY_WEIGHT[f.severity] for f in all_findings_t)
        score = float(weighted)
        grade = _grade_for(by_sev, len(all_findings_t))

        locales_hint = None
        if isinstance(manifest, dict):
            lang = manifest.get("lang")
            if isinstance(lang, str):
                locales_hint = lang

        return ok(AuditWebAppResult(
            grade=grade,
            score=round(score, 2),
            has_index_html=True,
            has_manifest=manifest_path.is_file(),
            has_csp=has_csp,
            has_pwa_manifest=has_pwa,
            locales_hint=locales_hint,
            findings=all_findings_t,
            findings_by_level=by_level,
            findings_by_severity=by_sev,
            top_actions=_build_top_actions(all_findings_t),
            advice=_build_advice(
                grade, has_csp, has_pwa, len(all_findings_t),
            ),
        ))


# ============================================================
# Compiled regex
# ============================================================

_RE_HTML_TAG = re.compile(r"<html(\s[^>]*)?>", re.IGNORECASE)
_RE_LANG_ATTR = re.compile(r"""\blang\s*=\s*['"][a-zA-Z-]+['"]""")
_RE_VIEWPORT = re.compile(
    r"""<meta[^>]+name\s*=\s*['"]viewport['"]""", re.IGNORECASE
)
_RE_DESC = re.compile(
    r"""<meta[^>]+name\s*=\s*['"]description['"][^>]+content\s*=\s*['"]([^'"]*)['"]""",
    re.IGNORECASE,
)
_RE_CSP_META = re.compile(
    r"""http-equiv\s*=\s*['"]Content-Security-Policy['"]""", re.IGNORECASE
)
_RE_THEME_COLOR = re.compile(
    r"""<meta[^>]+name\s*=\s*['"]theme-color['"]""", re.IGNORECASE
)
_RE_OG_TITLE = re.compile(
    r"""property\s*=\s*['"]og:(title|description)['"]""", re.IGNORECASE
)
_RE_APPLE_TOUCH = re.compile(
    r"""<link[^>]+rel\s*=\s*['"]apple-touch-icon['"]""", re.IGNORECASE
)
_RE_LOADING = re.compile(
    r"""id\s*=\s*['"](loading|splash|loader|app-loading)['"]"""
    r"""|class\s*=\s*['"][^'"]*(loading|splash|loader)[^'"]*['"]""",
    re.IGNORECASE,
)


# ============================================================
# index.html scanner
# ============================================================


def _scan_index_html(html: str, has_csp: bool) -> list[WebAppFinding]:
    out: list[WebAppFinding] = []
    if not html.strip():
        return out

    # Junior: html_no_lang_attr
    m = _RE_HTML_TAG.search(html)
    if m and not _RE_LANG_ATTR.search(m.group(0)):
        line_no = html.count("\n", 0, m.start()) + 1
        out.append(_mk(
            "html_no_lang_attr",
            "<html> tag has no lang attribute. Screen readers can't "
            "announce the page language; SEO crawlers can't classify it.",
            Severity.SERIOUS, WebQualityLevel.JUNIOR,
            "web/index.html", line_no, m.group(0)[:80],
            'Add a lang attribute: `<html lang="en">`.',
            "WCAG 3.1.1 Language of Page",
        ))

    # Junior: no_viewport_meta
    if not _RE_VIEWPORT.search(html):
        out.append(_mk(
            "no_viewport_meta",
            "No <meta name=\"viewport\"> — mobile browsers will render "
            "at desktop width then zoom out.",
            Severity.SERIOUS, WebQualityLevel.JUNIOR,
            "web/index.html", 0, "missing viewport meta",
            'Add `<meta name="viewport" content="width=device-width, '
            'initial-scale=1.0">`.',
            "Responsive web basics",
        ))

    # Junior: placeholder_meta_description
    m = _RE_DESC.search(html)
    if m:
        desc = m.group(1).strip()
        if desc in _SCAFFOLD_DESCRIPTIONS or not desc:
            line_no = html.count("\n", 0, m.start()) + 1
            out.append(_mk(
                "placeholder_meta_description",
                f"Meta description is the scaffold default ({desc!r}). "
                "Search results + social cards show this verbatim.",
                Severity.MINOR, WebQualityLevel.JUNIOR,
                "web/index.html", line_no, m.group(0)[:100],
                "Write a real one-sentence description of the app.",
                "SEO basics",
            ))

    # Mid: no_csp
    if not has_csp:
        out.append(_mk(
            "no_csp",
            "No Content-Security-Policy (no meta tag, no _headers entry). "
            "XSS payloads run unrestricted.",
            Severity.SERIOUS, WebQualityLevel.MID,
            "web/index.html", 0, "no CSP",
            "Add a CSP meta tag tuned for Flutter web (allow "
            "'wasm-unsafe-eval' + www.gstatic.com for CanvasKit), or a "
            "_headers Content-Security-Policy line.",
            "web.dev: Content Security Policy",
        ))

    # Mid: no_theme_color
    if not _RE_THEME_COLOR.search(html):
        out.append(_mk(
            "no_theme_color",
            "No <meta name=\"theme-color\"> — the browser chrome / PWA "
            "title bar won't match your brand.",
            Severity.MINOR, WebQualityLevel.MID,
            "web/index.html", 0, "no theme-color meta",
            'Add `<meta name="theme-color" content="#yourBrandHex">`.',
            "PWA theming",
        ))

    # Senior: no_seo_meta
    if not _RE_OG_TITLE.search(html):
        out.append(_mk(
            "no_seo_meta",
            "No Open-Graph tags (og:title / og:description). Links shared "
            "to Slack / Twitter / iMessage render as a blank grey card.",
            Severity.SERIOUS, WebQualityLevel.SENIOR,
            "web/index.html", 0, "no og: meta",
            'Add `<meta property="og:title" content="...">` + '
            "og:description + og:image.",
            "Open Graph protocol",
        ))

    # Senior: no_apple_touch_icon
    if not _RE_APPLE_TOUCH.search(html):
        out.append(_mk(
            "no_apple_touch_icon",
            "No apple-touch-icon link. iOS 'Add to Home Screen' uses a "
            "blurry auto-generated screenshot instead of your icon.",
            Severity.MINOR, WebQualityLevel.SENIOR,
            "web/index.html", 0, "no apple-touch-icon",
            'Add `<link rel="apple-touch-icon" href="icons/Icon-192.png">`.',
            "iOS web-app icons",
        ))

    return out


# ============================================================
# manifest.json scanner
# ============================================================


def _scan_manifest(
    manifest: dict | None, manifest_exists: bool,
) -> list[WebAppFinding]:
    out: list[WebAppFinding] = []

    if not manifest_exists:
        out.append(_mk(
            "manifest_missing_pwa_fields",
            "No web/manifest.json — the app can't be installed as a PWA.",
            Severity.SERIOUS, WebQualityLevel.MID,
            "web/manifest.json", 0, "file missing",
            "Add a manifest.json with name/short_name/start_url/"
            "display/icons.",
            "web.dev PWA checklist",
        ))
        return out

    if not isinstance(manifest, dict):
        return out  # malformed; JSON parse already skipped it

    # Mid: manifest_missing_pwa_fields
    missing = [
        f for f in _REQUIRED_MANIFEST_FIELDS if not manifest.get(f)
    ]
    if missing:
        out.append(_mk(
            "manifest_missing_pwa_fields",
            f"manifest.json missing required PWA field(s): "
            f"{', '.join(missing)}. Install prompt won't fire.",
            Severity.SERIOUS, WebQualityLevel.MID,
            "web/manifest.json", 0, f"missing: {', '.join(missing)}",
            "Add the missing fields; see web.dev PWA install criteria.",
            "web.dev PWA install criteria",
        ))

    # Mid: manifest_no_maskable_icon
    icons = manifest.get("icons")
    if isinstance(icons, list) and icons:
        has_maskable = any(
            isinstance(i, dict) and "maskable" in str(i.get("purpose", ""))
            for i in icons
        )
        if not has_maskable:
            out.append(_mk(
                "manifest_no_maskable_icon",
                "manifest icons present but none has purpose:maskable. "
                "Android shows your icon letterboxed in a white circle.",
                Severity.MINOR, WebQualityLevel.MID,
                "web/manifest.json", 0, "no maskable icon",
                'Add an icon entry with `"purpose": "maskable"` (a '
                "192/512 PNG with safe-zone padding).",
                "Android adaptive icons",
            ))

    # Senior: placeholder_app_name
    name = str(manifest.get("name", ""))
    if (
        "flutter project" in name.lower()
        or name.strip() in ("", "app", "my_app")
    ):
        out.append(_mk(
            "placeholder_app_name",
            f"manifest name {name!r} looks like the scaffold default. "
            "This is the PWA install title + home-screen label.",
            Severity.SERIOUS, WebQualityLevel.SENIOR,
            "web/manifest.json", 0, f'"name": {name!r}',
            "Set name + short_name to the real product name.",
            "PWA metadata",
        ))

    return out


# ============================================================
# web/ directory scanner
# ============================================================


def _scan_web_dir(
    web_files: set[str], web_subdirs: set[str], html: str,
) -> list[WebAppFinding]:
    out: list[WebAppFinding] = []

    # Junior: no_favicon
    has_favicon = (
        any(f.startswith("favicon") for f in web_files)
        or "favicon" in html.lower()
    )
    if not has_favicon:
        out.append(_mk(
            "no_favicon",
            "No favicon in web/. Browser tabs show a blank document icon.",
            Severity.MINOR, WebQualityLevel.JUNIOR,
            "web/", 0, "no favicon file",
            "Add a favicon.png (and favicon.svg for crisp scaling) to "
            "web/ and reference it in index.html.",
            "Web basics",
        ))

    # Staff: no_loading_indicator
    has_loading = (
        bool(_RE_LOADING.search(html))
        or "splash" in web_subdirs
        or any("splash" in f or "loading" in f for f in web_files)
    )
    if not has_loading:
        out.append(_mk(
            "no_loading_indicator",
            "No splash / loading element before Flutter boots. Users see "
            "a blank white page during the CanvasKit / wasm download "
            "(can be 1-3s on cold load).",
            Severity.MINOR, WebQualityLevel.STAFF,
            "web/index.html", 0, "no loading indicator",
            "Add a `<div id=\"loading\">` with a spinner that Flutter "
            "removes on first frame, or a web/splash/ asset set.",
            "Flutter web: avoiding the blank-screen-of-load",
        ))

    return out


# ============================================================
# Helpers
# ============================================================


def _has_csp(html: str, headers_text: str) -> bool:
    if _RE_CSP_META.search(html):
        return True
    # _headers file (Cloudflare Pages / Netlify): a line with
    # "Content-Security-Policy:"
    return bool(
        re.search(r"Content-Security-Policy\s*:", headers_text, re.IGNORECASE)
    )


def _manifest_has_all_required(manifest: dict | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    return all(manifest.get(f) for f in _REQUIRED_MANIFEST_FIELDS)


def _mk(
    rule: str, desc: str, severity: Severity, level: WebQualityLevel,
    file: str, line: int, snippet: str,
    fix_hint: str | None, standard: str | None,
) -> WebAppFinding:
    return WebAppFinding(
        rule=rule, description=desc, severity=severity, level=level,
        file=file, line=line, snippet=snippet[:140],
        fix_hint=fix_hint, standard=standard,
    )


def _not_web_app_result() -> AuditWebAppResult:
    return AuditWebAppResult(
        grade="not_web_app",
        score=0.0,
        has_index_html=False,
        has_manifest=False,
        has_csp=False,
        has_pwa_manifest=False,
        locales_hint=None,
        findings=(),
        findings_by_level={},
        findings_by_severity={},
        top_actions=(
            "No web/index.html found — this project doesn't target "
            "Flutter web (or web/ is at a non-standard path; pass "
            "web_dir to override).",
        ),
        advice=(
            "Project has no Flutter web target. If it should, run "
            "`flutter create --platforms web .` then re-run this audit."
        ),
    )


def _grade_for(by_sev: dict[str, int], n: int) -> str:
    if n == 0:
        return "excellent"
    if by_sev.get("blocker", 0) > 0:
        return "not_production_ready"
    if by_sev.get("serious", 0) >= 3:
        return "not_production_ready"
    if by_sev.get("serious", 0) > 0:
        return "needs_polish"
    return "acceptable"


def _build_top_actions(
    findings: tuple[WebAppFinding, ...],
) -> tuple[str, ...]:
    if not findings:
        return (
            "Web app passes the production-readiness checks. Ship-ready.",
        )
    ranked = sorted(
        findings,
        key=lambda f: -_SEVERITY_WEIGHT[f.severity],
    )
    out: list[str] = []
    for f in ranked[:5]:
        hint = f.fix_hint or "see rule definition"
        out.append(f"[{f.severity.value}] {f.rule} — {hint}")
    return tuple(out)


def _build_advice(
    grade: str, has_csp: bool, has_pwa: bool, n_findings: int,
) -> str:
    bits = [f"Web-app grade: {grade}."]
    bits.append("CSP present." if has_csp else "⚠ no CSP.")
    bits.append(
        "PWA-installable." if has_pwa else "⚠ PWA manifest incomplete."
    )
    bits.append(f"{n_findings} findings.")
    if grade == "not_production_ready":
        bits.append("Resolve serious findings before deploying.")
    return " ".join(bits)
