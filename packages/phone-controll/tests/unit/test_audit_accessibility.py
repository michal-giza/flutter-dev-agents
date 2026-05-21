"""Tests for the v0.3.0 phase-5 accessibility audit.

Hermetic — fakes the UiRepository to return canned uiautomator2
XML dumps. The dump_ui XML format is well-documented and stable
enough that synthetic fixtures are reliable.

Coverage:

- Tap-target-too-small check fires for clickable elements below 48 px.
- Missing-label check fires for clickable elements with no text /
  no content-desc.
- Disabled-but-clickable check fires for the explicit
  enabled='false' case.
- Non-clickable elements aren't flagged for tap-size or labels
  (the rules only apply to interactive ones).
- ignore_class_substrings excludes the right elements.
- Findings sorted blocker → serious → minor.
- Advice line summarizes counts + verdict tier.
- All-clean case produces the ✓ advice.
"""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.result import Ok, ok
from mcp_phone_controll.domain.usecases.audit_accessibility import (
    AuditAccessibility,
    AuditAccessibilityParams,
    Severity,
    _build_advice,
    _parse_ui_elements,
)

# ---- fakes ------------------------------------------------------------


class _FakeUiRepo:
    def __init__(self, xml: str):
        self.xml = xml

    async def dump_ui(self, serial: str):
        return ok(self.xml)


class _FakeStateRepo:
    async def get_selected_serial(self):
        return ok("emulator-5554")


class _FakeDeviceRepo:  # pragma: no cover (unused by audit)
    pass


# ---- _parse_ui_elements -----------------------------------------------


def test_parse_basic_node():
    xml = (
        '<node class="android.widget.Button" text="Sign in" '
        'clickable="true" enabled="true" bounds="[10,20][210,120]"/>'
    )
    els = _parse_ui_elements(xml)
    assert len(els) == 1
    e = els[0]
    assert e.class_name == "android.widget.Button"
    assert e.text == "Sign in"
    assert e.clickable is True
    assert e.enabled is True
    assert e.bounds is not None
    assert e.bounds.width == 200
    assert e.bounds.height == 100


def test_parse_zero_bounds_returns_none():
    """Zero-area bounds → bounds field is None (filtered out)."""
    xml = '<node class="X" clickable="true" bounds="[0,0][0,0]"/>'
    els = _parse_ui_elements(xml)
    assert els[0].bounds is None


def test_parse_multiple_nodes_in_order():
    xml = (
        '<node class="A" clickable="true" bounds="[0,0][50,50]"/>'
        '<node class="B" clickable="true" bounds="[100,0][150,50]"/>'
    )
    els = _parse_ui_elements(xml)
    assert [e.class_name for e in els] == ["A", "B"]


# ---- audit_accessibility end-to-end -----------------------------------


@pytest.mark.asyncio
async def test_tap_target_too_small_fires_for_small_clickable():
    """A clickable element below the 48 px threshold → serious finding."""
    xml = (
        '<node class="android.widget.IconButton" text="X" '
        'clickable="true" enabled="true" bounds="[100,100][120,120]"/>'
        # 20x20 px — well below the 48 minimum
    )
    uc = AuditAccessibility(
        devices=_FakeDeviceRepo(), ui=_FakeUiRepo(xml), state=_FakeStateRepo()
    )
    res = await uc(AuditAccessibilityParams())
    assert isinstance(res, Ok)
    findings = res.value.findings
    rules = [f.rule for f in findings]
    assert "tap_target_too_small" in rules
    tap_finding = next(f for f in findings if f.rule == "tap_target_too_small")
    assert tap_finding.severity == Severity.SERIOUS
    assert "WCAG 2.2 SC 2.5.5" in tap_finding.standard
    assert tap_finding.fix_hint is not None


@pytest.mark.asyncio
async def test_tap_target_size_ignored_for_non_clickable():
    """A 20×20 px element that's NOT clickable doesn't get flagged —
    you don't need a 48 dp text label, only interactive elements."""
    xml = (
        '<node class="android.widget.TextView" text="Header" '
        'clickable="false" enabled="true" bounds="[0,0][20,20]"/>'
    )
    uc = AuditAccessibility(
        devices=_FakeDeviceRepo(), ui=_FakeUiRepo(xml), state=_FakeStateRepo()
    )
    res = await uc(AuditAccessibilityParams())
    assert isinstance(res, Ok)
    assert all(f.rule != "tap_target_too_small" for f in res.value.findings)


@pytest.mark.asyncio
async def test_missing_label_fires_for_clickable_with_no_text_or_desc():
    """Clickable button with no text + no content-desc → blocker."""
    xml = (
        '<node class="android.widget.ImageButton" text="" content-desc="" '
        'clickable="true" enabled="true" bounds="[0,0][100,100]"/>'
    )
    uc = AuditAccessibility(
        devices=_FakeDeviceRepo(), ui=_FakeUiRepo(xml), state=_FakeStateRepo()
    )
    res = await uc(AuditAccessibilityParams())
    assert isinstance(res, Ok)
    findings = res.value.findings
    rules = [f.rule for f in findings]
    assert "missing_accessible_label" in rules
    label_finding = next(
        f for f in findings if f.rule == "missing_accessible_label"
    )
    assert label_finding.severity == Severity.BLOCKER
    assert "WCAG 2.2 SC 4.1.2" in label_finding.standard


@pytest.mark.asyncio
async def test_missing_label_NOT_flagged_when_content_desc_present():
    """A button with content-desc but no visible text is fine —
    that's exactly the IconButton tooltip pattern."""
    xml = (
        '<node class="android.widget.ImageButton" text="" '
        'content-desc="Sign in" '
        'clickable="true" enabled="true" bounds="[0,0][100,100]"/>'
    )
    uc = AuditAccessibility(
        devices=_FakeDeviceRepo(), ui=_FakeUiRepo(xml), state=_FakeStateRepo()
    )
    res = await uc(AuditAccessibilityParams())
    assert isinstance(res, Ok)
    rules = [f.rule for f in res.value.findings]
    assert "missing_accessible_label" not in rules


@pytest.mark.asyncio
async def test_disabled_clickable_fires_minor_finding():
    """clickable=true + enabled=false → minor finding (mixed signal)."""
    xml = (
        '<node class="android.widget.Button" text="Submit" '
        'clickable="true" enabled="false" bounds="[0,0][100,100]"/>'
    )
    uc = AuditAccessibility(
        devices=_FakeDeviceRepo(), ui=_FakeUiRepo(xml), state=_FakeStateRepo()
    )
    res = await uc(AuditAccessibilityParams())
    assert isinstance(res, Ok)
    rules = [f.rule for f in res.value.findings]
    assert "disabled_interactive_unmarked" in rules
    finding = next(
        f for f in res.value.findings
        if f.rule == "disabled_interactive_unmarked"
    )
    assert finding.severity == Severity.MINOR


@pytest.mark.asyncio
async def test_ignore_class_substrings_skips_decorative_widgets():
    """Pass `ignore_class_substrings` to exclude Divider, Padding, etc.
    Even with tap-size violations, they shouldn't fire."""
    xml = (
        '<node class="android.widget.Divider" '
        'clickable="true" enabled="true" bounds="[0,0][20,20]"/>'
        # Plus a real button so we have something to compare against
        '<node class="android.widget.Button" text="OK" '
        'clickable="true" enabled="true" bounds="[100,100][120,120]"/>'
    )
    uc = AuditAccessibility(
        devices=_FakeDeviceRepo(), ui=_FakeUiRepo(xml), state=_FakeStateRepo()
    )
    # Use default ignore list (includes 'Divider')
    res = await uc(AuditAccessibilityParams())
    assert isinstance(res, Ok)
    # Should have findings for the Button only — Divider gets skipped.
    button_findings = [
        f for f in res.value.findings
        if f.element_class and "Button" in f.element_class
    ]
    divider_findings = [
        f for f in res.value.findings
        if f.element_class and "Divider" in f.element_class
    ]
    assert button_findings
    assert not divider_findings


@pytest.mark.asyncio
async def test_findings_sorted_by_severity():
    """Multiple findings → blocker first, then serious, then minor."""
    xml = (
        # Disabled clickable — minor
        '<node class="android.widget.Button" text="A" '
        'clickable="true" enabled="false" bounds="[0,0][100,100]"/>'
        # Missing label — blocker
        '<node class="android.widget.ImageButton" '
        'clickable="true" enabled="true" bounds="[110,0][210,100]"/>'
        # Tap too small — serious
        '<node class="android.widget.Button" text="B" '
        'clickable="true" enabled="true" bounds="[220,0][240,20]"/>'
    )
    uc = AuditAccessibility(
        devices=_FakeDeviceRepo(), ui=_FakeUiRepo(xml), state=_FakeStateRepo()
    )
    res = await uc(AuditAccessibilityParams())
    assert isinstance(res, Ok)
    severities = [f.severity for f in res.value.findings]
    # All blockers before any serious; all serious before any minor.
    sev_rank = {Severity.BLOCKER: 0, Severity.SERIOUS: 1, Severity.MINOR: 2}
    ranks = [sev_rank[s] for s in severities]
    assert ranks == sorted(ranks)


@pytest.mark.asyncio
async def test_all_clean_produces_check_advice():
    """An empty UI tree → no findings → ✓ advice line."""
    uc = AuditAccessibility(
        devices=_FakeDeviceRepo(), ui=_FakeUiRepo(""), state=_FakeStateRepo()
    )
    res = await uc(AuditAccessibilityParams())
    assert isinstance(res, Ok)
    v = res.value
    assert v.blocker_count == 0
    assert v.serious_count == 0
    assert "✓" in v.advice
    # Honest disclaimer that contrast + focus order aren't covered.
    assert "color contrast" in v.advice.lower() or "manual review" in v.advice.lower()


@pytest.mark.asyncio
async def test_result_includes_unique_sorted_standards():
    """The standards tuple is dedup'd and sorted."""
    xml = (
        # Two findings against the same standard → only one entry
        '<node class="android.widget.Button" '
        'clickable="true" enabled="true" bounds="[0,0][20,20]"/>'
        '<node class="android.widget.Button" '
        'clickable="true" enabled="true" bounds="[100,0][120,20]"/>'
    )
    uc = AuditAccessibility(
        devices=_FakeDeviceRepo(), ui=_FakeUiRepo(xml), state=_FakeStateRepo()
    )
    res = await uc(AuditAccessibilityParams())
    assert isinstance(res, Ok)
    standards = res.value.standards
    assert standards == tuple(sorted(set(standards)))


# ---- _build_advice ----------------------------------------------------


def test_advice_blocker_uses_failure_verdict():
    advice = _build_advice(blocker=2, serious=0, minor=0, elements=50)
    assert "❌" in advice
    assert "MUST" in advice or "must" in advice.lower()


def test_advice_serious_only_uses_warn_verdict():
    advice = _build_advice(blocker=0, serious=3, minor=1, elements=50)
    assert "⚠" in advice
    assert "❌" not in advice


def test_advice_minor_only_is_polish():
    advice = _build_advice(blocker=0, serious=0, minor=2, elements=50)
    assert "✓" in advice
    assert "polish" in advice.lower() or "not blocking" in advice.lower()
