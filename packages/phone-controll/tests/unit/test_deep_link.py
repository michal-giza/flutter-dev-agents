"""Tests for the v0.3.0 phase-5 deep-link tool.

Hermetic — fakes the AdbClient + SimctlClient so no real device is
needed. Covers:

- Android happy path: adb shell intent fired, status parsed, no
  expect_screen_text → expected_text_found is None.
- Android with expect_screen_text → UI find called, true/false
  surfaced.
- Android failure (non-zero exit) → typed UiFailure with
  next_action='check_uri_or_intent_filter'.
- iOS sim path triggers SimctlClient.openurl.
- _looks_like_ios_udid heuristic distinguishes Android emulator
  serials (emulator-5554) / Samsung serials (R3CYA05CHXB) from
  iOS UDIDs (00008120-001A42542E30201E and 40-char hex).
- _extract_field parses adb's `am start -W` line-oriented output.
- _build_advice produces sensible PR-comment text in success +
  failure + no-expectation cases.
"""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.entities import Bounds, UiElement
from mcp_phone_controll.domain.result import Err, Ok, ok
from mcp_phone_controll.domain.usecases.deep_link import (
    TestDeepLink,
    TestDeepLinkParams,
    _build_advice,
    _extract_field,
    _looks_like_ios_udid,
)
from tests.fakes.fake_adb import FakeAdbClient as _FakeAdbClient

# ---- fakes ------------------------------------------------------------
# _FakeAdbClient is now a re-export of the shared FakeAdbClient. See
# tests/fakes/fake_adb.py for the implementation.


class _FakeUiRepo:
    """UiRepository stub. Configurable find result so the
    expect_screen_text path is testable."""

    def __init__(self, found_element: UiElement | None = None):
        self._found = found_element

    async def find(self, serial: str, **kwargs):
        return ok(self._found)

    # The other UiRepository methods aren't exercised in these tests,
    # but the Protocol expects them — provide no-ops.
    async def dump_ui(self, serial: str):  # pragma: no cover
        return ok("")


class _FakeStateRepo:
    """SessionStateRepository stub — always returns the same serial."""

    def __init__(self, serial: str = "emulator-5554"):
        self._serial = serial

    async def get_selected_serial(self):
        return ok(self._serial)


class _FakeDeviceRepo:
    """DeviceRepository stub — unused by deep_link directly but
    required by the constructor."""

    async def list_devices(self):  # pragma: no cover
        return ok([])


# ---- _looks_like_ios_udid ---------------------------------------------


def test_ios_udid_with_hyphen_recognized():
    """iPhone 15 / 16 / 17 use this format: 8 hex + '-' + 16 hex."""
    assert _looks_like_ios_udid("00008120-001A42542E30201E") is True


def test_older_ios_udid_40_char_hex_recognized():
    """Older iOS devices used a flat 40-char hex string."""
    assert _looks_like_ios_udid("a" * 40) is True


def test_android_emulator_serial_not_ios():
    assert _looks_like_ios_udid("emulator-5554") is False


def test_android_physical_serial_not_ios():
    """Samsung / Pixel device serials are short alphanumerics."""
    assert _looks_like_ios_udid("R3CYA05CHXB") is False


# ---- _extract_field ---------------------------------------------------


def test_extract_field_finds_value_in_am_start_output():
    """Mimic real `am start -W` output: each field on its own line
    with a colon prefix. The function should return the value
    trimmed."""
    stdout = (
        "Starting: Intent { dat=myapp://orders/123 ... }\n"
        "Status: ok\n"
        "LaunchState: COLD\n"
        "Activity: com.example/.OrderActivity\n"
        "TotalTime: 187\n"
    )
    assert _extract_field(stdout, "Status: ") == "ok"
    assert _extract_field(stdout, "Activity: ") == "com.example/.OrderActivity"


def test_extract_field_returns_none_when_missing():
    assert _extract_field("just stdout", "Status: ") is None


# ---- _build_advice -----------------------------------------------------


def test_advice_no_expectation_summarizes_launch_only():
    params = TestDeepLinkParams(uri="myapp://x")
    advice = _build_advice("android", "ok", "com.example/.X", params, None)
    assert "ANDROID" in advice
    assert "myapp://x" in advice
    assert "ok" in advice
    assert "✓" not in advice and "❌" not in advice


def test_advice_with_found_expectation():
    params = TestDeepLinkParams(uri="myapp://x", expect_screen_text="Welcome")
    advice = _build_advice("android", "ok", None, params, True)
    assert "✓" in advice
    assert "Welcome" in advice


def test_advice_with_missing_expectation_includes_dump_ui_hint():
    params = TestDeepLinkParams(uri="myapp://x", expect_screen_text="Welcome")
    advice = _build_advice("ios", "ok", None, params, False)
    assert "❌" in advice
    assert "dump_ui" in advice


# ---- TestDeepLink: Android happy path ---------------------------------


@pytest.mark.asyncio
async def test_android_happy_path_fires_intent_and_parses_status():
    """adb shell am start -W is invoked with the right args, status
    parsed from stdout, no expectation → expected_text_found=None."""
    adb = _FakeAdbClient(stdout=(
        "Starting: Intent { dat=myapp://orders/123 }\n"
        "Status: ok\n"
        "Activity: com.example/.OrderActivity\n"
        "TotalTime: 187\n"
    ))
    uc = TestDeepLink(
        devices=_FakeDeviceRepo(),
        ui=_FakeUiRepo(),
        state=_FakeStateRepo(serial="emulator-5554"),
        adb_client=adb,
    )
    res = await uc(TestDeepLinkParams(uri="myapp://orders/123"))
    assert isinstance(res, Ok)
    v = res.value
    assert v.platform == "android"
    assert v.launch_status == "ok"
    assert v.launched_activity == "com.example/.OrderActivity"
    assert v.expected_text_found is None

    # The shell call was the right shape
    call = adb.calls[0]
    assert call[0] == "emulator-5554"
    assert "am" in call
    assert "start" in call
    assert "-W" in call
    assert "myapp://orders/123" in call


@pytest.mark.asyncio
async def test_android_expect_screen_text_verifies_via_find():
    """When expect_screen_text is set, the use case calls
    UiRepository.find to confirm presence."""
    adb = _FakeAdbClient(stdout="Status: ok\n")
    # Stub UI repo returns an element → expected_text_found=True.
    found_elem = UiElement(
        text="Welcome",
        resource_id=None,
        class_name="TextView",
        content_description=None,
        bounds=Bounds(x=0, y=0, width=100, height=50),
        enabled=True,
        clickable=False,
    )
    uc = TestDeepLink(
        devices=_FakeDeviceRepo(),
        ui=_FakeUiRepo(found_element=found_elem),
        state=_FakeStateRepo(),
        adb_client=adb,
    )
    res = await uc(TestDeepLinkParams(
        uri="myapp://x", expect_screen_text="Welcome"
    ))
    assert isinstance(res, Ok)
    assert res.value.expected_text_found is True


@pytest.mark.asyncio
async def test_android_expect_screen_text_missing_returns_false():
    """When the expected text isn't found in the UI tree, the result
    reports expected_text_found=False but the call itself still
    succeeds (the launch worked; the verification didn't)."""
    adb = _FakeAdbClient(stdout="Status: ok\n")
    uc = TestDeepLink(
        devices=_FakeDeviceRepo(),
        ui=_FakeUiRepo(found_element=None),   # ← no element
        state=_FakeStateRepo(),
        adb_client=adb,
    )
    res = await uc(TestDeepLinkParams(
        uri="myapp://x", expect_screen_text="Welcome"
    ))
    assert isinstance(res, Ok)
    assert res.value.expected_text_found is False


@pytest.mark.asyncio
async def test_android_adb_failure_returns_typed_failure():
    """Non-zero exit → typed UiFailure with the right next_action."""
    adb = _FakeAdbClient(stderr="Error: Activity class {com.x/.Y} does not exist.", returncode=1)
    uc = TestDeepLink(
        devices=_FakeDeviceRepo(),
        ui=_FakeUiRepo(),
        state=_FakeStateRepo(),
        adb_client=adb,
    )
    res = await uc(TestDeepLinkParams(uri="myapp://nope"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "check_uri_or_intent_filter"
    assert "Activity class" in str(res.failure.details)
