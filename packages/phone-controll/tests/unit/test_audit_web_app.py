"""Tests for v0.5.0 phase-15 Flutter web production-readiness audit.

Each rule fires on a known-bad web/ fixture and stays silent on a
known-good one. The "good" fixture mirrors bike_news_room's web/
(CSP + full PWA manifest + SEO meta + maskable icons) — the only
finding it should produce is html_no_lang_attr, which is exactly
what the real field test surfaced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.audit_web_app import (
    AuditWebApp,
    AuditWebAppParams,
    WebQualityLevel,
)


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


GOOD_INDEX = """<!DOCTYPE html><html lang="en"><head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="A real, specific description of this app.">
  <meta name="theme-color" content="#E8C54A">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'">
  <meta property="og:title" content="My App">
  <meta property="og:description" content="Social card text.">
  <link rel="apple-touch-icon" href="icons/Icon-192.png">
  <link rel="icon" href="favicon.png">
  <title>My App</title>
</head>
<body>
  <div id="loading"><div class="spinner"></div></div>
</body></html>
"""

GOOD_MANIFEST = {
    "name": "Bike News Room",
    "short_name": "BNR",
    "start_url": ".",
    "display": "standalone",
    "theme_color": "#E8C54A",
    "lang": "en",
    "icons": [
        {"src": "icons/Icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icons/Icon-maskable-192.png", "sizes": "192x192",
         "type": "image/png", "purpose": "maskable"},
    ],
}


def _good_web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    _write(web / "index.html", GOOD_INDEX)
    _write(web / "manifest.json", json.dumps(GOOD_MANIFEST))
    _write(web / "favicon.png", "x")
    _write(web / "icons" / "Icon-192.png", "x")
    return tmp_path


async def _run(project: Path, **kwargs) -> Ok | Err:
    return await AuditWebApp()(
        AuditWebAppParams(project_path=project, **kwargs)
    )


def _rules(res: Ok) -> set[str]:
    return {f.rule for f in res.value.findings}


# ---- error handling + not-web-app --------------------------------------


@pytest.mark.asyncio
async def test_missing_project_path_returns_failure(tmp_path: Path):
    res = await _run(tmp_path / "does_not_exist")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_invalid_min_level_returns_failure(tmp_path: Path):
    (tmp_path / "web").mkdir()
    _write(tmp_path / "web" / "index.html", GOOD_INDEX)
    res = await _run(tmp_path, min_level="principal")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_no_web_dir_returns_not_web_app(tmp_path: Path):
    (tmp_path / "lib").mkdir()
    res = await _run(tmp_path)
    assert isinstance(res, Ok)
    assert res.value.grade == "not_web_app"
    assert res.value.has_index_html is False
    assert res.value.findings == ()


# ---- golden path -------------------------------------------------------


@pytest.mark.asyncio
async def test_good_web_app_only_flags_lang_attr(tmp_path: Path):
    """An exemplary web/ (mirrors bike_news_room) should produce
    exactly zero findings — GOOD_INDEX has lang='en'."""
    proj = _good_web(tmp_path)
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.findings == ()
    assert res.value.grade == "excellent"
    assert res.value.has_csp is True
    assert res.value.has_pwa_manifest is True
    assert res.value.locales_hint == "en"


@pytest.mark.asyncio
async def test_missing_lang_attr_fires(tmp_path: Path):
    """The real bike_news_room finding: <html> with no lang."""
    proj = _good_web(tmp_path)
    # Overwrite index with a bare <html> (no lang)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX.replace('<html lang="en">', "<html>"),
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "html_no_lang_attr" in _rules(res)


# ---- JUNIOR tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_no_viewport_meta_fires(tmp_path: Path):
    proj = _good_web(tmp_path)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX.replace(
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            "",
        ),
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_viewport_meta" in _rules(res)


@pytest.mark.asyncio
async def test_placeholder_description_fires(tmp_path: Path):
    proj = _good_web(tmp_path)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX.replace(
            "A real, specific description of this app.",
            "A new Flutter project.",
        ),
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "placeholder_meta_description" in _rules(res)


@pytest.mark.asyncio
async def test_no_favicon_fires(tmp_path: Path):
    web = tmp_path / "web"
    # No favicon file, and strip the favicon link from the html
    _write(
        web / "index.html",
        GOOD_INDEX.replace('<link rel="icon" href="favicon.png">', ""),
    )
    _write(web / "manifest.json", json.dumps(GOOD_MANIFEST))
    _write(web / "icons" / "Icon-192.png", "x")
    res = await _run(tmp_path)
    assert isinstance(res, Ok)
    assert "no_favicon" in _rules(res)


# ---- MID tier rules ----------------------------------------------------


@pytest.mark.asyncio
async def test_no_csp_fires(tmp_path: Path):
    proj = _good_web(tmp_path)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX.replace(
            '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'">',
            "",
        ),
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_csp" in _rules(res)


@pytest.mark.asyncio
async def test_csp_via_headers_file_silences_rule(tmp_path: Path):
    """CSP can live in a _headers file (Cloudflare Pages / Netlify)
    instead of a meta tag."""
    proj = _good_web(tmp_path)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX.replace(
            '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'">',
            "",
        ),
    )
    _write(
        proj / "web" / "_headers",
        "/*\n  Content-Security-Policy: default-src 'self'\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_csp" not in _rules(res)
    assert res.value.has_csp is True


@pytest.mark.asyncio
async def test_no_theme_color_fires(tmp_path: Path):
    proj = _good_web(tmp_path)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX.replace(
            '<meta name="theme-color" content="#E8C54A">', ""
        ),
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_theme_color" in _rules(res)


@pytest.mark.asyncio
async def test_manifest_missing_pwa_fields_fires(tmp_path: Path):
    web = tmp_path / "web"
    _write(web / "index.html", GOOD_INDEX)
    _write(web / "favicon.png", "x")
    # Manifest missing start_url + icons
    _write(web / "manifest.json", json.dumps({
        "name": "My App", "short_name": "MA", "display": "standalone",
    }))
    res = await _run(tmp_path)
    assert isinstance(res, Ok)
    assert "manifest_missing_pwa_fields" in _rules(res)


@pytest.mark.asyncio
async def test_missing_manifest_fires(tmp_path: Path):
    web = tmp_path / "web"
    _write(web / "index.html", GOOD_INDEX)
    _write(web / "favicon.png", "x")
    # No manifest.json at all
    res = await _run(tmp_path)
    assert isinstance(res, Ok)
    assert "manifest_missing_pwa_fields" in _rules(res)
    assert res.value.has_manifest is False


@pytest.mark.asyncio
async def test_manifest_no_maskable_icon_fires(tmp_path: Path):
    web = tmp_path / "web"
    _write(web / "index.html", GOOD_INDEX)
    _write(web / "favicon.png", "x")
    manifest = dict(GOOD_MANIFEST)
    manifest["icons"] = [
        {"src": "icons/Icon-192.png", "sizes": "192x192", "type": "image/png"},
    ]  # no maskable
    _write(web / "manifest.json", json.dumps(manifest))
    res = await _run(tmp_path)
    assert isinstance(res, Ok)
    assert "manifest_no_maskable_icon" in _rules(res)


# ---- SENIOR tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_placeholder_app_name_fires(tmp_path: Path):
    web = tmp_path / "web"
    _write(web / "index.html", GOOD_INDEX)
    _write(web / "favicon.png", "x")
    manifest = dict(GOOD_MANIFEST)
    manifest["name"] = "my_app"  # scaffold default-ish
    _write(web / "manifest.json", json.dumps(manifest))
    res = await _run(tmp_path)
    assert isinstance(res, Ok)
    assert "placeholder_app_name" in _rules(res)


@pytest.mark.asyncio
async def test_no_seo_meta_fires(tmp_path: Path):
    proj = _good_web(tmp_path)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX
        .replace('<meta property="og:title" content="My App">', "")
        .replace('<meta property="og:description" content="Social card text.">', ""),
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_seo_meta" in _rules(res)


@pytest.mark.asyncio
async def test_no_apple_touch_icon_fires(tmp_path: Path):
    proj = _good_web(tmp_path)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX.replace(
            '<link rel="apple-touch-icon" href="icons/Icon-192.png">', ""
        ),
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_apple_touch_icon" in _rules(res)


# ---- STAFF tier rules --------------------------------------------------


@pytest.mark.asyncio
async def test_no_loading_indicator_fires(tmp_path: Path):
    proj = _good_web(tmp_path)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX.replace(
            '<div id="loading"><div class="spinner"></div></div>', ""
        ),
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_loading_indicator" in _rules(res)


@pytest.mark.asyncio
async def test_splash_dir_silences_loading_rule(tmp_path: Path):
    """A web/splash/ directory counts as a loading indicator."""
    proj = _good_web(tmp_path)
    _write(
        proj / "web" / "index.html",
        GOOD_INDEX.replace(
            '<div id="loading"><div class="spinner"></div></div>', ""
        ),
    )
    _write(proj / "web" / "splash" / "img.png", "x")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_loading_indicator" not in _rules(res)


# ---- engine behaviors --------------------------------------------------


@pytest.mark.asyncio
async def test_min_level_filter_suppresses_lower(tmp_path: Path):
    """Strip everything → many junior/mid findings. min_level=senior
    should suppress them."""
    web = tmp_path / "web"
    _write(web / "index.html", "<!DOCTYPE html><html><head></head><body></body></html>")
    res = await _run(tmp_path, min_level="senior")
    assert isinstance(res, Ok)
    assert all(
        f.level not in (WebQualityLevel.JUNIOR, WebQualityLevel.MID)
        for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_custom_web_dir(tmp_path: Path):
    """web_dir override for non-standard layouts."""
    web = tmp_path / "frontend_web"
    _write(web / "index.html", GOOD_INDEX)
    _write(web / "manifest.json", json.dumps(GOOD_MANIFEST))
    _write(web / "favicon.png", "x")
    res = await _run(tmp_path, web_dir="frontend_web")
    assert isinstance(res, Ok)
    assert res.value.has_index_html is True
    assert res.value.grade == "excellent"


@pytest.mark.asyncio
async def test_grade_not_production_ready_with_many_serious(tmp_path: Path):
    """A bare index.html (no viewport, no csp, no manifest, no seo)
    has 3+ serious findings → not_production_ready."""
    web = tmp_path / "web"
    _write(web / "index.html", "<!DOCTYPE html><html><head></head><body></body></html>")
    res = await _run(tmp_path)
    assert isinstance(res, Ok)
    assert res.value.grade == "not_production_ready"


@pytest.mark.asyncio
async def test_advice_mentions_grade(tmp_path: Path):
    proj = _good_web(tmp_path)
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade in res.value.advice
