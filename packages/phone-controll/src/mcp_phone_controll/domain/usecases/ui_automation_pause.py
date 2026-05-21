"""Paired tools to silence the openatx uiautomator2 helper.

The Problem
-----------

The openatx `uiautomator2` Python library (which our
`UiAutomator2UiRepository` uses for tap / swipe / type_text /
dump_ui on Android) installs two helper APKs on the device:

  com.github.uiautomator        — the actual UI driver
  com.github.uiautomator.test   — the instrumentation runner

On a real device with aggressive backgrounding (e.g. Samsung
Galaxy), these helpers stay docile in the background. On Android
emulators (AVDs), the OS doesn't background them as
aggressively, so when the keepalive ping cycles, the helper's
UI process briefly grabs foreground — pushing the app under
observation back, breaking deep-screen captures and
re-launching the AUT.

Killing the PIDs is futile: the helper's foreground service
gets respawned on the next health-ping from any uiautomator2
client (including our own). The only reliable way to silence it
is `pm disable-user`, which prevents the package from running
at all until re-enabled.

The Solution: paired bracket tools
-----------------------------------

  pause_ui_automation()  — disables both helper packages, records
                           prior state so resume can no-op if
                           they were already disabled.
  resume_ui_automation() — re-enables them and waits briefly for
                           the package manager to settle. After
                           this, the next uiautomator2 call will
                           re-init (re-installing if needed).

The pair follows the same bracket invariant as
start_frame_profile / stop_frame_profile and start_debug_session
/ stop_debug_session: every paused state MUST be resumed.

When to use this
----------------

  ✓ On AVDs, before a series of read-only captures (screenshots,
    dump_ui via screencap, OCR) where the app must stay
    foreground. Pause first, do the captures, resume after.
  ✓ When `audit_accessibility` or a manual flow needs the AUT
    to render clean screens without the helper popping forward.
  ✓ During recording_*: pause before start_recording, resume
    after stop_recording, so the recorded video doesn't capture
    the helper's UI briefly flashing.

  ✗ Don't use it for tap / swipe / type_text flows — those NEED
    uiautomator2 to work. If you paused before such an op,
    you'll see UiFailure (no driver available).
  ✗ Don't use it on physical Samsung / Pixel devices where the
    helper backgrounds correctly — adds 1-3s of resume latency
    for no benefit.

Failure modes handled
---------------------

  • If uiautomator2 was never installed on the device, both
    tools return ok with `was_enabled=false` (no-op).
  • If `pm disable-user` is rejected (rooted device with custom
    rules), returns AdbFailure with the stderr.
  • If the device is offline mid-operation, returns AdbFailure
    with details; the helper may be left in either state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..failures import AdbFailure
from ..repositories import SessionStateRepository
from ..result import Err, Result, err, ok
from ._helpers import resolve_serial
from .base import BaseUseCase

# The two packages installed by openatx uiautomator2.
_HELPER_PACKAGES = (
    "com.github.uiautomator",
    "com.github.uiautomator.test",
)


@dataclass(frozen=True, slots=True)
class PauseUiAutomationParams:
    serial: str | None = None


@dataclass(frozen=True, slots=True)
class PauseUiAutomationResult:
    serial: str
    package_states: dict[str, bool]   # {package: was_enabled_before_pause}
    paused: tuple[str, ...]           # packages newly disabled this call
    already_disabled: tuple[str, ...]  # packages that were already off
    not_installed: tuple[str, ...]    # packages absent from the device
    advice: str


@dataclass(frozen=True, slots=True)
class ResumeUiAutomationParams:
    serial: str | None = None
    # Brief settle wait after `pm enable` returns; lets the
    # package manager rebuild its component map before the next
    # uiautomator2 init tries to connect.
    settle_ms: int = 800


@dataclass(frozen=True, slots=True)
class ResumeUiAutomationResult:
    serial: str
    resumed: tuple[str, ...]
    already_enabled: tuple[str, ...]
    not_installed: tuple[str, ...]
    latency_ms: int
    advice: str


class PauseUiAutomation(
    BaseUseCase[PauseUiAutomationParams, PauseUiAutomationResult]
):
    """Disables the openatx uiautomator2 helper packages."""

    def __init__(
        self,
        state: SessionStateRepository,
        adb_client,
    ) -> None:
        self._state = state
        self._adb = adb_client

    async def execute(
        self, params: PauseUiAutomationParams
    ) -> Result[PauseUiAutomationResult]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        serial = serial_res.value

        package_states: dict[str, bool] = {}
        paused: list[str] = []
        already_disabled: list[str] = []
        not_installed: list[str] = []

        for pkg in _HELPER_PACKAGES:
            state_res = await _package_state(self._adb, serial, pkg)
            if isinstance(state_res, Err):
                return state_res
            status = state_res.value
            if status == "absent":
                not_installed.append(pkg)
                package_states[pkg] = False
                continue
            package_states[pkg] = status == "enabled"
            if status == "enabled":
                disable = await self._adb.shell(
                    serial,
                    "pm", "disable-user", "--user", "0", pkg,
                )
                if not disable.ok:
                    return err(AdbFailure(
                        message=f"pm disable-user failed for {pkg}",
                        details={
                            "stdout": disable.stdout,
                            "stderr": disable.stderr,
                        },
                    ))
                paused.append(pkg)
            else:
                already_disabled.append(pkg)

        advice = _build_pause_advice(
            paused, already_disabled, not_installed
        )
        return ok(PauseUiAutomationResult(
            serial=serial,
            package_states=package_states,
            paused=tuple(paused),
            already_disabled=tuple(already_disabled),
            not_installed=tuple(not_installed),
            advice=advice,
        ))


class ResumeUiAutomation(
    BaseUseCase[ResumeUiAutomationParams, ResumeUiAutomationResult]
):
    """Re-enables the openatx uiautomator2 helper packages."""

    def __init__(
        self,
        state: SessionStateRepository,
        adb_client,
    ) -> None:
        self._state = state
        self._adb = adb_client

    async def execute(
        self, params: ResumeUiAutomationParams
    ) -> Result[ResumeUiAutomationResult]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        serial = serial_res.value

        resumed: list[str] = []
        already_enabled: list[str] = []
        not_installed: list[str] = []

        for pkg in _HELPER_PACKAGES:
            state_res = await _package_state(self._adb, serial, pkg)
            if isinstance(state_res, Err):
                return state_res
            status = state_res.value
            if status == "absent":
                not_installed.append(pkg)
                continue
            if status == "enabled":
                already_enabled.append(pkg)
                continue
            enable = await self._adb.shell(
                serial,
                "pm", "enable", pkg,
            )
            if not enable.ok:
                return err(AdbFailure(
                    message=f"pm enable failed for {pkg}",
                    details={
                        "stdout": enable.stdout,
                        "stderr": enable.stderr,
                    },
                ))
            resumed.append(pkg)

        settle = max(0, params.settle_ms)
        if resumed and settle > 0:
            await asyncio.sleep(settle / 1000.0)

        advice = _build_resume_advice(
            resumed, already_enabled, not_installed
        )
        return ok(ResumeUiAutomationResult(
            serial=serial,
            resumed=tuple(resumed),
            already_enabled=tuple(already_enabled),
            not_installed=tuple(not_installed),
            latency_ms=settle if resumed else 0,
            advice=advice,
        ))


# ============================================================
# Helpers
# ============================================================


async def _package_state(
    adb_client, serial: str, package: str,
) -> Result[str]:
    """Returns 'enabled', 'disabled', or 'absent'.

    Uses `cmd package list packages -e <pkg>` to detect enabled
    state directly, with a fallback `pm list packages` check to
    distinguish 'disabled' from 'absent'.
    """
    # Is the package installed at all?
    listed = await adb_client.shell(
        serial, "pm", "list", "packages", package,
    )
    if not listed.ok:
        return err(AdbFailure(
            message="pm list packages failed",
            details={
                "stdout": listed.stdout,
                "stderr": listed.stderr,
            },
        ))
    if f"package:{package}" not in listed.stdout:
        return ok("absent")

    # Installed — is it enabled?
    enabled_list = await adb_client.shell(
        serial, "pm", "list", "packages", "-e", package,
    )
    if not enabled_list.ok:
        return err(AdbFailure(
            message="pm list packages -e failed",
            details={
                "stdout": enabled_list.stdout,
                "stderr": enabled_list.stderr,
            },
        ))
    if f"package:{package}" in enabled_list.stdout:
        return ok("enabled")
    return ok("disabled")


def _build_pause_advice(
    paused: list[str], already_disabled: list[str],
    not_installed: list[str],
) -> str:
    parts: list[str] = []
    if paused:
        parts.append(f"Paused {len(paused)} helper package(s).")
    if already_disabled:
        parts.append(
            f"{len(already_disabled)} already disabled (no-op)."
        )
    if not_installed:
        parts.append(
            "uiautomator2 helper not installed — nothing to pause."
        )
    if not parts:
        parts.append("No uiautomator2 helper present on device.")
    parts.append(
        "Call resume_ui_automation() once you're done with the "
        "quiet-capture window."
    )
    return " ".join(parts)


def _build_resume_advice(
    resumed: list[str], already_enabled: list[str],
    not_installed: list[str],
) -> str:
    parts: list[str] = []
    if resumed:
        parts.append(f"Resumed {len(resumed)} helper package(s).")
    if already_enabled:
        parts.append(
            f"{len(already_enabled)} already enabled (no-op)."
        )
    if not_installed:
        parts.append(
            "uiautomator2 helper not installed — nothing to resume."
        )
    if not parts:
        parts.append("No uiautomator2 helper present on device.")
    if resumed:
        parts.append(
            "Next tap/swipe/dump_ui call will re-init the driver "
            "(~1-3s warmup)."
        )
    return " ".join(parts)
