"""Real-bug-driven tests for the Android tap path.

Field reports from a testing session against a Galaxy S25:
  1. `tap_text("Rozumiem")` / `tap_text("Podczas używania aplikacji")`
     fails — Polish diacritics weren't matching. NFC normalisation +
     UI-dump fallback fix.
  2. `tap(x,y)` occasionally drops on Samsung One UI. `adb shell
     input tap` fix.

These tests pin both fixes so a future refactor doesn't silently
regress.

Hermetic: we fake the uiautomator2 device + the adb client. No real
phone, no real adb invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_phone_controll.data.repositories.uiautomator2_ui_repository import (
    UiAutomator2UiRepository,
    _find_bounds_for_text,
    _normalise,
    _normalise_loose,
)

# ---- helpers -----------------------------------------------------------


@dataclass
class _FakeAdbResult:
    ok: bool = True
    stdout: str = ""
    stderr: str = ""


class _FakeSelector:
    """Mimics uiautomator2's `d(text=...)` selector object surface."""

    def __init__(self, exists: bool, click_raises: Exception | None = None):
        self._exists = exists
        self._click_raises = click_raises
        self.clicked = False

    @property
    def exists(self) -> bool:
        return self._exists

    def click(self):
        if self._click_raises:
            raise self._click_raises
        self.clicked = True


class _FakeDevice:
    """Slim stand-in for the uiautomator2 device. The constructor
    takes everything the tests need to script its behaviour."""

    def __init__(
        self,
        selector_for_text: dict[str, _FakeSelector] | None = None,
        click_raises: Exception | None = None,
        ui_dump: str = "",
    ):
        self._selectors = selector_for_text or {}
        self._click_raises = click_raises
        self._ui_dump = ui_dump
        self.click_calls: list[tuple[int, int]] = []

    def __call__(self, **kwargs):
        # uiautomator2 selectors come from `d(text=...)` or `d(textContains=...)`.
        key = kwargs.get("text") or kwargs.get("textContains") or ""
        if key in self._selectors:
            return self._selectors[key]
        return _FakeSelector(exists=False)

    def click(self, x: int, y: int):
        if self._click_raises:
            raise self._click_raises
        self.click_calls.append((x, y))

    def dump_hierarchy(self) -> str:
        return self._ui_dump


class _FakeU2Factory:
    def __init__(self, device: _FakeDevice):
        self._device = device

    async def get(self, serial: str):
        return self._device


def _adb_with_manufacturer(name: str) -> MagicMock:
    """An AdbClient stub whose `get_prop(_, ro.product.manufacturer)`
    returns `name`. `shell(...)` always succeeds."""
    adb = MagicMock()
    adb.get_prop = AsyncMock(
        return_value=_FakeAdbResult(ok=True, stdout=name)
    )
    adb.shell = AsyncMock(return_value=_FakeAdbResult(ok=True))
    return adb


# ---- normalisation -----------------------------------------------------


def test_normalise_collapses_decomposed_to_nfc():
    """Letters with diacritics have two valid Unicode encodings: a
    single precomposed codepoint (NFC) OR a base letter + a combining
    mark (NFD). `_normalise` must collapse both to the NFC form so
    selector matching works.

    Concrete case: "é" can be U+00E9 (precomposed) OR
    "e" (U+0065) + U+0301 (combining acute, NFD). Without NFC
    normalisation, these are unequal strings, and uiautomator2's
    selector matches by byte-equality.
    """
    precomposed = "café"  # NFC — one codepoint for "é"
    decomposed = "café"  # NFD — "e" + combining acute
    # Different byte representations of the same visual string.
    assert precomposed != decomposed
    assert len(precomposed) == 4
    assert len(decomposed) == 5
    # After normalising, both collapse to the same NFC form.
    assert _normalise(precomposed) == _normalise(decomposed) == "café"


def test_normalise_polish_diacritics_passthrough():
    """The Polish examples from the bug report — already in NFC form
    when typed normally — should pass through unchanged."""
    for word in ("Rozumiem", "używania", "Podczas używania aplikacji"):
        assert _normalise(word) == word


def test_normalise_strips_padding():
    assert _normalise("  Rozumiem  ") == "Rozumiem"


def test_find_bounds_for_text_matches_after_nfc():
    """A UI-dump XML node with the NFC form `Rozumiem` should match
    even if the agent passed the decomposed form."""
    xml = '<node text="Rozumiem" bounds="[10,20][110,80]" />'
    # Pass the decomposed version that uiautomator2 might fail to
    # match natively.
    bounds = _find_bounds_for_text(xml, "Rozumiem", exact=True)
    assert bounds is not None
    assert bounds.x == 10 and bounds.y == 20
    assert bounds.width == 100 and bounds.height == 60


def test_find_bounds_for_text_polish_diacritics():
    """The original bug repro: `Podczas używania aplikacji` exact
    match through the dump scan."""
    target = "Podczas używania aplikacji"
    xml = f'<node text="{target}" bounds="[0,100][720,180]" />'
    bounds = _find_bounds_for_text(xml, target, exact=True)
    assert bounds is not None
    assert bounds.width == 720


def test_find_bounds_for_text_returns_none_when_no_match():
    xml = '<node text="Other text" bounds="[0,0][100,100]" />'
    assert _find_bounds_for_text(xml, "Rozumiem", exact=True) is None


# ---- loose-match fallback for Android localization quirks -------------


def test_normalise_loose_folds_nbsp_to_ascii_space():
    """Android's Polish localization emits NO-BREAK SPACE (U+00A0)
    between words for typography. Visually identical to ASCII space
    but breaks byte-eq matching. The loose-normaliser folds them."""
    with_nbsp = "Podczas używania aplikacji"
    with_ascii = "Podczas używania aplikacji"
    assert with_nbsp != with_ascii  # bytes differ
    assert _normalise_loose(with_nbsp) == _normalise_loose(with_ascii)


def test_normalise_loose_folds_narrow_nbsp_and_thin_space():
    """French/Polish localizations also emit U+202F (NNBSP) and
    U+2009 (thin space) as word separators."""
    cases = [
        "Podczas używania aplikacji",
        "Podczas używania aplikacji",
    ]
    ref = _normalise_loose("Podczas używania aplikacji")
    for c in cases:
        assert _normalise_loose(c) == ref


def test_normalise_loose_strips_zero_width_chars():
    """ZWSP / word-joiner / BOM occasionally appear from translation
    tools. They render invisibly — should be stripped, not folded
    to a space (otherwise we'd insert phantom spaces)."""
    assert _normalise_loose("Rozu​miem") == "Rozumiem"
    assert _normalise_loose("﻿Rozumiem") == "Rozumiem"


def test_normalise_loose_collapses_internal_whitespace_runs():
    """Pretty-printed XML dumps sometimes have multiple spaces or
    tabs inside attribute values. Collapse those."""
    assert _normalise_loose("Podczas   używania\taplikacji") == (
        "Podczas używania aplikacji"
    )


def test_find_bounds_matches_nbsp_separated_polish_dialog():
    """The actual field failure: Android renders the permission
    dialog button as `"Podczas używania aplikacji"` but the dump XML
    encodes it with NBSP between words. Agent passes ASCII spaces.
    Strict scan misses; loose scan must catch it."""
    xml = (
        '<node text="Podczas używania aplikacji" '
        'bounds="[40,1800][680,1900]" />'
    )
    bounds = _find_bounds_for_text(
        xml, "Podczas używania aplikacji", exact=True
    )
    assert bounds is not None
    assert bounds.x == 40 and bounds.y == 1800


def test_find_bounds_loose_match_is_case_insensitive_in_substring_mode():
    """Agents reliably type "rozumiem" or "ROZUMIEM" expecting it to
    match the button labelled "Rozumiem". Strict mode keeps casing
    intact, loose mode case-folds for substring matching only."""
    xml = '<node text="Rozumiem" bounds="[10,20][110,80]" />'
    assert _find_bounds_for_text(xml, "rozumiem", exact=False) is not None
    assert _find_bounds_for_text(xml, "ROZUMIEM", exact=False) is not None


def test_find_bounds_strict_match_still_preferred_over_loose():
    """If both a strict-match and a loose-match node exist, the
    strict one wins — don't let case-folding accidentally pick a
    wrong target when there's an exact one available."""
    xml = (
        '<node text="rozumiem (cancel)" bounds="[0,0][100,50]" />'
        '<node text="Rozumiem" bounds="[200,200][400,250]" />'
    )
    bounds = _find_bounds_for_text(xml, "Rozumiem", exact=True)
    assert bounds is not None
    # Strict match wins → the second node's bounds.
    assert bounds.x == 200 and bounds.y == 200


def test_find_bounds_for_text_falls_back_to_content_desc():
    """Some Flutter buttons surface text only via `content-desc`
    (Semantics.label). The fallback path must check both."""
    xml = '<node content-desc="Rozumiem" bounds="[5,5][95,55]" />'
    bounds = _find_bounds_for_text(xml, "Rozumiem", exact=True)
    assert bounds is not None
    assert bounds.x == 5


# ---- tap_text path -----------------------------------------------------


@pytest.mark.asyncio
async def test_tap_text_via_selector_first_path_succeeds():
    sel = _FakeSelector(exists=True)
    dev = _FakeDevice(selector_for_text={"Rozumiem": sel})
    repo = UiAutomator2UiRepository(_FakeU2Factory(dev), adb_client=None)

    res = await repo.tap_text("SERIAL", "Rozumiem", exact=True)
    assert res.is_ok
    assert sel.clicked is True


@pytest.mark.asyncio
async def test_tap_text_falls_back_to_ui_dump_when_selector_misses():
    """The actual reported failure mode: uiautomator2's selector says
    `exists=False` for `Rozumiem`. The fallback path scans the dump,
    finds the node, taps by coordinates."""
    xml = '<node text="Rozumiem" bounds="[100,200][300,260]" />'
    dev = _FakeDevice(
        selector_for_text={"Rozumiem": _FakeSelector(exists=False)},
        ui_dump=xml,
    )
    repo = UiAutomator2UiRepository(_FakeU2Factory(dev), adb_client=None)

    res = await repo.tap_text("SERIAL", "Rozumiem", exact=True)
    assert res.is_ok
    # Tapped at centre of the bounds.
    assert dev.click_calls == [(200, 230)]


@pytest.mark.asyncio
async def test_tap_text_emits_structured_failure_when_truly_not_found():
    """When neither path finds the text, the agent gets a structured
    next_action it can switch on, not a generic exception."""
    dev = _FakeDevice(selector_for_text={}, ui_dump="<hierarchy/>")
    repo = UiAutomator2UiRepository(_FakeU2Factory(dev), adb_client=None)

    res = await repo.tap_text("SERIAL", "DoesNotExist", exact=True)
    assert not res.is_ok
    assert res.failure.next_action == "check_text_or_use_dump_ui"
    assert res.failure.details["requested"] == "DoesNotExist"


# ---- tap(x,y) path -----------------------------------------------------


@pytest.mark.asyncio
async def test_tap_uses_uiautomator2_on_non_samsung():
    dev = _FakeDevice()
    adb = _adb_with_manufacturer("google")  # Pixel
    repo = UiAutomator2UiRepository(_FakeU2Factory(dev), adb_client=adb)

    res = await repo.tap("SERIAL", 100, 200)
    assert res.is_ok
    assert dev.click_calls == [(100, 200)]
    # adb shell input tap was NOT called for non-Samsung.
    adb.shell.assert_not_awaited()


@pytest.mark.asyncio
async def test_tap_prefers_adb_on_samsung():
    """The headline fix: Samsung devices get adb-tap by default,
    even when uiautomator2 would succeed."""
    dev = _FakeDevice()
    adb = _adb_with_manufacturer("samsung")
    repo = UiAutomator2UiRepository(_FakeU2Factory(dev), adb_client=adb)

    res = await repo.tap("SERIAL-S25", 540, 1200)
    assert res.is_ok
    # adb was called, uiautomator2's click() was NOT.
    adb.shell.assert_awaited_once_with("SERIAL-S25", "input", "tap", "540", "1200")
    assert dev.click_calls == []


@pytest.mark.asyncio
async def test_tap_env_override_forces_adb(monkeypatch):
    """`MCP_ANDROID_PREFER_ADB_TAP=1` forces adb on every device,
    even Pixels."""
    monkeypatch.setenv("MCP_ANDROID_PREFER_ADB_TAP", "1")
    dev = _FakeDevice()
    adb = _adb_with_manufacturer("google")  # would otherwise use u2
    repo = UiAutomator2UiRepository(_FakeU2Factory(dev), adb_client=adb)

    res = await repo.tap("PIXEL-9", 50, 50)
    assert res.is_ok
    adb.shell.assert_awaited_once()
    assert dev.click_calls == []


@pytest.mark.asyncio
async def test_tap_falls_back_to_adb_when_u2_raises():
    """When uiautomator2 raises mid-call (the silent-drop pattern),
    fall back to adb instead of propagating the exception."""
    dev = _FakeDevice(click_raises=RuntimeError("accessibility event dropped"))
    adb = _adb_with_manufacturer("google")  # not preferred-adb
    repo = UiAutomator2UiRepository(_FakeU2Factory(dev), adb_client=adb)

    res = await repo.tap("SERIAL", 540, 1200)
    assert res.is_ok  # adb saved us
    adb.shell.assert_awaited_once()


@pytest.mark.asyncio
async def test_tap_returns_error_when_no_adb_fallback_and_u2_raises():
    """Without an adb client, uiautomator2 failures still surface as
    structured UiFailures — no silent crash."""
    dev = _FakeDevice(click_raises=RuntimeError("dropped"))
    repo = UiAutomator2UiRepository(_FakeU2Factory(dev), adb_client=None)

    res = await repo.tap("SERIAL", 1, 2)
    assert not res.is_ok
    assert "dropped" in res.failure.message


@pytest.mark.asyncio
async def test_manufacturer_lookup_is_cached():
    """`getprop` is cheap but we'd rather not call it on every tap.
    Verify the per-serial cache holds."""
    dev = _FakeDevice()
    adb = _adb_with_manufacturer("samsung")
    repo = UiAutomator2UiRepository(_FakeU2Factory(dev), adb_client=adb)

    await repo.tap("SERIAL-S25", 100, 100)
    await repo.tap("SERIAL-S25", 200, 200)
    await repo.tap("SERIAL-S25", 300, 300)
    # Only one getprop across three taps.
    assert adb.get_prop.await_count == 1
