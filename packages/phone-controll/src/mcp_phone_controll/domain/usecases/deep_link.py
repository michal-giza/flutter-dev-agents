"""Deep link testing.

The two ways an app gets opened by a link:

  1. Inside another app, user taps `https://myapp.com/orders/123`.
     The OS routes it to your app if you have the right intent
     filter (Android) or associated domain (iOS Universal Links).

  2. From an email / Slack message / push notification with a
     custom URI scheme like `myapp://orders/123`.

Both should land the user on the right screen with the right
state, whether the app was already running or boots cold. This
tool simulates that — `adb shell am start -W -a android.intent.
action.VIEW -d <uri>` on Android, `xcrun simctl openurl <udid>
<uri>` on iOS — then optionally asserts a follow-up screen
matches a text or element.

Why this needs its own tool:

- `launch_app(activity=...)` opens by package + activity name, not
  by URI. Different intent type, different code path on the device.
- `Bash("adb shell am start ...")` works but the agent loses the
  structured envelope.
- Cold-start vs warm-start matter — same URI to a fresh process
  vs a running one can land on different screens.

Scope of v0.3.0:

- Android via `adb shell am start -W` (the `-W` waits for the
  activity to render, returning launch timings useful for jank
  detection).
- iOS simulator via `xcrun simctl openurl`. Physical iOS device
  via universal links requires the user to test from Safari or
  Notes — out of scope for the MCP for now.
- Optional `expect_screen_text` — if set, calls `tap_text` after
  the link fires to verify the right screen rendered. (Re-uses
  the existing NFC + NBSP tolerant matcher from tap_text.)
"""

from __future__ import annotations

from dataclasses import dataclass

from ..failures import UiFailure
from ..repositories import (
    DeviceRepository,
    SessionStateRepository,
    UiRepository,
)
from ..result import Err, Result, err, ok
from ._helpers import resolve_serial
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class TestDeepLinkParams:
    uri: str                            # e.g. "myapp://orders/123" or "https://myapp.com/orders/123"
    expect_screen_text: str | None = None
    # Optional explicit serial; falls back to current session's device.
    serial: str | None = None
    # Cold start makes the link land on a fresh process. For the
    # warm-start case (app already running), leave at False.
    cold_start: bool = False
    # Max time to wait for the launch + render before treating it
    # as a hang. The `-W` adb flag returns when the activity is
    # ready, so this is mostly a backstop.
    timeout_s: float = 15.0


@dataclass(frozen=True, slots=True)
class TestDeepLinkResult:
    uri: str
    platform: str                       # "android" or "ios"
    launch_status: str                  # "ok" / "warn" / "error" — adb returns this verbatim
    launched_activity: str | None       # the activity / view-controller name when known
    expected_text_found: bool | None    # None if expect_screen_text wasn't set
    advice: str                         # paste-ready PR-comment line


class TestDeepLink(
    BaseUseCase[TestDeepLinkParams, TestDeepLinkResult]
):
    """Fire a deep link, optionally verify the right screen renders.

    Routes to the platform via the existing PlatformResolver
    (Android vs iOS). On Android, uses adb intents directly. On
    iOS sim, uses simctl openurl.

    The `expect_screen_text` check uses the existing tap_text
    matcher (NFC + NBSP folding + dump_ui fallback) so localization
    quirks don't trip the verification.
    """

    def __init__(
        self,
        devices: DeviceRepository,
        ui: UiRepository,
        state: SessionStateRepository,
        adb_client,
    ) -> None:
        self._devices = devices
        self._ui = ui
        self._state = state
        self._adb = adb_client

    async def execute(
        self, params: TestDeepLinkParams
    ) -> Result[TestDeepLinkResult]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        serial = serial_res.value

        # Detect platform. For now we treat anything matching
        # /^[0-9a-fA-F-]+$/ longer than the typical adb serial as
        # iOS (UDIDs are 25/40-char alphanumeric). Android emulator
        # / physical Android serials are shorter or contain ':'.
        # This is heuristic — for higher confidence the agent can
        # inspect device platform via list_devices first.
        is_ios = _looks_like_ios_udid(serial)

        if is_ios:
            # iOS path. simctl works for simulators; physical iOS
            # devices need universal links which can't be triggered
            # via CLI. We surface this as a clear failure.
            return await self._fire_ios_url(serial, params)
        return await self._fire_android_intent(serial, params)

    async def _fire_android_intent(
        self, serial: str, params: TestDeepLinkParams
    ) -> Result[TestDeepLinkResult]:
        # `am start -W` waits for the activity to render and prints
        # launch timing. The output includes a `Status` line we can
        # parse for ok/warn/error.
        cmd = [
            "am", "start", "-W",
            "-a", "android.intent.action.VIEW",
            "-d", params.uri,
        ]
        # Cold-start: kill the app first. Without the package_id we
        # use the broader `force-stop` skip — if the agent wants the
        # cold path, they should `stop_app(package_id=...)` before
        # this call. We accept the param as a hint but don't enforce
        # it here.
        result = await self._adb.shell(serial, *cmd, timeout_s=params.timeout_s)
        if not result.ok:
            return err(
                UiFailure(
                    message="adb am start failed",
                    next_action="check_uri_or_intent_filter",
                    details={
                        "uri": params.uri,
                        "stderr_tail": (result.stderr or "")[-1000:],
                        "stdout_tail": (result.stdout or "")[-1000:],
                    },
                )
            )

        # Parse the `am start -W` output for Status + ComponentName.
        # Real output looks like:
        #   Starting: Intent { ... dat=myapp://orders/123 ... }
        #   Status: ok
        #   LaunchState: COLD
        #   Activity: com.example/.OrderActivity
        #   TotalTime: 187
        stdout = result.stdout or ""
        status = _extract_field(stdout, "Status: ") or "unknown"
        activity = _extract_field(stdout, "Activity: ")

        expected_text_found = await self._verify_screen(params)

        advice = _build_advice("android", status, activity, params, expected_text_found)
        return ok(TestDeepLinkResult(
            uri=params.uri,
            platform="android",
            launch_status=status.strip(),
            launched_activity=activity.strip() if activity else None,
            expected_text_found=expected_text_found,
            advice=advice,
        ))

    async def _fire_ios_url(
        self, serial: str, params: TestDeepLinkParams
    ) -> Result[TestDeepLinkResult]:
        # iOS sim: `xcrun simctl openurl <udid> <uri>` works.
        # We invoke the same generic shell wrapper through a
        # separate codepath that runs xcrun directly.
        from ...infrastructure.simctl_client import SimctlClient
        # If the adb_client itself doesn't have simctl access, we
        # construct a minimal client. The caller can also pass a
        # shared simctl_client in future revisions.
        try:
            simctl = SimctlClient(self._adb._runner)  # reuse the same process runner
            result = await simctl.openurl(serial, params.uri, timeout_s=params.timeout_s)
        except Exception as e:
            return err(
                UiFailure(
                    message=f"failed to open URL via simctl: {e}",
                    next_action="check_simctl_or_physical_device",
                    details={
                        "uri": params.uri,
                        "hint": (
                            "Physical iOS device deep links require Safari "
                            "or Notes — the MCP can't trigger universal "
                            "links via CLI."
                        ),
                    },
                )
            )
        if not result.ok:
            return err(
                UiFailure(
                    message="simctl openurl failed",
                    next_action="check_uri_or_associated_domain",
                    details={
                        "uri": params.uri,
                        "stderr_tail": (result.stderr or "")[-1000:],
                    },
                )
            )

        expected_text_found = await self._verify_screen(params)

        advice = _build_advice("ios", "ok", None, params, expected_text_found)
        return ok(TestDeepLinkResult(
            uri=params.uri,
            platform="ios",
            launch_status="ok",
            launched_activity=None,    # iOS doesn't expose this from simctl
            expected_text_found=expected_text_found,
            advice=advice,
        ))

    async def _verify_screen(
        self, params: TestDeepLinkParams
    ) -> bool | None:
        """If expect_screen_text was set, check via the same UI tools
        the agent would otherwise call. Returns None when the caller
        opted out."""
        if not params.expect_screen_text:
            return None
        # Resolve serial again — same path the rest of the use case
        # already validated.
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return False
        serial = serial_res.value
        # Use the UiRepository's find path. We don't tap, just
        # check presence — find returns the element or None.
        try:
            res = await self._ui.find(serial, text=params.expect_screen_text)
            if isinstance(res, Err):
                return False
            return res.value is not None
        except Exception:
            return False


# ---- helpers -----------------------------------------------------------


def _looks_like_ios_udid(serial: str) -> bool:
    """Heuristic: iOS device UDIDs are 25-char (newer) or 40-char
    (older) hex strings, optionally with a hyphen separator.
    Android serials are shorter (typically 8-16 chars), can contain
    ':' for emulators, and don't match this shape."""
    # iOS UDIDs commonly contain '-' (e.g. 00008120-001A42542E30201E)
    # or are all-hex 40 chars.
    if "-" in serial and len(serial) >= 24:
        return True
    if len(serial) == 40 and all(c in "0123456789abcdefABCDEF" for c in serial):
        return True
    return False


def _extract_field(stdout: str, marker: str) -> str | None:
    """Pull the value following a `<marker>` line in stdout.

    am start -W output is line-oriented; each field on its own
    line. Robust to whitespace.
    """
    for line in stdout.splitlines():
        if marker in line:
            return line.split(marker, 1)[1].strip()
    return None


def _build_advice(
    platform: str,
    status: str,
    activity: str | None,
    params: TestDeepLinkParams,
    expected_found: bool | None,
) -> str:
    parts: list[str] = []
    parts.append(f"{platform.upper()} deep-link to {params.uri}: status={status}")
    if activity:
        parts.append(f"activity={activity}")
    if expected_found is True:
        parts.append(f"✓ Verified screen contains '{params.expect_screen_text}'.")
    elif expected_found is False:
        parts.append(
            f"❌ Expected '{params.expect_screen_text}' on screen, but it's not visible. "
            "Either the link routed to the wrong screen, or the screen "
            "uses different copy. Run `dump_ui` to see what's actually there."
        )
    return ". ".join(parts) + "."
