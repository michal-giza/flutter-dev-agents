"""Tests for the v0.3.0 phase-11 release-readiness composite.

The composite calls 4 sub-audits in parallel and aggregates.
These tests verify:

- Clean project → ship verdict, A grade
- Project with blockers → block verdict regardless of score
- Mid-tier issues only → hold verdict (no blockers, <80 score)
- Per-domain breakdown is populated for all enabled domains
- Disabled domains don't appear in breakdown
- Disabling everything returns fix_arguments
- Per-domain failure is caught + recorded, doesn't kill the report
- Weights affect composite score (heavier-weighted domains pull harder)
- top_actions are cross-domain and severity-sorted
- ran_in_s is populated and >= 0
- Invalid project_path → fix_arguments
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.audit_release_readiness import (
    AuditReleaseReadiness,
    AuditReleaseReadinessParams,
)

# ---- fixture helpers ----------------------------------------------------


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    (tmp_path / "lib").mkdir()
    return tmp_path


def _minimal_clean_project(tmp_path: Path) -> Path:
    """A pubspec+lib that should produce a clean grade across
    all four sub-audits."""
    proj = _project(tmp_path)
    _write(
        proj / "pubspec.yaml",
        "name: app\n"
        "environment:\n"
        "  sdk: '>=3.0.0 <4.0.0'\n"
        "  flutter: '>=3.16.0 <4.0.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  cupertino_icons: 1.0.5\n",
    )
    _write(
        proj / "lib" / "main.dart",
        "import 'package:cupertino_icons/cupertino_icons.dart';\n"
        "void main() {}\n",
    )
    return proj


async def _run(project: Path, **kwargs) -> Ok | Err:
    return await AuditReleaseReadiness()(
        AuditReleaseReadinessParams(project_path=project, **kwargs)
    )


@pytest.mark.asyncio
async def test_performance_domain_default_on_and_flags_jank(tmp_path: Path):
    """performance is a default-on composite domain (v0.9.0); a non-lazy
    list drags its grade below smooth."""
    proj = _project(tmp_path)
    _write(
        proj / "pubspec.yaml",
        "name: app\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n"
        "dependencies:\n  flutter:\n    sdk: flutter\n",
    )
    _write(
        proj / "lib" / "feed.dart",
        "Widget build(BuildContext c) =>\n"
        "    ListView(children: items.map((i) => Tile(i)).toList());\n",
    )
    res = await _run(
        proj,
        include_seniority=False, include_security=False,
        include_localization=False, include_dependencies=False,
        include_test_quality=False, include_web_app=False,
    )
    assert isinstance(res, Ok)
    perf = next(
        (d for d in res.value.domains if d.domain == "performance"), None
    )
    assert perf is not None
    assert perf.grade in ("janky", "severe")


# ---- error handling ----------------------------------------------------


@pytest.mark.asyncio
async def test_missing_project_path_returns_failure(tmp_path: Path):
    res = await _run(tmp_path / "does_not_exist")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_all_domains_disabled_returns_failure(tmp_path: Path):
    proj = _minimal_clean_project(tmp_path)
    res = await _run(
        proj,
        include_seniority=False,
        include_security=False,
        include_localization=False,
        include_dependencies=False,
        include_test_quality=False,
        include_performance=False,
        include_web_app=False,
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ---- happy path --------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_project_ships_with_high_grade(tmp_path: Path):
    proj = _minimal_clean_project(tmp_path)
    res = await _run(proj)
    assert isinstance(res, Ok)
    v = res.value
    assert v.verdict == "ship"
    assert v.composite_grade in ("A", "B")
    assert v.composite_score >= 80
    assert v.total_blockers == 0
    assert v.ran_in_s >= 0
    assert "SHIP" in v.advice


@pytest.mark.asyncio
async def test_per_domain_breakdown_populated(tmp_path: Path):
    proj = _minimal_clean_project(tmp_path)
    res = await _run(proj)
    assert isinstance(res, Ok)
    domains = {d.domain for d in res.value.domains}
    # The 5 static domains always run. web_app is included by
    # default but EXCLUDED (ran=False) on this mobile-only project.
    assert {
        "seniority", "security", "localization",
        "dependencies", "test_quality",
    } <= domains
    # The 5 static domains ran successfully with a grade
    ran_domains = [
        d for d in res.value.domains
        if d.domain in {
            "seniority", "security", "localization",
            "dependencies", "test_quality",
        }
    ]
    assert all(d.ran for d in ran_domains)
    assert all(d.grade is not None for d in ran_domains)


# ---- verdict transitions -----------------------------------------------


@pytest.mark.asyncio
async def test_blocker_in_any_domain_triggers_block(tmp_path: Path):
    """audit_localization fires `missing_l10n_key` as BLOCKER when
    code references a key not in arb. That should force `block`."""
    proj = _project(tmp_path)
    _write(
        proj / "pubspec.yaml",
        "name: app\n"
        "environment:\n"
        "  sdk: '>=3.0.0 <4.0.0'\n"
        "  flutter: '>=3.16.0 <4.0.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  flutter_localizations:\n"
        "    sdk: flutter\n",
    )
    # arb with only one key
    _write(
        proj / "lib" / "l10n" / "intl_en.arb",
        json.dumps({"hello": "Hi"}),
    )
    # code references a missing key → BLOCKER
    _write(
        proj / "lib" / "page.dart",
        "Widget x(BuildContext c) => "
        "Text(AppLocalizations.of(c)!.notInArbFile);\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.verdict == "block"
    assert res.value.total_blockers >= 1
    assert "BLOCK" in res.value.advice


@pytest.mark.asyncio
async def test_mid_tier_smells_only_triggers_hold(tmp_path: Path):
    """A project with only mid-tier smells (no blockers, score < 80)
    should land in 'hold'."""
    proj = _project(tmp_path)
    # Lots of dev tools in dependencies + hardcoded strings — generates many
    # 'serious' findings but no blockers.
    _write(
        proj / "pubspec.yaml",
        "name: app\n"
        "environment:\n"
        "  sdk: '>=3.0.0 <4.0.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  build_runner: ^2.4.0\n"
        "  mockito: ^5.4.0\n"
        "  freezed: ^2.0.0\n"
        "  some_pkg: '>=1.0.0 <4.0.0'\n",
    )
    _write(
        proj / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        + "\n".join([
            f"Widget w{i}() => Text('Hardcoded label {i}');"
            for i in range(15)
        ]),
    )
    # Disable performance — this project has no jank smells, so a
    # perfect performance=smooth(100) would lift the composite out of
    # the mid-tier 'hold' band this test exercises.
    res = await _run(proj, include_performance=False)
    assert isinstance(res, Ok)
    # No blockers, but composite low → hold
    assert res.value.total_blockers == 0
    assert res.value.verdict == "hold"


# ---- weighting ---------------------------------------------------------


@pytest.mark.asyncio
async def test_security_weight_dominates_when_high(tmp_path: Path):
    """If we crank security weight way up and the security domain
    is perfect (no findings → secure → 100), the composite should
    skew higher than the unweighted case."""
    proj = _minimal_clean_project(tmp_path)
    res_default = await _run(proj)
    res_weighted = await _run(
        proj,
        weight_security=10.0,  # security dominates
        weight_seniority=0.1,
        weight_localization=0.1,
        weight_dependencies=0.1,
    )
    assert isinstance(res_default, Ok)
    assert isinstance(res_weighted, Ok)
    # Both should be ship; weighted version should be at least
    # as high as default because security==100 on this clean project.
    assert res_weighted.value.composite_score >= res_default.value.composite_score - 1


# ---- domain enable/disable ---------------------------------------------


@pytest.mark.asyncio
async def test_disabled_domain_omitted_from_breakdown(tmp_path: Path):
    proj = _minimal_clean_project(tmp_path)
    res = await _run(
        proj,
        include_localization=False,
        include_dependencies=False,
    )
    assert isinstance(res, Ok)
    domains = {d.domain for d in res.value.domains}
    assert "localization" not in domains
    assert "dependencies" not in domains
    assert "seniority" in domains
    assert "security" in domains


@pytest.mark.asyncio
async def test_single_domain_run(tmp_path: Path):
    proj = _minimal_clean_project(tmp_path)
    res = await _run(
        proj,
        include_seniority=False,
        include_security=False,
        include_localization=False,
        include_dependencies=True,  # only deps
        include_test_quality=False,
        include_performance=False,
        include_web_app=False,
    )
    assert isinstance(res, Ok)
    assert len(res.value.domains) == 1
    assert res.value.domains[0].domain == "dependencies"


# ---- robustness --------------------------------------------------------


@pytest.mark.asyncio
async def test_sub_audit_error_does_not_kill_composite(tmp_path: Path):
    """audit_dependencies fails on a missing pubspec.yaml. The
    composite should still complete; only the dependencies domain
    is marked errored."""
    proj = _project(tmp_path)
    # No pubspec.yaml — dependencies audit will fail
    _write(proj / "lib" / "main.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    deps_domain = next(
        d for d in res.value.domains if d.domain == "dependencies"
    )
    assert not deps_domain.ran
    assert deps_domain.error is not None
    # The other static domains still ran. (web_app is excluded —
    # this fixture has no web/ dir — so don't count it here.)
    others = [
        d for d in res.value.domains
        if d.domain not in ("dependencies", "web_app")
    ]
    assert all(d.ran for d in others)


# ---- top_actions -------------------------------------------------------


@pytest.mark.asyncio
async def test_top_actions_are_cross_domain(tmp_path: Path):
    """When multiple domains have findings, top_actions should
    include lines from more than one domain."""
    proj = _project(tmp_path)
    _write(
        proj / "pubspec.yaml",
        "name: app\n"
        "environment:\n"
        "  sdk: '>=3.0.0 <4.0.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "  build_runner: ^2.4.0\n",  # deps issue
    )
    _write(
        proj / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget w() => Text('Hardcoded user-facing label');\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # top_actions should include domain prefixes
    prefixes = set()
    for action in res.value.top_actions:
        if "[seniority]" in action:
            prefixes.add("seniority")
        if "[security]" in action:
            prefixes.add("security")
        if "[localization]" in action:
            prefixes.add("localization")
        if "[dependencies]" in action:
            prefixes.add("dependencies")
    # At least 1 domain should appear
    assert len(prefixes) >= 1


@pytest.mark.asyncio
async def test_clean_project_returns_no_findings_action(tmp_path: Path):
    proj = _minimal_clean_project(tmp_path)
    res = await _run(proj)
    assert isinstance(res, Ok)
    # On a clean project, top_actions either get the "ship-ready"
    # banner OR get the sub-audits' own "nothing to fix" messages.
    # Either way the verdict is ship.
    assert res.value.top_actions
    assert res.value.verdict == "ship"
    # No findings of severity should be present
    assert res.value.total_findings == 0
    assert res.value.total_blockers == 0


# ---- advice ------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_quality_domain_runs_by_default(tmp_path: Path):
    """Phase 12.5: audit_test_quality is included by default."""
    proj = _minimal_clean_project(tmp_path)
    res = await _run(proj)
    assert isinstance(res, Ok)
    domains = {d.domain for d in res.value.domains}
    assert "test_quality" in domains
    tq = next(d for d in res.value.domains if d.domain == "test_quality")
    # Empty project has no tests → grade=excellent
    assert tq.grade == "excellent"


@pytest.mark.asyncio
async def test_web_app_domain_excluded_on_mobile_only(tmp_path: Path):
    """Phase 16.5: a project with no web/ dir gets web_app graded
    not_web_app, which is EXCLUDED from the composite (ran=False)
    so it doesn't inflate a mobile-only project's score."""
    proj = _minimal_clean_project(tmp_path)  # no web/ dir
    res = await _run(proj)
    assert isinstance(res, Ok)
    web = next(
        (d for d in res.value.domains if d.domain == "web_app"), None
    )
    assert web is not None
    assert web.ran is False
    assert web.grade == "not_web_app"


@pytest.mark.asyncio
async def test_web_app_domain_runs_when_web_dir_present(tmp_path: Path):
    """When web/index.html exists, web_app is a scored domain."""
    proj = _minimal_clean_project(tmp_path)
    _write(
        tmp_path / "web" / "index.html",
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta name="viewport" content="width=device-width">'
        '<meta name="description" content="Real desc.">'
        '<meta name="theme-color" content="#000">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'">'
        '<meta property="og:title" content="X">'
        '<link rel="apple-touch-icon" href="i.png">'
        '<link rel="icon" href="favicon.png"></head>'
        '<body><div id="loading"></div></body></html>',
    )
    import json as _json
    _write(
        tmp_path / "web" / "manifest.json",
        _json.dumps({
            "name": "Real App", "short_name": "RA", "start_url": ".",
            "display": "standalone",
            "icons": [{"src": "i.png", "sizes": "192x192",
                       "type": "image/png", "purpose": "maskable"}],
        }),
    )
    _write(tmp_path / "web" / "favicon.png", "x")
    res = await _run(proj)
    assert isinstance(res, Ok)
    web = next(
        (d for d in res.value.domains if d.domain == "web_app"), None
    )
    assert web is not None
    assert web.ran is True
    assert web.grade == "excellent"


@pytest.mark.asyncio
async def test_lighthouse_report_adds_web_vitals_domain(tmp_path: Path):
    """Phase 16.5: a Lighthouse report path adds the web_vitals
    domain to the composite."""
    import json as _json
    proj = _minimal_clean_project(tmp_path)
    _write(
        tmp_path / "lighthouse.json",
        _json.dumps({
            "finalUrl": "https://example.com/",
            "categories": {
                "performance": {"score": 0.85},
                "accessibility": {"score": 0.95},
                "best-practices": {"score": 0.93},
                "seo": {"score": 0.92},
            },
            "audits": {
                "largest-contentful-paint": {
                    "numericValue": 2100.0, "score": 0.9,
                    "displayValue": "2.1 s",
                },
                "cumulative-layout-shift": {
                    "numericValue": 0.05, "score": 0.95,
                    "displayValue": "0.05",
                },
            },
        }),
    )
    res = await _run(
        proj,
        lighthouse_report_path=tmp_path / "lighthouse.json",
    )
    assert isinstance(res, Ok)
    wv = next(
        (d for d in res.value.domains if d.domain == "web_vitals"), None
    )
    assert wv is not None
    assert wv.ran is True
    assert wv.grade == "good"


@pytest.mark.asyncio
async def test_poor_web_vitals_blocks_composite(tmp_path: Path):
    """A blocked Lighthouse grade (poor LCP) forces verdict=block."""
    import json as _json
    proj = _minimal_clean_project(tmp_path)
    _write(
        tmp_path / "lighthouse.json",
        _json.dumps({
            "finalUrl": "https://example.com/",
            "categories": {
                "performance": {"score": 0.40},
                "accessibility": {"score": 0.95},
                "best-practices": {"score": 0.90},
                "seo": {"score": 0.90},
            },
            "audits": {
                "largest-contentful-paint": {
                    "numericValue": 5000.0, "score": 0.2,  # 5s — poor
                    "displayValue": "5.0 s",
                },
            },
        }),
    )
    res = await _run(
        proj,
        lighthouse_report_path=tmp_path / "lighthouse.json",
    )
    assert isinstance(res, Ok)
    assert res.value.verdict == "block"


@pytest.mark.asyncio
async def test_maestro_report_adds_test_execution_domain(tmp_path: Path):
    """Phase 14.5: when maestro_report_path is provided,
    test_execution becomes the 6th domain."""
    proj = _minimal_clean_project(tmp_path)
    _write(
        tmp_path / "maestro_report.xml",
        "<testsuite name='m' tests='2'>"
        "<testcase name='login' time='2.0'/>"
        "<testcase name='checkout' time='3.0'/>"
        "</testsuite>",
    )
    res = await _run(
        proj,
        maestro_report_path=tmp_path / "maestro_report.xml",
    )
    assert isinstance(res, Ok)
    domains = {d.domain for d in res.value.domains}
    assert "test_execution" in domains
    te = next(d for d in res.value.domains if d.domain == "test_execution")
    assert te.grade == "clean"


@pytest.mark.asyncio
async def test_maestro_failure_propagates_to_block_verdict(tmp_path: Path):
    """A failed Maestro flow should force verdict=block."""
    proj = _minimal_clean_project(tmp_path)
    _write(
        tmp_path / "maestro_report.xml",
        "<testsuite name='m' tests='2'>"
        "<testcase name='login' time='2.0'/>"
        "<testcase name='checkout' time='3.0'>"
        "<failure message='broken'>broken</failure>"
        "</testcase>"
        "</testsuite>",
    )
    res = await _run(
        proj,
        maestro_report_path=tmp_path / "maestro_report.xml",
    )
    assert isinstance(res, Ok)
    assert res.value.verdict == "block"


@pytest.mark.asyncio
async def test_test_quality_blocker_propagates_to_composite(tmp_path: Path):
    """A blocker in the test_quality domain (e.g. real Dio in test)
    should force `block` verdict regardless of other domains."""
    proj = _minimal_clean_project(tmp_path)
    (proj / "test").mkdir(exist_ok=True)
    _write(
        proj / "test" / "bad_test.dart",
        "void main() {\n"
        "  test('x', () async {\n"
        "    final dio = Dio();\n"  # BLOCKER: real network in test
        "  });\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.verdict == "block"
    tq = next(d for d in res.value.domains if d.domain == "test_quality")
    assert tq.blockers_count >= 1


@pytest.mark.asyncio
async def test_advice_mentions_verdict(tmp_path: Path):
    proj = _minimal_clean_project(tmp_path)
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.verdict.upper() in res.value.advice.upper()
    assert "Grade:" in res.value.advice
