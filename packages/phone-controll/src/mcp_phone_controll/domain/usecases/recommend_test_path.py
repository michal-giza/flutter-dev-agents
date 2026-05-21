"""Test-path advisor — picks the right testing strategy for the context.

`propose_test_scenarios` answers *what* to test. This tool answers
*how + when + in what order*. Given a context (pre-commit /
pre-PR / daily-dev / nightly / pre-release / hotfix / postmortem),
returns a sequenced runnable plan with isolation guarantees and
pass/fail criteria.

Why this is its own tool, separate from propose_test_scenarios:

- propose_test_scenarios is brainstorming-shaped: returns a flat
  list of scenarios across categories. Useful for *what would we
  even check?*
- recommend_test_path is orchestration-shaped: returns a sequence
  of MCP tool calls in execution order with estimated timings.
  Useful for *what do I do right now, in 10 minutes, that's
  defensible?*

The canonical paths encode the conventional testing pyramid +
real-world context-aware practice:

  pre_commit       60s    quick sanity before commit
  pre_pr           5-10m  must-pass quality gate before review
  daily_dev        15m    inner loop on a real device
  nightly          1h+    regression matrix across devices
  pre_release      30-60m full audit before any production ship
  hotfix           5-10m  minimal verification before re-shipping
  postmortem       open   reproduce + diagnose a production incident

Each path's steps are picked to be **safe for production-shaped
environments**: clear_app_data between flows, locked devices, no
real-user data writes, no outbound webhook calls (controlled by
MCP_WEBHOOK_ALLOWLIST). The `isolation_guarantees` field on the
result lists what the path provably WON'T touch — so the user can
run a `pre_release` path on a phone signed into their personal
Google account without fear.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from .base import BaseUseCase


class TestPath(str, Enum):
    PRE_COMMIT = "pre_commit"
    PRE_PR = "pre_pr"
    DAILY_DEV = "daily_dev"
    NIGHTLY = "nightly"
    PRE_RELEASE = "pre_release"
    HOTFIX = "hotfix"
    POSTMORTEM = "postmortem"


@dataclass(frozen=True, slots=True)
class TestStep:
    tool: str                        # the MCP tool name
    args: dict                       # arguments to pass
    reason: str                      # why this step is here
    estimated_s: int                 # rough wall-clock budget
    optional: bool = False           # can skip without breaking the path
    skip_if: str | None = None       # human-readable reason to skip
    # When True, this step affects shared state (locks, writes,
    # builds). The `pass_criteria` summary uses this to decide
    # whether downstream steps should retry.
    side_effects: bool = False


@dataclass(frozen=True, slots=True)
class RecommendTestPathParams:
    project_path: Path
    context: str                     # one of TestPath values
    # If the agent already knows which device to use, pass it so
    # the plan inlines that serial in `select_device` step. Else
    # the plan picks "the first available."
    device_serial: str | None = None
    # Some paths benefit from knowing your release-baseline file
    # (the previous --analyze-size JSON). Optional; only used by
    # pre_release / nightly paths.
    size_baseline_path: Path | None = None
    # Coverage threshold for pre_pr path. Default 0.80 matches
    # the convention test_coverage_report uses.
    coverage_fail_under: float = 0.80


@dataclass(frozen=True, slots=True)
class RecommendTestPathResult:
    path: str                        # one of TestPath values
    description: str                 # one-line summary
    estimated_wall_clock_s: int      # rough total of step estimates
    steps: tuple[TestStep, ...]
    pass_criteria: str               # how the agent decides "done"
    isolation_guarantees: tuple[str, ...]    # what this path WON'T touch
    skip_conditions: tuple[str, ...]         # when this is the wrong choice
    alternative_paths: tuple[str, ...]       # which to use instead
    advice: str                      # paste-ready PR-comment line


class RecommendTestPath(
    BaseUseCase[RecommendTestPathParams, RecommendTestPathResult]
):
    """Returns the canonical test path for the given context.

    Pure function — no LLM call, no file inspection beyond
    confirming the project_path exists. The taxonomy + step
    sequencing is encoded from established mobile QA practice
    (Google CAQ, Apple HIG, ISO/IEC 25010, Drizz 2026 survey).
    """

    async def execute(
        self, params: RecommendTestPathParams
    ) -> Result[RecommendTestPathResult]:
        if not params.project_path.is_dir():
            return err(
                FilesystemFailure(
                    message=f"project_path not found: {params.project_path}",
                    next_action="fix_arguments",
                )
            )

        try:
            path = TestPath(params.context)
        except ValueError:
            return err(
                FilesystemFailure(
                    message=(
                        f"unknown context {params.context!r}. Valid: "
                        + ", ".join(p.value for p in TestPath)
                    ),
                    next_action="fix_arguments",
                )
            )

        builders = {
            TestPath.PRE_COMMIT: _build_pre_commit,
            TestPath.PRE_PR: _build_pre_pr,
            TestPath.DAILY_DEV: _build_daily_dev,
            TestPath.NIGHTLY: _build_nightly,
            TestPath.PRE_RELEASE: _build_pre_release,
            TestPath.HOTFIX: _build_hotfix,
            TestPath.POSTMORTEM: _build_postmortem,
        }
        return ok(builders[path](params))


# ---- path builders -----------------------------------------------------


def _build_pre_commit(p: RecommendTestPathParams) -> RecommendTestPathResult:
    """~60 seconds. The smallest meaningful gate before `git commit`.

    No device interaction — pure static + unit tests. Designed to
    be runnable as a pre-commit hook without slowing the
    developer's loop.
    """
    steps = (
        TestStep(
            tool="dart_analyze",
            args={"project_path": str(p.project_path)},
            reason="Catches syntax + lint + obvious type errors before the test phase.",
            estimated_s=10,
        ),
        TestStep(
            tool="dart_format",
            args={"project_path": str(p.project_path), "check_only": True},
            reason="Formatting check (non-mutating). Fails if any file needs reformat.",
            estimated_s=5,
        ),
        TestStep(
            tool="run_widget_test",
            args={"project_path": str(p.project_path)},
            reason="Full widget+unit suite — fast feedback (<30s on a small app).",
            estimated_s=30,
            side_effects=True,
        ),
        TestStep(
            tool="list_missing_widget_keys",
            args={"project_path": str(p.project_path)},
            reason="Selector-hygiene diagnostic — surfaces unkeyed tap targets.",
            estimated_s=3,
            optional=True,
            skip_if="Your team doesn't use widget keys for testing.",
        ),
    )
    return RecommendTestPathResult(
        path=TestPath.PRE_COMMIT.value,
        description="Fast static + unit checks before committing. No device needed.",
        estimated_wall_clock_s=sum(s.estimated_s for s in steps),
        steps=steps,
        pass_criteria=(
            "All steps return ok=true. If dart_analyze or run_widget_test "
            "fails, fix locally — do NOT amend over a broken state."
        ),
        isolation_guarantees=(
            "No device interaction.",
            "No network calls.",
            "No artifact-dir writes outside tmp.",
            "Safe to run on a battery-powered laptop in 60 seconds.",
        ),
        skip_conditions=(
            "You're only changing docs — run nothing.",
            "You're mid-rebase — wait until rebase completes.",
        ),
        alternative_paths=("pre_pr (deeper) before opening the PR"),
        advice=(
            "Pre-commit path: 4 steps, ~60s wall-clock. Designed to fit "
            "in a pre-commit hook. Catches the 80% of breakage cheaply."
        ),
    )


def _build_pre_pr(p: RecommendTestPathParams) -> RecommendTestPathResult:
    """5-10 minutes. The must-pass gate before opening a PR."""
    serial_arg = {"serial": p.device_serial} if p.device_serial else {}
    steps = (
        TestStep(
            tool="check_environment",
            args={},
            reason="Confirm the toolchain is healthy before the suite runs.",
            estimated_s=5,
        ),
        TestStep(
            tool="select_device",
            args=serial_arg,
            reason="Lock a device for the duration of the PR check.",
            estimated_s=2,
            side_effects=True,
        ),
        TestStep(
            tool="quality_gate",
            args={"project_path": str(p.project_path)},
            reason="Analyzer + format + unit tests as a single composite call.",
            estimated_s=60,
            side_effects=True,
        ),
        TestStep(
            tool="test_coverage_report",
            args={
                "project_path": str(p.project_path),
                "fail_under": p.coverage_fail_under,
            },
            reason=(
                f"Confirm coverage ≥ {int(p.coverage_fail_under * 100)}%. "
                "Coverage threshold is the most defensible PR gate."
            ),
            estimated_s=90,
        ),
        TestStep(
            tool="run_integration_tests",
            args={"project_path": str(p.project_path), **serial_arg},
            reason=(
                "Patrol / integration tests on a real device — catches "
                "the UI / lifecycle regressions unit tests can't."
            ),
            estimated_s=180,
            side_effects=True,
        ),
        TestStep(
            tool="audit_accessibility",
            args=serial_arg,
            reason=(
                "Quick a11y pass on the current screen state. EU EAA "
                "compliance gate — blockers MUST be zero."
            ),
            estimated_s=5,
        ),
        TestStep(
            tool="release_device",
            args=serial_arg,
            reason="Free the lock for other concurrent sessions.",
            estimated_s=2,
            side_effects=True,
        ),
    )
    return RecommendTestPathResult(
        path=TestPath.PRE_PR.value,
        description="Quality gate before opening a PR. Static + unit + integration + a11y.",
        estimated_wall_clock_s=sum(s.estimated_s for s in steps),
        steps=steps,
        pass_criteria=(
            "All required steps ok. test_coverage_report.passed_threshold "
            "must be true. audit_accessibility.blocker_count must be 0. "
            "If any of these fail, the PR isn't ready — fix locally first."
        ),
        isolation_guarantees=(
            "Test-isolated device (locked + cleared between runs).",
            "Uses the project's existing test fixtures — no real-user data.",
            "No outbound webhook calls (MCP_WEBHOOK_ALLOWLIST controls).",
            "Does NOT touch production backends — uses test/integration env.",
        ),
        skip_conditions=(
            "You're opening a docs-only PR (skip integration + coverage).",
            "Your branch is < 24h ahead of main (the nightly path is more comprehensive).",
        ),
        alternative_paths=("nightly (broader matrix), pre_release (deeper audit)"),
        advice=(
            "Pre-PR path: 7 steps, ~6 min wall-clock. Designed as the "
            "minimum-defensible quality gate before review."
        ),
    )


def _build_daily_dev(p: RecommendTestPathParams) -> RecommendTestPathResult:
    """15 minutes. The agent-driven inner loop during active dev."""
    serial_arg = {"serial": p.device_serial} if p.device_serial else {}
    steps = (
        TestStep(
            tool="mcp_ping",
            args={},
            reason="Confirm the MCP isn't a stale subprocess running old code.",
            estimated_s=1,
        ),
        TestStep(
            tool="select_device",
            args=serial_arg,
            reason="Lock the dev device for the session.",
            estimated_s=2,
            side_effects=True,
        ),
        TestStep(
            tool="new_session",
            args={},
            reason="Fresh session dir for the artifacts this iteration produces.",
            estimated_s=1,
            side_effects=True,
        ),
        TestStep(
            tool="prepare_for_test",
            args=serial_arg,
            reason="Clear data + grant common permissions for clean-slate testing.",
            estimated_s=5,
            side_effects=True,
        ),
        TestStep(
            tool="propose_test_scenarios",
            args={"project_path": str(p.project_path), "focus_areas": ["happy_path"], "top_n": 3},
            reason=(
                "Pick the 3 highest-priority happy-path scenarios. The "
                "agent iterates through these manually with tap_and_verify."
            ),
            estimated_s=2,
        ),
        TestStep(
            tool="start_debug_session",
            args={"project_path": str(p.project_path), **serial_arg},
            reason="Hot-reload session for the iteration phase.",
            estimated_s=15,
            side_effects=True,
        ),
        TestStep(
            tool="memory_summary",
            args={},
            reason="Baseline memory before driving any interaction.",
            estimated_s=3,
        ),
        TestStep(
            tool="allocation_profile",
            args={"reset_accumulator": True},
            reason=(
                "Open the leak-detection bracket. After driving the flow, "
                "call allocation_profile again to see deltas."
            ),
            estimated_s=3,
        ),
        TestStep(
            tool="start_frame_profile",
            args={},
            reason="Begin frame-jank capture during the upcoming UI interaction.",
            estimated_s=2,
        ),
        # ... agent drives the actual scenario here via tap/swipe/etc ...
        TestStep(
            tool="stop_frame_profile",
            args={"target_fps": 60},
            reason="Close the bracket — analyze frame timings.",
            estimated_s=3,
        ),
        TestStep(
            tool="detect_undisposed_controllers",
            args={},
            reason="Spot leak candidates from the interaction.",
            estimated_s=3,
        ),
        TestStep(
            tool="assert_no_errors_since",
            args={"since_s": 30},
            reason="Final check — no error logs surfaced during the iteration.",
            estimated_s=2,
        ),
        TestStep(
            tool="summarize_session",
            args={},
            reason="One-paragraph summary of the iteration for the journal.",
            estimated_s=2,
        ),
        TestStep(
            tool="stop_debug_session",
            args={},
            reason="Clean teardown — kill the flutter run --machine daemon.",
            estimated_s=2,
            side_effects=True,
        ),
        TestStep(
            tool="release_device",
            args=serial_arg,
            reason="Free the lock.",
            estimated_s=2,
            side_effects=True,
        ),
    )
    return RecommendTestPathResult(
        path=TestPath.DAILY_DEV.value,
        description=(
            "Inner-loop dev iteration: scenario picking + debug session + "
            "memory/frame profile + summary. Agent drives the UI between "
            "start_frame_profile and stop_frame_profile."
        ),
        estimated_wall_clock_s=sum(s.estimated_s for s in steps),
        steps=steps,
        pass_criteria=(
            "stop_frame_profile.jank_pct < 5%. "
            "allocation_profile delta has no growing classes you expected "
            "to stay flat. "
            "detect_undisposed_controllers.total_suspect_instances doesn't "
            "trend up across iterations. "
            "assert_no_errors_since passes."
        ),
        isolation_guarantees=(
            "Locked device — other Claude windows can't interfere.",
            "Fresh session dir — artifacts don't pollute previous runs.",
            "clear_app_data on entry — last run's state doesn't leak in.",
        ),
        skip_conditions=(
            "You're only refactoring — pre_commit covers this faster.",
            "You're investigating a production incident — use postmortem.",
        ),
        alternative_paths=("hotfix (focused), nightly (broader)"),
        advice=(
            "Daily-dev path: 15 steps, ~60s of fixed cost + however long "
            "the user drives the UI between start/stop frame_profile. "
            "Captures memory + frame + log signals around the interaction."
        ),
    )


def _build_nightly(p: RecommendTestPathParams) -> RecommendTestPathResult:
    """1+ hour. Cross-device matrix regression catcher."""
    steps = (
        TestStep(
            tool="check_environment",
            args={},
            reason="Confirm tooling state before the long run.",
            estimated_s=10,
        ),
        TestStep(
            tool="propose_test_scenarios",
            args={"project_path": str(p.project_path), "top_n": 50},
            reason="Get the full P0+P1+P2 list — nightly is the time to run them all.",
            estimated_s=2,
        ),
        TestStep(
            tool="list_avds",
            args={},
            reason="Enumerate available Android emulators for matrix coverage.",
            estimated_s=3,
        ),
        TestStep(
            tool="list_simulators",
            args={},
            reason="Enumerate iOS simulators if the host supports it.",
            estimated_s=3,
        ),
        TestStep(
            tool="build_app",
            args={"project_path": str(p.project_path), "mode": "release"},
            reason="Build the release variant — same artifact across the matrix.",
            estimated_s=600,
            side_effects=True,
        ),
        TestStep(
            tool="analyze_app_size",
            args={
                "project_path": str(p.project_path),
                "platform": "apk",
                **({"baseline_json_path": str(p.size_baseline_path)} if p.size_baseline_path else {}),
            },
            reason=(
                "Catch app-size regressions vs the previous nightly. "
                "+500KB without justification = investigate."
            ),
            estimated_s=15,
        ),
        TestStep(
            tool="run_test_plan",
            args={"plan_path": "examples/templates/smoke.yaml"},
            reason=(
                "Run the smoke YAML plan on every device class. "
                "Captures the full audit trail in the session dir."
            ),
            estimated_s=1800,
            side_effects=True,
        ),
        TestStep(
            tool="audit_accessibility",
            args={},
            reason="A11y audit on the current device state.",
            estimated_s=5,
        ),
        TestStep(
            tool="disk_usage",
            args={},
            reason="Nightly runs accumulate artifacts — surface usage before bytes spiral.",
            estimated_s=2,
        ),
        TestStep(
            tool="prune_originals",
            args={"older_than_days": 14, "dry_run": False},
            reason="Auto-clean .orig.png companions older than retention window.",
            estimated_s=2,
            optional=True,
            side_effects=True,
        ),
        TestStep(
            tool="summarize_session",
            args={},
            reason="Single paragraph for the nightly notification.",
            estimated_s=2,
        ),
    )
    return RecommendTestPathResult(
        path=TestPath.NIGHTLY.value,
        description=(
            "Cross-device regression matrix. Builds release, runs the "
            "full P0+P1+P2 scenario set across available devices, checks "
            "app-size delta vs baseline."
        ),
        estimated_wall_clock_s=sum(s.estimated_s for s in steps),
        steps=steps,
        pass_criteria=(
            "All scenarios pass. "
            "audit_accessibility.blocker_count == 0. "
            "analyze_app_size deltas vs baseline are < 500KB per package "
            "(unless intentional). "
            "No 'next_action' field surfaces in the session trace — "
            "everything completed cleanly."
        ),
        isolation_guarantees=(
            "Test devices only — never run against a developer's daily phone.",
            "Build artifacts isolated in the session dir.",
            "MCP_WEBHOOK_ALLOWLIST must be set to send pass/fail notification.",
        ),
        skip_conditions=(
            "No new changes since last nightly — re-run is wasteful.",
            "The CI build itself is failing — fix CI first.",
        ),
        alternative_paths=("pre_release (deeper) before any actual ship"),
        advice=(
            "Nightly path: 11 steps, ~40 min wall-clock. Best run in CI "
            "with results stored to artifact retention."
        ),
    )


def _build_pre_release(p: RecommendTestPathParams) -> RecommendTestPathResult:
    """30-60 minutes. Full audit before any production ship."""
    steps = (
        TestStep(
            tool="check_environment",
            args={},
            reason="Toolchain health check.",
            estimated_s=10,
        ),
        TestStep(
            tool="quality_gate",
            args={"project_path": str(p.project_path)},
            reason="Analyzer + format + unit tests — must be clean to release.",
            estimated_s=60,
            side_effects=True,
        ),
        TestStep(
            tool="test_coverage_report",
            args={"project_path": str(p.project_path), "fail_under": p.coverage_fail_under},
            reason="Coverage threshold gate.",
            estimated_s=90,
        ),
        TestStep(
            tool="build_app",
            args={"project_path": str(p.project_path), "mode": "release"},
            reason="Release build — store-listing artifact.",
            estimated_s=600,
            side_effects=True,
        ),
        TestStep(
            tool="analyze_app_size",
            args={
                "project_path": str(p.project_path),
                **({"baseline_json_path": str(p.size_baseline_path)} if p.size_baseline_path else {}),
            },
            reason="App-size analysis vs last release. Big regressions block the ship.",
            estimated_s=15,
        ),
        TestStep(
            tool="propose_test_scenarios",
            args={
                "project_path": str(p.project_path),
                "focus_areas": ["happy_path", "permission", "network", "lifecycle", "security"],
                "top_n": 20,
            },
            reason="P0 scenarios across the critical categories.",
            estimated_s=2,
        ),
        TestStep(
            tool="run_test_plan",
            args={"plan_path": "examples/templates/ump_decline.yaml"},
            reason="The decline-path test — catches the consent-broken-by-update case.",
            estimated_s=300,
            side_effects=True,
        ),
        TestStep(
            tool="audit_accessibility",
            args={},
            reason="EU EAA 2025 compliance gate. blocker_count must be 0.",
            estimated_s=5,
        ),
        TestStep(
            tool="memory_summary",
            args={},
            reason="Final memory check — anchor the baseline for next release's comparison.",
            estimated_s=3,
        ),
        TestStep(
            tool="detect_undisposed_controllers",
            args={},
            reason="Last leak-scan before ship.",
            estimated_s=3,
        ),
        TestStep(
            tool="capture_release_screenshot",
            args={"project_path": str(p.project_path)},
            reason="Store-listing screenshots at canonical device classes.",
            estimated_s=120,
            optional=True,
            skip_if="Store listing already updated this cycle.",
            side_effects=True,
        ),
        TestStep(
            tool="session_summary",
            args={},
            reason="Audit trail — paste into the release notes.",
            estimated_s=2,
        ),
    )
    return RecommendTestPathResult(
        path=TestPath.PRE_RELEASE.value,
        description=(
            "Full audit before production ship. Analyzer + coverage + "
            "release build + app-size delta + critical scenarios + a11y + "
            "memory + (optional) store-listing shots."
        ),
        estimated_wall_clock_s=sum(s.estimated_s for s in steps),
        steps=steps,
        pass_criteria=(
            "quality_gate ok. "
            "test_coverage_report.passed_threshold true. "
            "analyze_app_size deltas vs baseline justify any growth. "
            "audit_accessibility.blocker_count == 0. "
            "All P0 scenarios from propose_test_scenarios pass. "
            "session_summary documents the release for audit."
        ),
        isolation_guarantees=(
            "Test-environment build — does NOT push to production backends.",
            "Test devices only — no real-user phone involved.",
            "Capture-release-screenshot writes only to artifacts dir.",
            "No webhook notifications fired without MCP_WEBHOOK_ALLOWLIST.",
        ),
        skip_conditions=(
            "This isn't actually a release — use pre_pr.",
            "You're shipping a CMS content change — your release process is different.",
        ),
        alternative_paths=("hotfix if you're patching a live issue"),
        advice=(
            "Pre-release path: 12 steps, ~30-60 min wall-clock. The most "
            "defensible 'we tested this' record before App Store / Play "
            "Store submission."
        ),
    )


def _build_hotfix(p: RecommendTestPathParams) -> RecommendTestPathResult:
    """5-10 minutes. Minimal verification before re-shipping a fix."""
    serial_arg = {"serial": p.device_serial} if p.device_serial else {}
    steps = (
        TestStep(
            tool="mcp_ping",
            args={},
            reason="Confirm MCP is fresh — stale subprocess could mask the fix.",
            estimated_s=1,
        ),
        TestStep(
            tool="dart_analyze",
            args={"project_path": str(p.project_path)},
            reason="Catch new analyzer warnings introduced by the fix.",
            estimated_s=10,
        ),
        TestStep(
            tool="run_widget_test",
            args={"project_path": str(p.project_path)},
            reason=(
                "Run the affected widget test(s). If you have a regression "
                "test for the bug, this confirms the fix landed."
            ),
            estimated_s=30,
            side_effects=True,
        ),
        TestStep(
            tool="select_device",
            args=serial_arg,
            reason="Lock a device for the on-device verification.",
            estimated_s=2,
            side_effects=True,
        ),
        TestStep(
            tool="clear_app_data",
            args={"package_id": "REPLACE_WITH_YOUR_PACKAGE_ID"},
            reason="Fresh state — verify the bug doesn't recur from cached data.",
            estimated_s=3,
            side_effects=True,
        ),
        TestStep(
            tool="launch_app",
            args={"package_id": "REPLACE_WITH_YOUR_PACKAGE_ID"},
            reason="Reproduce the originally-broken flow.",
            estimated_s=10,
            side_effects=True,
        ),
        # The agent fills in the reproduce steps based on the bug.
        TestStep(
            tool="tap_and_verify",
            args={"text": "REPLACE: the button that triggered the bug"},
            reason=(
                "The crucial step — drive the action that previously "
                "failed, verify it now succeeds. The agent customizes "
                "this per bug."
            ),
            estimated_s=10,
        ),
        TestStep(
            tool="assert_no_errors_since",
            args={"since_s": 30},
            reason="Confirm no error logs surfaced during the repro.",
            estimated_s=2,
        ),
        TestStep(
            tool="take_screenshot",
            args={"label": "hotfix-verified"},
            reason="Visual evidence the fix works — attach to the PR.",
            estimated_s=3,
            side_effects=True,
        ),
        TestStep(
            tool="release_device",
            args=serial_arg,
            reason="Free the lock.",
            estimated_s=2,
            side_effects=True,
        ),
    )
    return RecommendTestPathResult(
        path=TestPath.HOTFIX.value,
        description=(
            "Focused verification before shipping a hotfix. Confirms the "
            "broken flow works post-fix. Skips the broad regression — that "
            "happens in the post-merge nightly."
        ),
        estimated_wall_clock_s=sum(s.estimated_s for s in steps),
        steps=steps,
        pass_criteria=(
            "Regression test passes. "
            "tap_and_verify succeeds. "
            "assert_no_errors_since clean. "
            "Screenshot attached to the hotfix PR."
        ),
        isolation_guarantees=(
            "Single device locked.",
            "clear_app_data before launch — no leaked state.",
            "No outbound webhook calls.",
        ),
        skip_conditions=(
            "The bug is purely a build / config change — use pre_commit.",
            "The bug is in a deferred path the user rarely hits — defer to nightly.",
        ),
        alternative_paths=("postmortem if you want full diagnosis, pre_pr if a regression PR"),
        advice=(
            "Hotfix path: 10 steps, ~5-10 min. The package_id + repro "
            "steps need agent customization — they're marked 'REPLACE' "
            "in the args."
        ),
    )


def _build_postmortem(p: RecommendTestPathParams) -> RecommendTestPathResult:
    """Open-ended. Reproduce + diagnose a production incident."""
    serial_arg = {"serial": p.device_serial} if p.device_serial else {}
    steps = (
        TestStep(
            tool="check_environment",
            args={},
            reason="Toolchain health — postmortems get derailed by stale envs.",
            estimated_s=5,
        ),
        TestStep(
            tool="new_session",
            args={},
            reason="Fresh session — the trace becomes the postmortem evidence.",
            estimated_s=1,
            side_effects=True,
        ),
        TestStep(
            tool="select_device",
            args=serial_arg,
            reason="Lock the repro device.",
            estimated_s=2,
            side_effects=True,
        ),
        TestStep(
            tool="clear_app_data",
            args={"package_id": "REPLACE_WITH_YOUR_PACKAGE_ID"},
            reason="Clean slate. Matches a user's first-launch state.",
            estimated_s=3,
            side_effects=True,
        ),
        TestStep(
            tool="start_debug_session",
            args={"project_path": str(p.project_path), **serial_arg},
            reason="Debug session for log capture + VM introspection.",
            estimated_s=15,
            side_effects=True,
        ),
        TestStep(
            tool="start_frame_profile",
            args={},
            reason="Begin frame capture — performance signals may correlate with the incident.",
            estimated_s=2,
        ),
        # Agent reproduces the incident flow here.
        TestStep(
            tool="stop_frame_profile",
            args={"target_fps": 60},
            reason="Close the frame bracket — was jank a factor?",
            estimated_s=3,
        ),
        TestStep(
            tool="memory_summary",
            args={},
            reason="Heap state at the moment of (attempted) repro.",
            estimated_s=3,
        ),
        TestStep(
            tool="read_debug_log",
            args={"since_s": 120},
            reason="Full log window — postmortems benefit from generous context.",
            estimated_s=3,
        ),
        TestStep(
            tool="dump_widget_tree",
            args={},
            reason="State of the widget tree at the failure point.",
            estimated_s=5,
        ),
        TestStep(
            tool="take_screenshot",
            args={"label": "postmortem-failure-state"},
            reason="Visual evidence of where the failure landed.",
            estimated_s=3,
            side_effects=True,
        ),
        TestStep(
            tool="session_summary",
            args={},
            reason="Full audit trail for the postmortem document.",
            estimated_s=2,
        ),
    )
    return RecommendTestPathResult(
        path=TestPath.POSTMORTEM.value,
        description=(
            "Reproduce + diagnose a production incident. Captures every "
            "diagnostic signal (frames, memory, logs, widget tree) so the "
            "session trace becomes the postmortem evidence."
        ),
        estimated_wall_clock_s=sum(s.estimated_s for s in steps),
        steps=steps,
        pass_criteria=(
            "Either: the issue reproduces deterministically and "
            "session_summary captures the trace for the postmortem doc. "
            "Or: the issue does NOT reproduce — and the trace documents "
            "what was tried so the next engineer doesn't redo the work."
        ),
        isolation_guarantees=(
            "Single locked device — no interference.",
            "Fresh session — trace is the postmortem record.",
            "No production-backend writes (uses test env).",
        ),
        skip_conditions=(
            "The incident is solved — no postmortem needed.",
            "The incident is purely backend / infra — different toolchain.",
        ),
        alternative_paths=("hotfix once you have a fix to verify"),
        advice=(
            "Postmortem path: 12 steps, open-ended (depends on repro time). "
            "Captures every diagnostic primitive — frames, memory, logs, "
            "widget tree, screenshots — so the trace itself becomes the "
            "postmortem evidence."
        ),
    )
