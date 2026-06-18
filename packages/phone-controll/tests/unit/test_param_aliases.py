"""Param-name aliases for common agent guesses (v0.14.0 #8)."""

from __future__ import annotations

from mcp_phone_controll.presentation.descriptors._param_builders import (
    _params_press_key,
    _params_swipe,
    _params_tap,
    _parse_bounds,
)


def test_swipe_accepts_startxy_aliases():
    p = _params_swipe({"startX": 10, "startY": 20, "endX": 30, "endY": 40})
    assert (p.x1, p.y1, p.x2, p.y2) == (10, 20, 30, 40)


def test_swipe_canonical_still_works():
    p = _params_swipe({"x1": 1, "y1": 2, "x2": 3, "y2": 4})
    assert (p.x1, p.y1, p.x2, p.y2) == (1, 2, 3, 4)


def test_press_key_accepts_key_alias():
    assert _params_press_key({"key": "back"}).keycode == "back"
    assert _params_press_key({"keycode": "home"}).keycode == "home"


def test_bounds_parses_dump_ui_string_form():
    assert _parse_bounds("[10,20][110,220]") == (10, 20, 110, 220)


def test_bounds_parses_list_form():
    assert _parse_bounds([1, 2, 3, 4]) == (1, 2, 3, 4)


def test_bounds_rejects_garbage():
    assert _parse_bounds("not bounds") is None
    assert _parse_bounds([1, 2, 3]) is None
    assert _parse_bounds(None) is None


def test_tap_parses_bounds_string():
    p = _params_tap({"bounds": "[0,0][100,100]"})
    assert p.bounds == (0, 0, 100, 100)
