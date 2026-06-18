"""Tap by selector — resolve + tap server-side in one call (v0.13.0 #1)."""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.entities import Bounds, UiElement
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.ui_input import Tap, TapParams
from tests.fakes.fake_repositories import (
    FakeSessionStateRepository,
    FakeUiRepository,
)

_SERIAL = "device123"


def _element(x=10, y=20, w=100, h=40) -> UiElement:
    return UiElement(
        text="Sign in",
        resource_id="com.example:id/btn_signin",
        class_name="android.widget.Button",
        content_description=None,
        bounds=Bounds(x=x, y=y, width=w, height=h),
        enabled=True,
        clickable=True,
    )


def _tap(found=None):
    ui = FakeUiRepository(found=found)
    state = FakeSessionStateRepository(serial=_SERIAL)
    return Tap(ui, state), ui


@pytest.mark.asyncio
async def test_coordinates_still_work():
    uc, ui = _tap()
    res = await uc(TapParams(x=300, y=500))
    assert isinstance(res, Ok)
    assert ui.taps == [("fake", "tap", _SERIAL, 300, 500)]


@pytest.mark.asyncio
async def test_text_routes_through_tap_text():
    uc, ui = _tap()
    res = await uc(TapParams(text="Rozumiem", exact=True))
    assert isinstance(res, Ok)
    assert ui.taps == [("fake", "tap_text", _SERIAL, "Rozumiem", True)]


@pytest.mark.asyncio
async def test_resource_id_resolves_and_taps_center():
    uc, ui = _tap(found=_element(x=10, y=20, w=100, h=40))
    res = await uc(TapParams(resource_id="com.example:id/btn_signin"))
    assert isinstance(res, Ok)
    # centre of [10,20]+100x40 → (60, 40)
    assert ui.taps == [("fake", "tap", _SERIAL, 60, 40)]


@pytest.mark.asyncio
async def test_class_name_resolves_and_taps_center():
    uc, ui = _tap(found=_element(x=0, y=0, w=200, h=100))
    res = await uc(TapParams(class_name="android.widget.Button"))
    assert isinstance(res, Ok)
    assert ui.taps == [("fake", "tap", _SERIAL, 100, 50)]


@pytest.mark.asyncio
async def test_selector_not_found_returns_capture_diagnostics():
    uc, ui = _tap(found=None)
    res = await uc(TapParams(resource_id="com.example:id/missing"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "capture_diagnostics"
    assert ui.taps == []  # never tapped a guessed coordinate


@pytest.mark.asyncio
async def test_no_target_is_invalid_argument_with_hint():
    uc, ui = _tap()
    res = await uc(TapParams())
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"
    # surfaces the structured-first hint + a corrected example
    assert "corrected_example" in res.failure.details
    assert ui.taps == []


@pytest.mark.asyncio
async def test_coordinates_take_precedence_over_selector():
    """If both are passed, coordinates win (unambiguous)."""
    uc, ui = _tap(found=_element())
    res = await uc(TapParams(x=5, y=7, resource_id="com.example:id/btn_signin"))
    assert isinstance(res, Ok)
    assert ui.taps == [("fake", "tap", _SERIAL, 5, 7)]


@pytest.mark.asyncio
async def test_only_x_without_y_falls_through_to_selector_or_error():
    """A lone x (no y) is not a valid coordinate tap — must not tap (x, None)."""
    uc, ui = _tap()
    res = await uc(TapParams(x=300))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"
    assert ui.taps == []
