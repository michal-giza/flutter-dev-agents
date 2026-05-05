"""CapabilitiesProvider — answers describe_capabilities for autonomous agents."""

from __future__ import annotations

from importlib.util import find_spec

from ...domain.entities import Capability, CapabilityReport
from ...domain.repositories import CapabilitiesProvider
from ...domain.result import Result, ok


_PLAN_SCHEMA = {
    "version": "phone-controll/v1",
    "kind": "TestPlan",
    "valid_phases": [
        "PRE_FLIGHT",
        "CLEAN",
        "LAUNCHED",
        "<NAME>_GATE",
        "UNDER_TEST",
        "VERDICT_DECLINED",
        "VERDICT_BLOCKED",
        "OPEN_IDE",
        "DEV_SESSION_START",
        "HOT_RELOAD",
        "DEV_SESSION_STOP",
    ],
    "valid_driver_kinds": [
        "patrol_test", "flutter_test", "tap_text", "noop",
        "dev_session_action", "read_debug_log",
    ],
    "phase_requirements": {
        "PRE_FLIGHT": {"required": [], "optional": []},
        "CLEAN": {"required": ["package_id"]},
        "LAUNCHED": {"required": ["package_id"], "optional": ["wait_for_key", "wait_for_text", "timeout_s"]},
        "<NAME>_GATE": {"required": ["driver"], "optional": ["planned_outcome", "capture"]},
        "UNDER_TEST": {"required": ["driver"], "optional": ["capture"]},
        "VERDICT_DECLINED": {"required": [], "optional": ["capture"]},
        "VERDICT_BLOCKED": {"required": [], "optional": ["capture"]},
        "OPEN_IDE": {"required": [], "optional": ["ide", "new_window"]},
        "DEV_SESSION_START": {"required": [], "optional": ["mode", "flavor", "target"]},
        "HOT_RELOAD": {"required": [], "optional": ["full_restart", "capture"]},
        "DEV_SESSION_STOP": {"required": [], "optional": []},
    },
    "driver_kinds": {
        "patrol_test": {
            "needs": ["target", "project_path"],
            "summary": "Run a Patrol test file via the patrol CLI. Drives by widget Keys (locale-independent).",
        },
        "flutter_test": {
            "needs": ["target", "project_path"],
            "summary": (
                "Run a plain `flutter test` (with --reporter=json). Use when the project "
                "uses integration_test without Patrol."
            ),
        },
        "tap_text": {
            "needs": ["target"],
            "summary": "Tap a system-UI element by visible text. SYSTEM UI ONLY (Settings, ATT, permission dialogs).",
        },
        "noop": {
            "needs": [],
            "summary": "No-op driver — useful for plan scaffolding or capture-only phases.",
        },
    },
    "minimal_plan_yaml": (
        "apiVersion: phone-controll/v1\n"
        "kind: TestPlan\n"
        "metadata: { name: smoke }\n"
        "spec:\n"
        "  device: { platform: android, pool: any }\n"
        "  project: { path: . }\n"
        "  phases:\n"
        "    - phase: PRE_FLIGHT\n"
        "    - phase: CLEAN\n"
        "      package_id: com.your.app\n"
        "    - phase: LAUNCHED\n"
        "      package_id: com.your.app\n"
        "      wait_for_key: splashLogo\n"
        "      timeout_s: 15\n"
        "    - phase: UNDER_TEST\n"
        "      driver:\n"
        "        kind: flutter_test          # or patrol_test\n"
        "        target: integration_test/auth_test.dart\n"
        "      capture: [screenshot, logs]\n"
        "  report: { format: json }\n"
    ),
    "templates": [
        "examples/templates/smoke.yaml",
        "examples/templates/flutter_test_smoke.yaml",
        "examples/templates/ump_decline.yaml",
        "examples/templates/ar_anchor.yaml",
    ],
    "notes": [
        "VERDICT_BLOCKED is auto-injected by the executor when a phase fails — do not declare it as a planned phase.",
        "VERDICT_DECLINED is a planned terminal — declare it after a *_GATE phase with planned_outcome: decline.",
        "Phases ending in _GATE are user-defined gate names (UMP_GATE, ATT_GATE, PERM_CAMERA_GATE, ...) — they all require a driver.",
        "Single-phase plans (e.g. just PRE_FLIGHT) are valid — useful for setup-only flows.",
    ],
}


class StaticCapabilitiesProvider(CapabilitiesProvider):
    """Static + lightweight: introspects optional packages once, no I/O."""

    async def describe(self) -> Result[CapabilityReport]:
        cv2_present = find_spec("cv2") is not None
        fastapi_present = find_spec("fastapi") is not None
        capabilities = (
            Capability(name="patrol", available=True, detail="Flutter widget-Key driving"),
            Capability(name="adb", available=True, detail="Android lifecycle + UI + logs"),
            Capability(
                name="pymobiledevice3",
                available=True,
                detail="iOS device discovery + tunnel-routed services",
            ),
            Capability(
                name="vision",
                available=cv2_present,
                detail="OpenCV (compare_screenshot, detect_markers, infer_pose)"
                if cv2_present
                else "install with: uv pip install -e \".[ar]\"",
            ),
            Capability(
                name="http_adapter",
                available=fastapi_present,
                detail="OpenAI-compat HTTP API for autonomous agents"
                if fastapi_present
                else "install with: uv pip install -e \".[http]\"",
            ),
            Capability(
                name="test_plans",
                available=True,
                detail="declarative YAML plans via run_test_plan",
            ),
            Capability(
                name="session_trace",
                available=True,
                detail="every tool call recorded; query via session_summary",
            ),
        )
        vision_ops = (
            "compare_screenshot",
            "detect_markers",
            "wait_for_marker",
            "infer_camera_pose",
        )
        return ok(
            CapabilityReport(
                platforms=("android", "ios"),
                test_frameworks=("patrol", "flutter"),
                gates_handled=("UMP", "ATT", "runtime_permission"),
                vision_ops=vision_ops if cv2_present else (),
                capabilities=capabilities,
                known_limits=(
                    "iOS developer-tier services may need Xcode iOS-version-matched DDI",
                    "screen recording is Android-only",
                    "WebDriverAgent must be built once per iOS device for UI driving",
                    "AR/Vision tests must run on physical devices — emulators/simulators give canned input",
                ),
                plan_schema=_PLAN_SCHEMA,
            )
        )
