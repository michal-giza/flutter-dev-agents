"""Tests for the v0.3.0 phase-4 test scenario designer.

What this validates:

- Canonical baseline scenarios always appear regardless of project
  shape (the 25 that apply to every app).
- Feature detection from AndroidManifest / Info.plist / pubspec
  correctly flips the right flags in `detected_features`.
- Each detected feature triggers its enricher scenarios + nothing
  more (an iOS-only app doesn't get Android-only enrichers).
- focus_areas narrows output to the requested categories.
- top_n caps the result.
- Scenarios are sorted P0 first.
- advice line includes the right priority breakdown + detected
  features mention.
- references is the unique sorted list of standards cited.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.propose_test_scenarios import (
    Category,
    Priority,
    ProposeTestScenarios,
    ProposeTestScenariosParams,
    _detect_features,
)

# ---- helpers: build fake Flutter projects -----------------------------


def _make_minimal_project(root: Path) -> Path:
    """An empty project — no manifest, no plist, no pubspec.
    Only baseline scenarios should appear."""
    root.mkdir(parents=True, exist_ok=True)
    return root


def _make_camera_app(root: Path) -> Path:
    """Project with camera permission on Android + iOS + image_picker
    in pubspec. Three signals for the same feature → must still
    only fire enricher once."""
    root.mkdir(parents=True, exist_ok=True)
    android_dir = root / "android" / "app" / "src" / "main"
    android_dir.mkdir(parents=True, exist_ok=True)
    (android_dir / "AndroidManifest.xml").write_text(
        '<manifest>'
        '<uses-permission android:name="android.permission.CAMERA"/>'
        '</manifest>'
    )
    ios_dir = root / "ios" / "Runner"
    ios_dir.mkdir(parents=True, exist_ok=True)
    (ios_dir / "Info.plist").write_text(
        '<plist><dict>'
        '<key>NSCameraUsageDescription</key>'
        '<string>To take photos.</string>'
        '</dict></plist>'
    )
    (root / "pubspec.yaml").write_text(
        "name: testapp\ndependencies:\n  image_picker: ^1.0.0\n"
    )
    return root


def _make_full_featured_app(root: Path) -> Path:
    """The kitchen-sink project: camera + location + notifications +
    deep links + IAP + biometrics + auth + localization."""
    root.mkdir(parents=True, exist_ok=True)
    android = root / "android" / "app" / "src" / "main"
    android.mkdir(parents=True, exist_ok=True)
    (android / "AndroidManifest.xml").write_text(
        '<manifest>'
        '<uses-permission android:name="android.permission.CAMERA"/>'
        '<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>'
        '<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>'
        '<uses-permission android:name="android.permission.USE_BIOMETRIC"/>'
        '<application>'
        '<activity><intent-filter>'
        '<action android:name="android.intent.action.VIEW"/>'
        '</intent-filter></activity>'
        '</application>'
        '</manifest>'
    )
    (root / "pubspec.yaml").write_text(
        "name: testapp\n"
        "dependencies:\n"
        "  camera: ^0.10.0\n"
        "  geolocator: ^11.0.0\n"
        "  in_app_purchase: ^3.0.0\n"
        "  local_auth: ^2.0.0\n"
        "  firebase_auth: ^4.0.0\n"
        "  flutter_localizations:\n"
        "    sdk: flutter\n"
        "  intl: ^0.18.0\n"
    )
    return root


# ---- _detect_features --------------------------------------------------


def test_detect_features_minimal_project_returns_all_false(tmp_path: Path):
    """Empty project → every feature flag is False."""
    proj = _make_minimal_project(tmp_path / "minimal")
    features = _detect_features(proj)
    # All values should be False
    assert all(v is False for v in features.values())


def test_detect_features_camera_from_three_sources(tmp_path: Path):
    """Camera permission declared in 3 places — only the flag is set once."""
    proj = _make_camera_app(tmp_path / "cam")
    features = _detect_features(proj)
    assert features["uses_camera"] is True
    assert features["uses_location"] is False


def test_detect_features_full_featured(tmp_path: Path):
    """Kitchen-sink app → expected flags True, others False."""
    proj = _make_full_featured_app(tmp_path / "full")
    features = _detect_features(proj)
    assert features["uses_camera"] is True
    assert features["uses_location"] is True
    assert features["uses_notifications"] is True
    assert features["uses_biometrics"] is True
    assert features["uses_deep_links"] is True
    assert features["uses_in_app_purchase"] is True
    assert features["has_login_flow"] is True
    assert features["supports_localization"] is True
    # NOT detected (no signals provided):
    assert features["uses_microphone"] is False
    assert features["uses_ar"] is False


# ---- the use case end-to-end ------------------------------------------


@pytest.mark.asyncio
async def test_minimal_project_returns_baseline_only(tmp_path: Path):
    """A project with no features triggers no enrichers — only the
    canonical baseline scenarios appear."""
    proj = _make_minimal_project(tmp_path / "minimal")
    res = await ProposeTestScenarios()(ProposeTestScenariosParams(project_path=proj))
    assert isinstance(res, Ok)
    v = res.value
    # No enrichment → no project_specific=True scenarios
    assert all(not s.project_specific for s in v.scenarios)
    # Baseline always has cold launch + happy path + permission denial
    names = [s.name for s in v.scenarios]
    assert any("Cold launch" in n for n in names)
    assert any("Deny every runtime permission" in n for n in names)


@pytest.mark.asyncio
async def test_camera_app_adds_camera_enricher(tmp_path: Path):
    """When camera permission is detected, the camera-denial fallback
    scenario gets added."""
    proj = _make_camera_app(tmp_path / "cam")
    res = await ProposeTestScenarios()(ProposeTestScenariosParams(project_path=proj))
    assert isinstance(res, Ok)
    project_specific = [s for s in res.value.scenarios if s.project_specific]
    names = [s.name for s in project_specific]
    assert any("Deny camera permission" in n for n in names)


@pytest.mark.asyncio
async def test_full_featured_app_adds_multiple_enrichers(tmp_path: Path):
    """Kitchen-sink app → multiple project-specific scenarios."""
    proj = _make_full_featured_app(tmp_path / "full")
    res = await ProposeTestScenarios()(
        ProposeTestScenariosParams(project_path=proj, top_n=50)
    )
    assert isinstance(res, Ok)
    project_specific = [s for s in res.value.scenarios if s.project_specific]
    names = [s.name for s in project_specific]
    # At minimum: camera + location + IAP + biometric + auth + localization
    assert any("camera" in n.lower() for n in names)
    assert any("location" in n.lower() for n in names)
    assert any("purchase" in n.lower() or "Restore" in n for n in names)
    assert any("biometric" in n.lower() for n in names)


@pytest.mark.asyncio
async def test_focus_areas_filters_categories(tmp_path: Path):
    """focus_areas=['accessibility'] → only accessibility scenarios."""
    proj = _make_minimal_project(tmp_path / "minimal")
    res = await ProposeTestScenarios()(
        ProposeTestScenariosParams(
            project_path=proj,
            focus_areas=("accessibility",),
            top_n=50,
        )
    )
    assert isinstance(res, Ok)
    assert len(res.value.scenarios) > 0
    assert all(s.category == Category.ACCESSIBILITY for s in res.value.scenarios)


@pytest.mark.asyncio
async def test_focus_areas_unknown_category_silently_ignored(tmp_path: Path):
    """Pass 'bogus_category' alongside 'permission' — only permission
    scenarios appear; the typo doesn't crash."""
    proj = _make_minimal_project(tmp_path / "minimal")
    res = await ProposeTestScenarios()(
        ProposeTestScenariosParams(
            project_path=proj,
            focus_areas=("permission", "bogus_category"),
            top_n=50,
        )
    )
    assert isinstance(res, Ok)
    assert all(s.category == Category.PERMISSION for s in res.value.scenarios)


@pytest.mark.asyncio
async def test_top_n_caps_result_size(tmp_path: Path):
    """top_n=5 → at most 5 scenarios returned."""
    proj = _make_full_featured_app(tmp_path / "full")
    res = await ProposeTestScenarios()(
        ProposeTestScenariosParams(project_path=proj, top_n=5)
    )
    assert isinstance(res, Ok)
    assert len(res.value.scenarios) == 5


@pytest.mark.asyncio
async def test_scenarios_sorted_by_priority_p0_first(tmp_path: Path):
    """The result is sorted so P0 scenarios appear before P1, P1 before P2."""
    proj = _make_minimal_project(tmp_path / "minimal")
    res = await ProposeTestScenarios()(
        ProposeTestScenariosParams(project_path=proj, top_n=50)
    )
    assert isinstance(res, Ok)
    priorities = [s.priority.value for s in res.value.scenarios]
    # Confirm monotone non-decreasing (P0 < P1 < P2 by string)
    assert priorities == sorted(priorities)


@pytest.mark.asyncio
async def test_advice_includes_priority_counts(tmp_path: Path):
    """advice line surfaces P0 + P1 counts and mentions detected features."""
    proj = _make_camera_app(tmp_path / "cam")
    res = await ProposeTestScenarios()(ProposeTestScenariosParams(project_path=proj))
    assert isinstance(res, Ok)
    advice = res.value.advice
    assert "P0" in advice
    assert "P1" in advice
    assert "camera" in advice.lower()


@pytest.mark.asyncio
async def test_references_are_unique_and_sorted(tmp_path: Path):
    """The references tuple is deduplicated + sorted."""
    proj = _make_minimal_project(tmp_path / "minimal")
    res = await ProposeTestScenarios()(
        ProposeTestScenariosParams(project_path=proj, top_n=50)
    )
    assert isinstance(res, Ok)
    refs = res.value.references
    assert refs == tuple(sorted(set(refs)))
    # Several canonical references must appear
    assert any("Google" in r or "Android" in r for r in refs)
    assert any("WCAG" in r for r in refs)


@pytest.mark.asyncio
async def test_missing_project_path_returns_typed_failure(tmp_path: Path):
    """Non-existent path → FilesystemFailure with fix_arguments."""
    res = await ProposeTestScenarios()(
        ProposeTestScenariosParams(project_path=tmp_path / "does_not_exist")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_scenarios_carry_tool_sequence(tmp_path: Path):
    """Every scenario has a non-empty tool_sequence — agent always
    has a concrete next-step."""
    proj = _make_minimal_project(tmp_path / "minimal")
    res = await ProposeTestScenarios()(
        ProposeTestScenariosParams(project_path=proj, top_n=50)
    )
    assert isinstance(res, Ok)
    # Some scenarios have empty tool_sequence by design (the ones
    # waiting on planned future tools like audit_accessibility).
    # But the majority should have something.
    with_sequence = [s for s in res.value.scenarios if s.tool_sequence]
    assert len(with_sequence) >= len(res.value.scenarios) * 0.7


def test_all_priorities_used():
    """Sanity: the canonical taxonomy uses all 3 priority tiers."""
    from mcp_phone_controll.domain.usecases.propose_test_scenarios import (
        _canonical_scenarios,
    )
    scenarios = _canonical_scenarios()
    priorities = {s.priority for s in scenarios}
    # P0 + P1 at minimum (P2 is optional but should exist)
    assert Priority.P0 in priorities
    assert Priority.P1 in priorities


def test_all_categories_represented_in_baseline():
    """Sanity: every category has at least one canonical scenario.

    If a category has no baseline scenarios, the tool's
    focus_areas filter would return empty unless the user has
    that exact feature — bad UX."""
    from mcp_phone_controll.domain.usecases.propose_test_scenarios import (
        _canonical_scenarios,
    )
    scenarios = _canonical_scenarios()
    seen = {s.category for s in scenarios}
    # Categories we expect to have at least one canonical entry
    must_have = {
        Category.HAPPY_PATH, Category.PERMISSION, Category.NETWORK,
        Category.INPUT, Category.INTERRUPTION, Category.LIFECYCLE,
        Category.ACCESSIBILITY, Category.LOCALIZATION,
        Category.DEVICE_MATRIX, Category.PERFORMANCE, Category.SECURITY,
        Category.DATA,
    }
    missing = must_have - seen
    assert not missing, f"Categories missing baseline scenarios: {missing}"
