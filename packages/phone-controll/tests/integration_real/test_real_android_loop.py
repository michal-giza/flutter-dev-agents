"""Real-device integration tests against a connected Android device/emulator.

Gated behind BOTH `MCP_REAL=1` (the slow-tests opt-in) and
`MCP_REAL_DEVICE=1` (the device-attached opt-in). Skipped silently in
normal CI. To run locally:

    # Boot any AVD or attach a USB device first, then:
    MCP_REAL=1 MCP_REAL_DEVICE=1 pytest tests/integration_real/test_real_android_loop.py -v

These tests close the long-standing gap (§7 item 5 of
docs/code-review-2026-05-15.md): all 425 hermetic tests use fakes, so
real-world breakage is only ever caught by manual screen-clicking.
This file exercises the three most-load-bearing live paths so a
regression that breaks an actual `adb shell screencap` round-trip is
caught before the user hits it.

What we DON'T do here:
- iOS — needs Xcode + pymobiledevice3 + WDA + a connected iPhone
  per-machine. Add `test_real_ios_loop.py` separately when a CI box
  has the iOS toolchain.
- flutter run --machine — the long-lived debug session is a
  multi-minute test; defer to a dedicated nightly job.
- multi-device parallelism — needs N devices; one-machine CI only.

This is the minimum-viable real-device floor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.container import build_runtime


@pytest.fixture(scope="module")
def runtime():
    """A real composition root with REAL infrastructure clients —
    not the fakes used by tests/unit/. Subprocesses are launched
    against real adb, real flutter, etc."""
    use_cases, dispatcher = build_runtime()
    return use_cases, dispatcher


@pytest.mark.asyncio
async def test_check_environment_against_real_toolchain(
    runtime, flutter_cli, adb_cli
):
    """check_environment must report adb green + flutter green on a
    machine where both are installed. If either is red, the local
    toolchain itself is broken — fix the dev box, not the test."""
    _, dispatcher = runtime
    res = await dispatcher.dispatch("check_environment", {})
    assert res["ok"], res
    checks = res["data"]["checks"]
    by_name = {c["name"]: c for c in checks}
    assert by_name["adb"]["ok"], by_name["adb"]
    assert by_name["flutter"]["ok"], by_name["flutter"]


@pytest.mark.asyncio
async def test_list_devices_returns_real_device(runtime, real_device_required):
    """list_devices against a real attached device should include it
    in the returned list with the right serial."""
    _, dispatcher = runtime
    res = await dispatcher.dispatch("list_devices", {})
    assert res["ok"], res
    serials = [d["serial"] for d in res["data"]]
    assert real_device_required in serials, (
        f"expected {real_device_required} in {serials}"
    )


@pytest.mark.asyncio
async def test_select_screenshot_release_round_trip(
    runtime, real_device_required, tmp_path: Path
):
    """End-to-end: select a real device, take a screenshot against it,
    verify the file exists and is a real PNG within our hard ceiling,
    release the lock. Catches any regression in:

      - device locking (cross-session)
      - the platform router (serial → adb vs pymobiledevice3)
      - real adb shell screencap
      - the image-cap pipeline against a real Android screen size
      - lock release on the way out
    """
    _, dispatcher = runtime

    serial = real_device_required
    try:
        res = await dispatcher.dispatch(
            "select_device", {"serial": serial, "force": True}
        )
        assert res["ok"], res

        shot = await dispatcher.dispatch(
            "take_screenshot", {"label": "real-loop-smoke"}
        )
        assert shot["ok"], shot
        path = Path(shot["data"])
        assert path.is_file(), f"screenshot path not on disk: {path}"

        # Verify it's a PNG within the hard ceiling — the safety net
        # plus per-use-case cap should always guarantee this.
        from mcp_phone_controll.data.image_capping import (
            _read_png_dimensions,
            is_within_cap,
        )

        dims = _read_png_dimensions(path)
        assert dims is not None, f"not a valid PNG: {path}"
        assert is_within_cap(path, max_dim=1900), (
            f"real-device screenshot exceeded hard ceiling: {dims} at {path}"
        )
    finally:
        # Always release. If the lock leaks, the next test run fails.
        await dispatcher.dispatch("release_device", {"serial": serial})
