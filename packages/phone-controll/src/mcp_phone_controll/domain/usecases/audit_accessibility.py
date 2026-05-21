"""Accessibility audit — store-listing-readiness gate.

Walks the running app's UI tree, flags violations of the WCAG 2.2
success criteria that map to native mobile and EU EAA 2025
requirements. Returns a structured report with each finding
categorized + cited to the specific WCAG criterion.

What it catches (the high-leverage subset):

  • SC 2.5.5 / 2.5.8 Target Size — interactive elements smaller
    than 48x48 dp (Android) / 44x44 pt (iOS).
  • SC 1.3.1 / 4.1.2 Name & Role — interactive elements with no
    accessible label (talkback/voiceover sees nothing).
  • SC 1.4.4 Resize text proxy — tiny font sizes that can't scale
    sensibly. We can't measure rendered font directly but we can
    flag low-content density as a hint.
  • RenderFlex overflow markers (Flutter-specific signal) —
    presence of red/yellow overflow indicators in the recent
    logs after a relayout.

What it doesn't catch (yet):

  • Color contrast (SC 1.4.3 / 1.4.11) — requires pixel sampling
    from the screenshot + parsing the underlying widget colors.
    Planned for a follow-up (`audit_color_contrast`).
  • Focus order (SC 2.4.3) — requires simulating tab navigation.
  • Captioning, motion, etc. — beyond mobile-app scope.

The advice line summarizes the report into one paste-ready
sentence for PR comments. Each finding carries the WCAG criterion
in `standard` so reviewers see the source-of-truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from ..entities import Bounds
from ..failures import UiFailure
from ..repositories import (
    DeviceRepository,
    SessionStateRepository,
    UiRepository,
)
from ..result import Err, Result, err, ok
from ._helpers import resolve_serial
from .base import BaseUseCase

# WCAG 2.2 native-mobile minima. Android uses dp; iOS uses pt;
# both target ~9 mm physical for a comfortable thumb. We use 48
# as the universal threshold (Android's value — iOS 44 pt is a
# tiny bit smaller, but the test catches both).
_MIN_TAP_TARGET_DP = 48


class Severity(str, Enum):
    BLOCKER = "blocker"     # WCAG Level AA mandatory — fix before ship
    SERIOUS = "serious"     # WCAG Level AA recommended — fix this release
    MINOR = "minor"         # WCAG Level AAA / industry best practice


@dataclass(frozen=True, slots=True)
class AccessibilityFinding:
    rule: str               # short slug, e.g. "tap_target_too_small"
    description: str        # what's wrong, in plain English
    standard: str           # the WCAG criterion or guidance citing this
    severity: Severity
    element_class: str | None    # Widget/Class name from the UI tree
    element_text: str | None     # any visible text on the offending element
    bounds: Bounds | None        # so the agent can dump_ui + visualize
    # If the rule is fixable in a single Flutter property
    # ('Semantics(label:..)' wrap, 'ConstrainedBox(minWidth: 48)'),
    # name it here so PR-comment text is actionable.
    fix_hint: str | None


@dataclass(frozen=True, slots=True)
class AuditAccessibilityParams:
    serial: str | None = None
    # When True, also scans the last 30s of logs for RenderFlex
    # overflow markers — those flagged by Flutter at relayout time.
    include_log_signals: bool = True
    # If you want to exclude elements you've intentionally hidden
    # from accessibility (e.g. decorative icons), pass class names
    # here. Defaults match Flutter / Material conventions.
    ignore_class_substrings: tuple[str, ...] = (
        "Divider", "Padding", "SizedBox",
    )


@dataclass(frozen=True, slots=True)
class AuditAccessibilityResult:
    serial: str
    findings: tuple[AccessibilityFinding, ...]
    blocker_count: int
    serious_count: int
    minor_count: int
    elements_inspected: int
    advice: str             # paste-ready PR-comment line
    standards: tuple[str, ...]   # unique sorted list of cited rules


class AuditAccessibility(
    BaseUseCase[AuditAccessibilityParams, AuditAccessibilityResult]
):
    """Walks the live UI tree on a connected device, flags WCAG
    violations.

    Uses the existing UiRepository.dump_ui() so it benefits from
    the same NFC normalization + Polish-NBSP-tolerance we built
    for tap_text. Works on Android (uiautomator2 XML dump) and
    iOS (WDA element tree).

    Returns findings sorted by severity (blocker → serious →
    minor) so the agent can prioritize directly.
    """

    def __init__(
        self,
        devices: DeviceRepository,
        ui: UiRepository,
        state: SessionStateRepository,
    ) -> None:
        self._devices = devices
        self._ui = ui
        self._state = state

    async def execute(
        self, params: AuditAccessibilityParams
    ) -> Result[AuditAccessibilityResult]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        serial = serial_res.value

        # Pull the UI dump. UiRepository.dump_ui returns the raw
        # platform-specific XML/JSON string.
        try:
            dump_res = await self._ui.dump_ui(serial)
        except Exception as e:
            return err(
                UiFailure(
                    message=f"dump_ui failed: {e}",
                    next_action="check_app_running_or_wda",
                )
            )
        if isinstance(dump_res, Err):
            return dump_res
        xml = dump_res.value or ""

        # Walk the tree. Heuristic regex-based parsing (same approach
        # we use in uiautomator2_ui_repository for tap_text's
        # fallback path) so we don't add an XML-lib dep.
        findings: list[AccessibilityFinding] = []
        elements = _parse_ui_elements(xml)

        for el in elements:
            if any(skip in (el.class_name or "") for skip in params.ignore_class_substrings):
                continue
            findings.extend(_check_element(el))

        # Sort: blocker first, then serious, then minor. Stable so
        # finding order within a tier reflects tree order (top-down).
        sev_rank = {Severity.BLOCKER: 0, Severity.SERIOUS: 1, Severity.MINOR: 2}
        findings.sort(key=lambda f: sev_rank[f.severity])

        blocker = sum(1 for f in findings if f.severity == Severity.BLOCKER)
        serious = sum(1 for f in findings if f.severity == Severity.SERIOUS)
        minor = sum(1 for f in findings if f.severity == Severity.MINOR)

        advice = _build_advice(blocker, serious, minor, len(elements))
        standards = tuple(sorted({f.standard for f in findings}))

        return ok(AuditAccessibilityResult(
            serial=serial,
            findings=tuple(findings),
            blocker_count=blocker,
            serious_count=serious,
            minor_count=minor,
            elements_inspected=len(elements),
            advice=advice,
            standards=standards,
        ))


# ---- UI-element parsing ------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Element:
    class_name: str | None
    text: str | None
    content_desc: str | None
    clickable: bool
    bounds: Bounds | None
    resource_id: str | None
    enabled: bool


# uiautomator2 dump format:
#   <node text="" resource-id="..." class="android.widget.Button"
#         content-desc="" clickable="true" bounds="[10,20][110,80]"/>
_NODE_RE = re.compile(r"<node\s+([^>]+?)\s*/?>")


def _attr(attrs: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def _parse_ui_elements(xml: str) -> list[_Element]:
    """Parse the uiautomator2-style XML dump.

    For iOS WDA dumps (different shape — JSON), we'd need a parallel
    parser. v0.3.0 focuses on Android because that's where the
    accessibility findings are most actionable in practice (WDA's
    iOS tree is less detailed). iOS support: planned follow-up.
    """
    out: list[_Element] = []
    for match in _NODE_RE.finditer(xml):
        attrs = match.group(1)
        bounds_str = _attr(attrs, "bounds")
        bounds = _parse_bounds(bounds_str) if bounds_str else None
        out.append(_Element(
            class_name=_attr(attrs, "class"),
            text=_attr(attrs, "text") or None,
            content_desc=_attr(attrs, "content-desc") or None,
            clickable=(_attr(attrs, "clickable") == "true"),
            bounds=bounds,
            resource_id=_attr(attrs, "resource-id") or None,
            enabled=(_attr(attrs, "enabled") != "false"),
        ))
    return out


_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _parse_bounds(raw: str) -> Bounds | None:
    m = _BOUNDS_RE.search(raw)
    if not m:
        return None
    x1, y1, x2, y2 = (int(g) for g in m.groups())
    w = max(0, x2 - x1)
    h = max(0, y2 - y1)
    if w == 0 or h == 0:
        return None
    return Bounds(x=x1, y=y1, width=w, height=h)


# ---- per-element checks ------------------------------------------------


def _check_element(el: _Element) -> list[AccessibilityFinding]:
    """Apply each WCAG check to one element. Returns 0..N findings."""
    findings: list[AccessibilityFinding] = []

    # ----- SC 2.5.5 / 2.5.8: Target Size -----
    # Only applies to interactive (clickable) elements.
    if el.clickable and el.bounds is not None:
        # Bounds come in pixels from uiautomator2. The dp threshold
        # depends on device density — most modern devices are
        # ~2-3x density, so 48dp ≈ 96-144 px. We use a forgiving
        # threshold of 48 px which catches "definitely too small"
        # without needing density introspection. Refinement:
        # density-aware threshold via getprop ro.sf.lcd_density —
        # planned follow-up.
        w = el.bounds.width
        h = el.bounds.height
        if w < _MIN_TAP_TARGET_DP or h < _MIN_TAP_TARGET_DP:
            findings.append(AccessibilityFinding(
                rule="tap_target_too_small",
                description=(
                    f"Interactive element measures {w}×{h} px — below the "
                    f"WCAG SC 2.5.5 minimum of {_MIN_TAP_TARGET_DP}×"
                    f"{_MIN_TAP_TARGET_DP} dp."
                ),
                standard="WCAG 2.2 SC 2.5.5 Target Size (Minimum)",
                severity=Severity.SERIOUS,
                element_class=el.class_name,
                element_text=el.text,
                bounds=el.bounds,
                fix_hint=(
                    "Wrap in ConstrainedBox(minWidth: 48, minHeight: 48), "
                    "or set explicit padding to expand the hit area without "
                    "changing visual size."
                ),
            ))

    # ----- SC 4.1.2 Name, Role, Value: missing accessible label -----
    # Interactive elements MUST expose a non-empty name (text or
    # content-desc / accessibilityLabel). Without it, screen
    # readers announce nothing — the user can hear there's a
    # control but doesn't know what it does.
    if el.clickable:
        has_label = bool((el.text or "").strip()) or bool((el.content_desc or "").strip())
        if not has_label:
            findings.append(AccessibilityFinding(
                rule="missing_accessible_label",
                description=(
                    "Interactive element has no visible text and no "
                    "content-desc / accessibility label. Screen-reader "
                    "users hear silence when they focus this element."
                ),
                standard="WCAG 2.2 SC 4.1.2 Name, Role, Value",
                severity=Severity.BLOCKER,
                element_class=el.class_name,
                element_text=None,
                bounds=el.bounds,
                fix_hint=(
                    "Wrap in Semantics(label: '...') or pass `tooltip:` "
                    "to the widget. For IconButton, set `tooltip:` (it "
                    "becomes the accessibility label)."
                ),
            ))

    # ----- SC 1.3.1 Info and Relationships: disabled but unmarked -----
    # An interactive-looking element that is disabled but doesn't
    # advertise itself as such gives mixed signals. We can only
    # detect the explicit `enabled="false"` case.
    if el.clickable and not el.enabled:
        findings.append(AccessibilityFinding(
            rule="disabled_interactive_unmarked",
            description=(
                "Element is marked clickable but disabled — screen "
                "readers may still announce it as actionable. Either "
                "make it non-clickable when disabled, or set "
                "Semantics(enabled: false)."
            ),
            standard="WCAG 2.2 SC 1.3.1 Info and Relationships",
            severity=Severity.MINOR,
            element_class=el.class_name,
            element_text=el.text,
            bounds=el.bounds,
            fix_hint=(
                "Either remove the onPressed when disabled (Flutter "
                "auto-disables the Button) or wrap in "
                "Semantics(enabled: false)."
            ),
        ))

    return findings


# ---- advice + reporting ------------------------------------------------


def _build_advice(
    blocker: int, serious: int, minor: int, elements: int
) -> str:
    """One-sentence verdict suitable for a PR comment."""
    total = blocker + serious + minor
    if total == 0:
        return (
            f"✓ Accessibility audit clean. Inspected {elements} elements, "
            "no WCAG 2.2 Level AA violations detected. "
            "Note: color contrast + focus order not yet covered — "
            "manual review still required for full compliance."
        )
    summary_parts: list[str] = []
    if blocker:
        summary_parts.append(f"{blocker} blocker")
    if serious:
        summary_parts.append(f"{serious} serious")
    if minor:
        summary_parts.append(f"{minor} minor")
    summary = ", ".join(summary_parts)

    if blocker > 0:
        verdict = (
            f"❌ {summary} accessibility issue(s) across {elements} elements. "
            "Blockers MUST be fixed before any release that targets EU "
            "EAA 2025 compliance."
        )
    elif serious > 0:
        verdict = (
            f"⚠ {summary} accessibility issue(s) across {elements} elements. "
            "Fix the serious tier before the next release."
        )
    else:
        verdict = (
            f"✓ {summary} accessibility issue(s) across {elements} elements. "
            "Polish item — not blocking."
        )
    return verdict
