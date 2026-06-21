"""wait_until — server-side block on visible/gone (v0.15.0 #3)."""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.entities import Bounds, UiElement
from mcp_phone_controll.domain.result import Err, Ok, ok
from mcp_phone_controll.domain.usecases.ui_query import WaitUntil, WaitUntilParams
from tests.fakes.fake_repositories import FakeSessionStateRepository

_S = "dev"


def _el():
    return UiElement(
        text="Loading", resource_id="r", class_name=None, content_description=None,
        bounds=Bounds(0, 0, 10, 10), enabled=True, clickable=False,
    )


class _ScriptedUi:
    """Returns a scripted sequence of find() results (None = absent)."""

    def __init__(self, sequence):
        self._seq = list(sequence)
        self.find_calls = 0

    async def find(self, serial, text=None, resource_id=None, class_name=None, timeout_s=5.0):
        self.find_calls += 1
        val = self._seq.pop(0) if self._seq else self._seq_last
        self._seq_last = val
        return ok(val)


def _uc(seq):
    ui = _ScriptedUi(seq)
    return WaitUntil(ui, FakeSessionStateRepository(serial=_S))


@pytest.mark.asyncio
async def test_visible_returns_element():
    uc = _uc([None, None, _el()])  # appears on the 3rd poll
    res = await uc(WaitUntilParams(resource_id="r", gone=False, timeout_s=2, poll_interval_s=0.05))
    assert isinstance(res, Ok), res
    assert res.value.condition == "visible"
    assert res.value.met is True
    assert res.value.element is not None


@pytest.mark.asyncio
async def test_gone_returns_when_absent():
    uc = _uc([_el(), _el(), None])  # disappears on the 3rd poll
    res = await uc(WaitUntilParams(resource_id="r", gone=True, timeout_s=2, poll_interval_s=0.05))
    assert isinstance(res, Ok), res
    assert res.value.condition == "gone"
    assert res.value.met is True
    assert res.value.element is None


@pytest.mark.asyncio
async def test_visible_times_out():
    uc = _uc([None])  # never appears
    res = await uc(WaitUntilParams(resource_id="r", gone=False, timeout_s=0.15, poll_interval_s=0.05))
    assert isinstance(res, Err)
    assert res.failure.details["condition"] == "visible"
    assert res.failure.next_action == "capture_diagnostics"


@pytest.mark.asyncio
async def test_gone_times_out_when_element_stays():
    uc = _uc([_el()])  # stays forever
    res = await uc(WaitUntilParams(resource_id="r", gone=True, timeout_s=0.15, poll_interval_s=0.05))
    assert isinstance(res, Err)
    assert res.failure.details["condition"] == "gone"


@pytest.mark.asyncio
async def test_requires_a_selector():
    uc = _uc([None])
    res = await uc(WaitUntilParams(gone=True))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"
