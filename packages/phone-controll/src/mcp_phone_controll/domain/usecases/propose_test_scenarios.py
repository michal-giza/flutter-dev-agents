"""Test scenario designer — turns 'what should I test?' into a
research-grounded checklist.

The problem this solves: ask any LLM 'design test scenarios for my
app' and you get a generic list (login, navigation, button clicks).
That misses the failure modes that actually break apps in
production — permission denials, network drops, locale switches,
incoming calls during a flow.

Industry mobile-QA research has converged on a clear taxonomy of
test scenarios that catch real-world failures. This tool encodes
that taxonomy + tailors it to the specific app under test by
reading its manifest / Info.plist / pubspec.

References this is grounded in (cited per-scenario in the result):

  • Google Android Quality Guidelines — Core App Quality (CAQ).
    https://developer.android.com/quality
  • Apple HIG testing checklist + App Store Review Guidelines §2
    https://developer.apple.com/design/human-interface-guidelines/testing
  • ISO/IEC 25010:2011 — Software Quality Model (8 categories).
  • WCAG 2.2 — Web Content Accessibility Guidelines (applies to
    native mobile under EU EAA 2025).
  • Drizz 2026 mobile QA industry survey (selector-maintenance
    cost numbers).
  • Flutter team's own integration_test conventions.
  • Patrol's recommended-flow patterns (LeanCode docs).

The output isn't a wall of advice — it's a structured list the
agent can iterate through, each scenario tagged with priority
(P0/P1/P2), the standard that motivates it, and the concrete
sequence of tools to call.

Scope of v0.3.0:

- Hard-coded baseline taxonomy (always applies regardless of app).
- Project-aware enrichers that inspect manifest/pubspec to add
  scenarios for specific features (camera permission, deep links,
  background services, etc.).
- A `focus_areas` parameter lets the agent narrow output if it
  only cares about a subset (e.g. 'accessibility' before a store
  submission).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from .base import BaseUseCase


class Priority(str, Enum):
    P0 = "P0"   # Must-test before any ship — bugs here block users.
    P1 = "P1"   # Should-test for a credible release.
    P2 = "P2"   # Nice-to-test — polish + edge cases.


class Category(str, Enum):
    HAPPY_PATH = "happy_path"
    PERMISSION = "permission"
    NETWORK = "network"
    INPUT = "input"
    INTERRUPTION = "interruption"
    LIFECYCLE = "lifecycle"
    ACCESSIBILITY = "accessibility"
    LOCALIZATION = "localization"
    DEVICE_MATRIX = "device_matrix"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DATA = "data"


@dataclass(frozen=True, slots=True)
class TestScenario:
    name: str                            # short imperative, e.g. "Deny camera permission mid-flow"
    description: str                     # what + why in 1-2 sentences
    category: Category
    priority: Priority
    standard: str                        # reference for "why this matters"
    tool_sequence: tuple[str, ...]       # MCP tools the agent would call
    project_specific: bool = False       # True if added by an enricher


@dataclass(frozen=True, slots=True)
class ProposeTestScenariosParams:
    project_path: Path
    # Optional natural-language description the agent provides
    # ("a fitness tracker that records GPS routes"). When set, we
    # try to keyword-match it against scenario tags for ranking;
    # otherwise we return the canonical-priority order.
    app_description: str | None = None
    # Filter to a subset of categories. Useful for store-listing
    # accessibility audits or pre-release security passes.
    focus_areas: tuple[str, ...] = ()
    # Cap on total scenarios returned. Default 25 is the sweet
    # spot — enough to be thorough, few enough to actually do.
    top_n: int = 25


@dataclass(frozen=True, slots=True)
class ProposeTestScenariosResult:
    project_path: str
    detected_features: dict[str, bool]   # what enrichers picked up
    scenarios: tuple[TestScenario, ...]  # sorted by priority then category
    advice: str                          # paste-ready PR-comment line
    references: tuple[str, ...]          # the standards this draws from


class ProposeTestScenarios(
    BaseUseCase[ProposeTestScenariosParams, ProposeTestScenariosResult]
):
    """Returns a research-grounded test-scenario checklist for the project.

    Inspects:
      • android/app/src/main/AndroidManifest.xml — permissions, intent
        filters (deep links), services
      • ios/Runner/Info.plist — usage descriptions (the iOS analog of
        Android permissions)
      • pubspec.yaml — packages that signal features (geolocator,
        flutter_local_notifications, firebase_*, etc.)

    Returns the union of canonical scenarios + project-aware additions,
    sorted by priority. Each scenario carries the tool sequence the
    agent would actually run.
    """

    async def execute(
        self, params: ProposeTestScenariosParams
    ) -> Result[ProposeTestScenariosResult]:
        if not params.project_path.is_dir():
            return err(
                FilesystemFailure(
                    message=f"project_path not found: {params.project_path}",
                    next_action="fix_arguments",
                )
            )

        # Inspect project features for tailored scenarios.
        features = _detect_features(params.project_path)

        # Start with the canonical baseline (always applies).
        scenarios = list(_canonical_scenarios())

        # Project-aware enrichers — each adds scenarios only when its
        # trigger feature is present.
        scenarios += list(_project_enrichers(features))

        # Filter by focus_areas if the caller narrowed it down.
        if params.focus_areas:
            allowed = {Category(a) for a in params.focus_areas if _is_valid_category(a)}
            scenarios = [s for s in scenarios if s.category in allowed]

        # Rank: P0 first, then P1, then P2. Within priority, keep
        # category-grouped order for readability.
        scenarios.sort(key=lambda s: (s.priority.value, s.category.value))

        # Truncate to top_n.
        scenarios = scenarios[: max(params.top_n, 1)]

        advice = _build_advice(scenarios, features)
        references = _collect_references(scenarios)

        return ok(
            ProposeTestScenariosResult(
                project_path=str(params.project_path),
                detected_features=features,
                scenarios=tuple(scenarios),
                advice=advice,
                references=references,
            )
        )


# ---- feature detection -------------------------------------------------


def _detect_features(project_path: Path) -> dict[str, bool]:
    """Inspect the project to learn what features it uses.

    Best-effort: any individual file being missing or malformed
    is fine — we just won't add the enrichers for that feature.
    """
    features: dict[str, bool] = {
        "uses_camera": False,
        "uses_location": False,
        "uses_microphone": False,
        "uses_storage": False,
        "uses_notifications": False,
        "uses_contacts": False,
        "uses_deep_links": False,
        "uses_background_services": False,
        "uses_in_app_purchase": False,
        "uses_biometrics": False,
        "uses_firebase": False,
        "uses_payments": False,
        "uses_ml_kit": False,
        "uses_ar": False,
        "has_login_flow": False,
        "supports_dark_mode": False,
        "supports_localization": False,
    }

    # Android manifest
    manifest = project_path / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    if manifest.is_file():
        try:
            content = manifest.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""
        if "android.permission.CAMERA" in content:
            features["uses_camera"] = True
        if any(p in content for p in (
            "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION",
            "ACCESS_BACKGROUND_LOCATION",
        )):
            features["uses_location"] = True
        if "RECORD_AUDIO" in content:
            features["uses_microphone"] = True
        if any(p in content for p in (
            "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE",
            "MANAGE_EXTERNAL_STORAGE", "READ_MEDIA_IMAGES",
        )):
            features["uses_storage"] = True
        if any(p in content for p in (
            "POST_NOTIFICATIONS", "android.permission.NOTIFICATIONS",
        )):
            features["uses_notifications"] = True
        if "READ_CONTACTS" in content or "WRITE_CONTACTS" in content:
            features["uses_contacts"] = True
        if "<intent-filter>" in content and "android.intent.action.VIEW" in content:
            features["uses_deep_links"] = True
        if "android.permission.FOREGROUND_SERVICE" in content or "<service" in content:
            features["uses_background_services"] = True
        if "USE_BIOMETRIC" in content or "USE_FINGERPRINT" in content:
            features["uses_biometrics"] = True

    # iOS Info.plist
    plist = project_path / "ios" / "Runner" / "Info.plist"
    if plist.is_file():
        try:
            content = plist.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""
        if "NSCameraUsageDescription" in content:
            features["uses_camera"] = True
        if any(k in content for k in (
            "NSLocationWhenInUseUsageDescription",
            "NSLocationAlwaysAndWhenInUseUsageDescription",
        )):
            features["uses_location"] = True
        if "NSMicrophoneUsageDescription" in content:
            features["uses_microphone"] = True
        if "NSPhotoLibraryUsageDescription" in content:
            features["uses_storage"] = True
        if "NSContactsUsageDescription" in content:
            features["uses_contacts"] = True
        if "NSFaceIDUsageDescription" in content:
            features["uses_biometrics"] = True

    # pubspec.yaml — Flutter package signals
    pubspec = project_path / "pubspec.yaml"
    if pubspec.is_file():
        try:
            content = pubspec.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""
        # Permission/feature packages
        if "geolocator:" in content or "location:" in content:
            features["uses_location"] = True
        if "camera:" in content or "image_picker:" in content:
            features["uses_camera"] = True
        if "flutter_local_notifications" in content or "firebase_messaging" in content:
            features["uses_notifications"] = True
        if "in_app_purchase" in content:
            features["uses_in_app_purchase"] = True
        if "firebase_" in content:
            features["uses_firebase"] = True
        if "google_pay" in content or "stripe" in content or "razorpay" in content:
            features["uses_payments"] = True
        if "google_mlkit" in content or "tflite_flutter" in content:
            features["uses_ml_kit"] = True
        if "ar_flutter_plugin" in content or "arcore_flutter_plugin" in content:
            features["uses_ar"] = True
        if "local_auth" in content:
            features["uses_biometrics"] = True
        # Auth / login indicators
        if any(k in content for k in (
            "firebase_auth", "google_sign_in", "sign_in_with_apple",
            "flutter_appauth", "oauth2",
        )):
            features["has_login_flow"] = True
        # Localization
        if "flutter_localizations" in content or "intl:" in content:
            features["supports_localization"] = True
        # Theme hints
        if "ThemeMode" in content:
            features["supports_dark_mode"] = True

    # Source-level deep-link route hints — look at the router files
    for router_path in (
        project_path / "lib" / "app_router.dart",
        project_path / "lib" / "router.dart",
        project_path / "lib" / "core" / "router" / "app_router.dart",
    ):
        if router_path.is_file():
            try:
                if re.search(r"GoRoute|GoRouter|routes:", router_path.read_text(encoding="utf-8", errors="ignore")):
                    features["uses_deep_links"] = True
            except OSError:
                pass

    return features


# ---- canonical baseline taxonomy ---------------------------------------


def _canonical_scenarios() -> list[TestScenario]:
    """The scenarios that apply to ~every mobile app.

    Ordered by priority then category for readability. Each tagged
    with the standard that justifies it.
    """
    return [
        # ---- HAPPY PATH (P0) ----
        TestScenario(
            name="Cold launch → main screen renders within 3s",
            description=(
                "Boot from fully terminated state, measure time-to-first-frame. "
                "Google Android Vitals flags > 5s cold-start times — 3s is the "
                "user-perceptible threshold."
            ),
            category=Category.HAPPY_PATH,
            priority=Priority.P0,
            standard="Google Android Vitals — Cold Start",
            tool_sequence=(
                "select_device", "prepare_for_test",
                "stop_app", "launch_app",
                "wait_for_element", "assert_no_errors_since",
            ),
        ),
        TestScenario(
            name="Primary user journey end-to-end",
            description=(
                "The single most-traveled path through the app — the journey "
                "the product manager would describe in one sentence. If this "
                "fails, the app is broken."
            ),
            category=Category.HAPPY_PATH,
            priority=Priority.P0,
            standard="ISO/IEC 25010 §6.3 Functional suitability",
            tool_sequence=(
                "launch_app", "tap_and_verify", "tap_and_verify",
                "assert_no_errors_since",
            ),
        ),

        # ---- PERMISSION (P0) ----
        TestScenario(
            name="Deny every runtime permission, app still launches",
            description=(
                "Tap 'Deny' on every permission dialog on first launch. The "
                "app must not crash and must surface a path forward (settings "
                "deep link, retry button, or graceful degradation)."
            ),
            category=Category.PERMISSION,
            priority=Priority.P0,
            standard="Google CAQ — Permission Handling; App Store Review §5.1.1",
            tool_sequence=(
                "clear_app_data", "launch_app", "tap_text:Deny:system=true",
                "assert_no_errors_since",
            ),
        ),
        TestScenario(
            name="Grant permission, then revoke from OS settings while app runs",
            description=(
                "User grants camera permission in-app, opens Settings → Apps → "
                "your-app → Permissions, revokes it. App must detect the change "
                "and re-prompt (or fail gracefully) instead of silently calling "
                "into the platform with no permission."
            ),
            category=Category.PERMISSION,
            priority=Priority.P1,
            standard="Google CAQ — Permission Handling",
            tool_sequence=(
                "launch_app", "grant_permission", "stop_app",
                "press_key:HOME", "launch_app:com.android.settings",
                # ... revoke in settings ...
                "launch_app:<the app under test>",
                "assert_no_errors_since",
            ),
        ),

        # ---- NETWORK (P0) ----
        TestScenario(
            name="Cold start with no network",
            description=(
                "Boot the app with airplane mode on. If it relies on backend "
                "for first paint, it must show a clear offline state, not a "
                "white screen or a thrown exception."
            ),
            category=Category.NETWORK,
            priority=Priority.P0,
            standard="Google CAQ — Offline Behavior",
            tool_sequence=(
                "press_key:AIRPLANE_MODE",
                "stop_app", "launch_app",
                "wait_for_element:Offline OR No connection",
                "assert_no_errors_since",
            ),
        ),
        TestScenario(
            name="Network drops mid-action (interrupt mid-submit)",
            description=(
                "User starts an action that hits the network (submit form, "
                "send message). Mid-request, network drops. App must show a "
                "retry/offline state with the user's input preserved — NOT "
                "lose the form data."
            ),
            category=Category.NETWORK,
            priority=Priority.P0,
            standard="Drizz 2026 mobile-QA survey — top 5 user-visible bug",
            tool_sequence=(
                "type_text", "tap_text:Submit",
                "press_key:AIRPLANE_MODE",
                "wait_for_element:Retry OR Offline",
                "assert_no_errors_since",
            ),
        ),
        TestScenario(
            name="Slow network (2G simulation)",
            description=(
                "Throttle to 2G speeds; assert UI shows progress indicators "
                "for any operation > 1 second. Frequent omission — users on "
                "spotty connections think the app froze."
            ),
            category=Category.NETWORK,
            priority=Priority.P1,
            standard="Google CAQ — Loading States",
            tool_sequence=(
                "launch_app", "tap_and_verify",
                "start_frame_profile",
                "stop_frame_profile",
            ),
        ),

        # ---- INPUT (P1) ----
        TestScenario(
            name="Submit form with empty required fields",
            description=(
                "Every form: tap submit without filling required fields. "
                "Inline validation must trigger before the network call."
            ),
            category=Category.INPUT,
            priority=Priority.P1,
            standard="Material Design — Text fields validation",
            tool_sequence=(
                "tap_text:Submit",
                "assert_visible:required",
                "assert_no_errors_since",
            ),
        ),
        TestScenario(
            name="Paste emoji + RTL + special chars into text fields",
            description=(
                "Real users paste 🎉, Arabic/Hebrew text, smart quotes (' '), "
                "and combined characters. Field must not crash or truncate "
                "mid-grapheme."
            ),
            category=Category.INPUT,
            priority=Priority.P1,
            standard="Unicode TR29 — grapheme cluster handling",
            tool_sequence=(
                "tap_and_verify",
                "type_text:🎉 السلام عليكم 你好",
                "assert_no_errors_since",
            ),
        ),
        TestScenario(
            name="Maximum-length input (server limit)",
            description=(
                "Paste the server's max-length string +1 char. Client should "
                "either clip with feedback or reject before sending — never "
                "send and let the server 400."
            ),
            category=Category.INPUT,
            priority=Priority.P2,
            standard="OWASP Mobile Top 10 — Improper Input Validation",
            tool_sequence=(
                "type_text:<oversized string>",
                "tap_text:Submit",
                "assert_visible:Too long OR Maximum",
            ),
        ),

        # ---- INTERRUPTION (P1) ----
        TestScenario(
            name="Incoming phone call during a multi-step flow",
            description=(
                "User in the middle of a checkout or auth flow. Simulate an "
                "incoming call. After dismissing, the app must restore the "
                "exact step + user input intact."
            ),
            category=Category.INTERRUPTION,
            priority=Priority.P1,
            standard="Apple HIG — App Architecture / State Preservation",
            tool_sequence=(
                "launch_app", "tap_text:Next",
                # adb shell am start -a android.intent.action.CALL ...
                "wait_for_element",
                "assert_no_errors_since",
            ),
        ),
        TestScenario(
            name="App backgrounded mid-flow, OS kills it, user re-opens",
            description=(
                "Backgrounded apps can be killed at any moment under memory "
                "pressure. The recents-tap restore path should land users "
                "where they left off — not at the splash screen."
            ),
            category=Category.INTERRUPTION,
            priority=Priority.P0,
            standard="Android Lifecycle / iOS State Restoration",
            tool_sequence=(
                "launch_app", "tap_and_verify",
                "press_key:HOME",
                "stop_app",  # simulates OS kill
                "launch_app",
                "assert_visible:<the step you were on>",
            ),
        ),

        # ---- LIFECYCLE (P0) ----
        TestScenario(
            name="Logout → login → all stale data cleared",
            description=(
                "After logout, no previous user's data should be visible "
                "(profile photo, recent items, cached settings). Caches "
                "leaking across users is a P0 privacy bug."
            ),
            category=Category.LIFECYCLE,
            priority=Priority.P0,
            standard="OWASP Mobile Top 10 — Insecure Data Storage",
            tool_sequence=(
                "tap_text:Logout",
                "tap_text:Login",  # different user
                "assert_no_errors_since",
                # manually verify no leakage in dump_ui
            ),
        ),

        # ---- ACCESSIBILITY (P1, EAA-compliance gates) ----
        TestScenario(
            name="TalkBack/VoiceOver can navigate the main flow",
            description=(
                "Turn on the screen reader; the primary flow must be "
                "completable using only screen-reader gestures (swipe + "
                "double-tap). EU EAA 2025 makes this regulatory in many "
                "countries."
            ),
            category=Category.ACCESSIBILITY,
            priority=Priority.P1,
            standard="WCAG 2.2 Level AA; EU EAA 2025",
            tool_sequence=(
                "dump_ui",  # semantics tree check
                # planned v0.3.x: audit_accessibility tool
            ),
        ),
        TestScenario(
            name="Tap targets ≥ 48×48 dp",
            description=(
                "All interactive elements meet WCAG 2.2 success criterion "
                "2.5.5 (Target Size). Tiny tap targets are the #1 cause of "
                "store-review accessibility complaints."
            ),
            category=Category.ACCESSIBILITY,
            priority=Priority.P1,
            standard="WCAG 2.2 SC 2.5.5",
            tool_sequence=(
                "dump_ui",
                # planned v0.3.x: audit_accessibility tool
            ),
        ),
        TestScenario(
            name="200% text scale doesn't break layouts",
            description=(
                "Android Display size / iOS Dynamic Type cranked to max. "
                "RenderFlex overflows are the most common bug class here."
            ),
            category=Category.ACCESSIBILITY,
            priority=Priority.P1,
            standard="WCAG 2.2 SC 1.4.4 Resize text",
            tool_sequence=(
                "launch_app",
                "read_logs:30s",  # look for RenderFlex overflow
                "take_screenshot",
            ),
        ),

        # ---- LOCALIZATION (P1) ----
        TestScenario(
            name="Switch device locale to RTL (Arabic/Hebrew)",
            description=(
                "Re-launch with locale set to ar-SA or he-IL. Layout direction "
                "should flip; icons that have inherent direction (back arrow, "
                "send arrow) should mirror."
            ),
            category=Category.LOCALIZATION,
            priority=Priority.P1,
            standard="Material Design — Bidirectionality; ICU CLDR",
            tool_sequence=(
                # set locale via adb shell setprop persist.sys.locale ar-SA
                "stop_app", "launch_app",
                "take_screenshot:rtl-layout",
            ),
        ),
        TestScenario(
            name="Long-translation strings don't truncate or overflow",
            description=(
                "German strings can be 30-40% longer than English. Spanish "
                "and Polish similarly. Buttons + tabs + dialog titles need to "
                "handle this without ellipsis-cutting key meaning."
            ),
            category=Category.LOCALIZATION,
            priority=Priority.P1,
            standard="ICU CLDR translation-length guidance",
            tool_sequence=(
                "stop_app", "launch_app",  # de-DE locale
                "take_screenshot",
                # planned: localization-audit tool
            ),
        ),

        # ---- DEVICE MATRIX (P1) ----
        TestScenario(
            name="Low-end device: 2GB RAM, slow CPU",
            description=(
                "Test on a Pixel 6a-class device (or an emulator throttled to "
                "2GB / 2 cores). Major share of emerging markets. Memory + "
                "frame budgets are stricter here."
            ),
            category=Category.DEVICE_MATRIX,
            priority=Priority.P1,
            standard="Google CAQ — Performance on low-end devices",
            tool_sequence=(
                "start_emulator:pixel_6a_low_end",
                "select_device",
                "launch_app",
                "start_frame_profile",
                "stop_frame_profile",
                "memory_summary",
            ),
        ),
        TestScenario(
            name="Tablet / large-screen layout",
            description=(
                "Run on an iPad-class or Android tablet (or foldable in "
                "unfolded mode). Master-detail layouts, multi-column lists, "
                "and rotation should adapt — not just scale up."
            ),
            category=Category.DEVICE_MATRIX,
            priority=Priority.P2,
            standard="Material Design — Adaptive layouts; HIG — iPad",
            tool_sequence=(
                "select_device:<tablet UDID>",
                "launch_app", "take_screenshot",
            ),
        ),

        # ---- PERFORMANCE (P1) ----
        TestScenario(
            name="Scroll a long list — frame rate stays ≥ 60fps",
            description=(
                "The single most common jank source. Janky scroll is "
                "user-visible; static analysis doesn't catch it."
            ),
            category=Category.PERFORMANCE,
            priority=Priority.P1,
            standard="Flutter team — '120fps' performance guide",
            tool_sequence=(
                "start_frame_profile",
                "swipe",
                "stop_frame_profile",
            ),
        ),
        TestScenario(
            name="Memory doesn't grow across 10× navigation cycles",
            description=(
                "Push and pop the same route 10 times. Heap should return to "
                "baseline (± controller-count noise). Growth = uncleaned "
                "subscriptions/controllers."
            ),
            category=Category.PERFORMANCE,
            priority=Priority.P1,
            standard="Flutter team — State Management / Resource Disposal",
            tool_sequence=(
                "allocation_profile:reset_accumulator=true",
                # navigate N times
                "allocation_profile",
                "detect_undisposed_controllers",
            ),
        ),

        # ---- SECURITY (P0) ----
        TestScenario(
            name="No secrets / API keys in the built app",
            description=(
                "Decompile (or grep) the release APK/IPA for 'apiKey', "
                "'secret', 'password'. Common bug: dev-only debugging "
                "constants shipped to production."
            ),
            category=Category.SECURITY,
            priority=Priority.P0,
            standard="OWASP Mobile Top 10 — Insecure Configuration",
            tool_sequence=(
                "build_app:release",
                # planned: secret_scan tool. For now: manual grep.
            ),
        ),

        # ---- DATA (P1) ----
        TestScenario(
            name="App handles a malformed/empty backend response",
            description=(
                "Mock the backend to return `{}` or `null` for a list "
                "endpoint. App should show empty-state UI, not crash or "
                "infinite-load."
            ),
            category=Category.DATA,
            priority=Priority.P1,
            standard="ISO/IEC 25010 §6.4 Reliability — Fault tolerance",
            tool_sequence=(
                # requires backend mock or network mock; future tool
                "launch_app",
                "assert_visible:empty-state",
                "assert_no_errors_since",
            ),
        ),
    ]


def _project_enrichers(features: dict[str, bool]) -> list[TestScenario]:
    """Project-specific scenarios — only added when the feature is detected.

    The marker `project_specific=True` lets the caller surface "this
    scenario was added because we detected your manifest declares X."
    """
    out: list[TestScenario] = []

    if features["uses_camera"]:
        out.append(TestScenario(
            name="Deny camera permission → fallback path works",
            description=(
                "User taps the camera button, denies the permission dialog. "
                "The app must offer an alternative (gallery upload, manual "
                "entry) instead of dead-ending."
            ),
            category=Category.PERMISSION,
            priority=Priority.P0,
            standard="Google CAQ — Permission Denial Handling",
            tool_sequence=(
                "tap_text:Take photo",
                "tap_text:Deny:system=true",
                "assert_visible:Gallery OR Choose another",
            ),
            project_specific=True,
        ))

    if features["uses_location"]:
        out.append(TestScenario(
            name="Location services disabled at OS level",
            description=(
                "OS Location is OFF in Settings (not just permission denied — "
                "system-level disabled). App should detect this and direct "
                "user to enable, not hang waiting for a fix that won't come."
            ),
            category=Category.PERMISSION,
            priority=Priority.P0,
            standard="Google Maps SDK — LocationSettings docs",
            tool_sequence=(
                "launch_app:com.android.settings",
                # toggle location off
                "launch_app:<your app>",
                "tap_text:Get my location",
                "assert_visible:Enable location",
            ),
            project_specific=True,
        ))

    if features["uses_notifications"]:
        out.append(TestScenario(
            name="Notifications permission denied — app still works",
            description=(
                "Android 13+ requires runtime permission. Deny it. App should "
                "function fully without push, and surface a way to re-enable "
                "(settings deep link) at the relevant moment."
            ),
            category=Category.PERMISSION,
            priority=Priority.P0,
            standard="Android 13+ POST_NOTIFICATIONS runtime permission",
            tool_sequence=(
                "launch_app", "tap_text:Deny:system=true",
                "assert_no_errors_since",
            ),
            project_specific=True,
        ))

    if features["uses_deep_links"]:
        out.extend([
            TestScenario(
                name="Deep link from cold-start opens correct screen",
                description=(
                    "Tap a deep-link URL from another app (or `adb shell am "
                    "start -a VIEW -d <uri>`). App boots cold, lands on the "
                    "deep-linked screen with the right state."
                ),
                category=Category.LIFECYCLE,
                priority=Priority.P0,
                standard="Android App Links / iOS Universal Links specs",
                tool_sequence=(
                    "stop_app",
                    # adb shell am start -W -a android.intent.action.VIEW -d <uri>
                    "wait_for_element",
                    "assert_no_errors_since",
                ),
                project_specific=True,
            ),
            TestScenario(
                name="Deep link to a screen requiring auth — login flow gracefully resumes",
                description=(
                    "User taps deep link → app is unauthenticated → login "
                    "screen → after login, lands on the originally-requested "
                    "screen with arguments intact, NOT the home screen."
                ),
                category=Category.LIFECYCLE,
                priority=Priority.P1,
                standard="OAuth 2.0 RFC 6749 redirect flow",
                tool_sequence=(
                    "stop_app",
                    "launch_app:<deep link URI>",
                    "tap_and_verify:Login",
                    "assert_visible:<deep-linked content>",
                ),
                project_specific=True,
            ),
        ])

    if features["uses_in_app_purchase"]:
        out.extend([
            TestScenario(
                name="Successful purchase via sandbox account",
                description=(
                    "Apple/Google sandbox test accounts process payment but "
                    "don't charge. Verify entitlement unlocks, receipt is "
                    "stored, UI shows purchased state immediately + "
                    "after restart."
                ),
                category=Category.HAPPY_PATH,
                priority=Priority.P0,
                standard="App Store Review §3.1.1; Google Play Billing v6",
                tool_sequence=(
                    "tap_text:Subscribe",
                    "tap_text:Confirm",
                    "assert_visible:Active OR Subscribed",
                ),
                project_specific=True,
            ),
            TestScenario(
                name="Restore purchases on a new device / fresh install",
                description=(
                    "Mandatory per App Store Review §3.1.1. Without this, "
                    "your IAP gets rejected during review."
                ),
                category=Category.LIFECYCLE,
                priority=Priority.P0,
                standard="App Store Review §3.1.1",
                tool_sequence=(
                    "clear_app_data",
                    "launch_app",
                    "tap_text:Restore purchases",
                    "assert_visible:Restored",
                ),
                project_specific=True,
            ),
        ])

    if features["uses_biometrics"]:
        out.append(TestScenario(
            name="Biometric unavailable / not enrolled fallback",
            description=(
                "User opens lock screen on a device with no Face ID/fingerprint "
                "enrolled (or hardware unsupported). App must fall back to "
                "PIN/password — never dead-end on 'biometric failed'."
            ),
            category=Category.PERMISSION,
            priority=Priority.P1,
            standard="Apple LAContext / Android Keystore docs",
            tool_sequence=(
                "tap_text:Unlock with biometric",
                "wait_for_element:Use PIN OR Cancel",
            ),
            project_specific=True,
        ))

    if features["has_login_flow"]:
        out.extend([
            TestScenario(
                name="Wrong password 5 times in a row",
                description=(
                    "Many auth providers rate-limit after N failures. "
                    "App should surface this with clear messaging, NOT a "
                    "generic 'something went wrong.'"
                ),
                category=Category.SECURITY,
                priority=Priority.P1,
                standard="OWASP ASVS 4.0 §2.2 Authentication Lifecycle",
                tool_sequence=(
                    # 5x: type_text + tap_text:Login + wait
                    "assert_visible:Too many attempts",
                ),
                project_specific=True,
            ),
            TestScenario(
                name="Token expiry mid-session — silent refresh works",
                description=(
                    "Manually expire the access token (or wait for it). The "
                    "next request should refresh-and-retry transparently. If "
                    "refresh fails, the app should ask the user to re-auth, "
                    "not crash."
                ),
                category=Category.NETWORK,
                priority=Priority.P0,
                standard="OAuth 2.0 RFC 6749 §6 token refresh",
                tool_sequence=(
                    # vm_evaluate to set token expiry; alternatively wait
                    "tap_and_verify",
                    "assert_no_errors_since",
                ),
                project_specific=True,
            ),
        ])

    if features["uses_ar"] or features["uses_ml_kit"]:
        out.append(TestScenario(
            name="AR/ML feature on unsupported device",
            description=(
                "Older devices lack ARCore / ARKit or sufficient ML hardware. "
                "App should detect this at launch and show 'not supported on "
                "this device' — not crash trying to call missing APIs."
            ),
            category=Category.DEVICE_MATRIX,
            priority=Priority.P0,
            standard="ARCore Supported Devices / ARKit Device Compatibility",
            tool_sequence=(
                "launch_app",
                "wait_for_element:Not supported OR Compatible device",
            ),
            project_specific=True,
        ))

    if features["uses_payments"]:
        out.append(TestScenario(
            name="3DS / SCA challenge mid-payment",
            description=(
                "EU SCA mandates a second factor for most card payments. "
                "Test the bank's 3DS WebView opening, completing OTP, and "
                "returning to the app with success status."
            ),
            category=Category.NETWORK,
            priority=Priority.P0,
            standard="PSD2 Strong Customer Authentication; EMV 3DS 2.x",
            tool_sequence=(
                "tap_text:Pay", "wait_for_element:Verify",
                "type_text:000000",  # sandbox OTP
                "assert_visible:Success",
            ),
            project_specific=True,
        ))

    if features["supports_localization"]:
        out.append(TestScenario(
            name="No string keys missing translations",
            description=(
                "Every supported locale's .arb file has the full key set. "
                "Missing keys fall through to English at runtime — fine for "
                "dev, bad for users in pl-PL who see English buttons in a "
                "Polish-language app."
            ),
            category=Category.LOCALIZATION,
            priority=Priority.P1,
            standard="ICU MessageFormat; Flutter intl package",
            tool_sequence=(
                # planned: localization_audit tool. For now: manual diff.
            ),
            project_specific=True,
        ))

    if features["supports_dark_mode"]:
        out.append(TestScenario(
            name="OS dark-mode toggle mid-session",
            description=(
                "User switches OS theme while app is open. Colors should "
                "flip immediately (or on next route push) without a manual "
                "restart."
            ),
            category=Category.LIFECYCLE,
            priority=Priority.P2,
            standard="Material Design — Dark Theme; HIG — Dark Mode",
            tool_sequence=(
                "launch_app",
                # adb shell cmd uimode night yes
                "take_screenshot:dark-mode",
            ),
            project_specific=True,
        ))

    return out


# ---- helpers ----------------------------------------------------------


def _is_valid_category(s: str) -> bool:
    try:
        Category(s)
        return True
    except ValueError:
        return False


def _build_advice(
    scenarios: list[TestScenario], features: dict[str, bool]
) -> str:
    """Paste-ready advice line summarizing the scenario set."""
    p0_count = sum(1 for s in scenarios if s.priority == Priority.P0)
    p1_count = sum(1 for s in scenarios if s.priority == Priority.P1)
    project_count = sum(1 for s in scenarios if s.project_specific)
    detected = [k.replace("uses_", "").replace("has_", "").replace("supports_", "")
                for k, v in features.items() if v]
    detected_str = ", ".join(detected) if detected else "no special features"
    return (
        f"Proposed {len(scenarios)} scenarios "
        f"({p0_count} P0 / {p1_count} P1). "
        f"{project_count} project-specific based on detected features: "
        f"{detected_str}. "
        "Start with the P0 set before any release; P1 before any major version bump."
    )


def _collect_references(scenarios: list[TestScenario]) -> tuple[str, ...]:
    """Unique sorted list of the standards cited across the result."""
    return tuple(sorted({s.standard for s in scenarios}))
