"""extract_ui_graph — turn dump_ui XML into a typed graph."""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.result import ok
from mcp_phone_controll.domain.usecases.ui_graph import (
    ExtractUiGraph,
    ExtractUiGraphParams,
    _parse,
)

_ANDROID_DUMP = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" bounds="[0,0][1080,2340]">
    <node class="android.widget.LinearLayout" bounds="[0,0][1080,200]">
      <node class="android.widget.TextView" text="Welcome" clickable="false"
            resource-id="com.example:id/title" bounds="[40,80][400,160]"
            enabled="true" />
      <node class="android.widget.Button" text="Sign in" clickable="true"
            resource-id="com.example:id/btn_signin" bounds="[40,200][400,280]"
            enabled="true" />
      <node class="android.widget.EditText" text="" clickable="true"
            resource-id="com.example:id/email" bounds="[40,320][1040,400]"
            enabled="true" />
      <node class="android.widget.ImageView" bounds="[100,500][200,600]"
            clickable="false" enabled="true" />
    </node>
  </node>
</hierarchy>
"""


_IOS_DUMP = """<?xml version="1.0" encoding="UTF-8"?>
<XCUIElementTypeApplication>
  <XCUIElementTypeWindow>
    <XCUIElementTypeButton label="Continue" enabled="true" />
    <XCUIElementTypeStaticText label="Welcome back" />
    <XCUIElementTypeTextField label="Email" />
    <XCUIElementTypeImage label="logo" />
  </XCUIElementTypeWindow>
</XCUIElementTypeApplication>
"""


def test_parses_android_dump_into_typed_buckets():
    result = _parse(_ANDROID_DUMP, max_nodes=200)
    assert result.platform == "android"
    assert any(n.text == "Sign in" and n.role == "button" for n in result.clickables)
    assert any(n.role == "text_field" for n in result.inputs)
    assert any(n.role == "text" and n.text == "Welcome" for n in result.texts)
    assert any(n.role == "image" for n in result.images)


def test_parses_ios_dump():
    result = _parse(_IOS_DUMP, max_nodes=200)
    assert result.platform == "ios"
    assert any(n.role == "button" and n.text == "Continue" for n in result.clickables)
    assert any(n.role == "text_field" for n in result.inputs)


def test_respects_max_nodes_cap():
    # Big synthetic dump.
    children = "\n".join(
        f'<node class="android.widget.Button" text="b{i}" clickable="true" />'
        for i in range(50)
    )
    big = f'<?xml version="1.0"?><hierarchy>{children}</hierarchy>'
    result = _parse(big, max_nodes=10)
    assert result.node_count == 10
    assert result.truncated is True


def test_parses_bounds_correctly():
    result = _parse(_ANDROID_DUMP, max_nodes=200)
    btn = next(n for n in result.clickables if n.text == "Sign in")
    assert btn.bounds == (40, 200, 400, 280)


class _FakeUiRepo:
    def __init__(self, xml: str) -> None:
        self._xml = xml

    async def dump_ui(self, _serial): return ok(self._xml)
    async def tap(self, *_a, **_k): return ok(None)
    async def tap_text(self, *_a, **_k): return ok(None)
    async def swipe(self, *_a, **_k): return ok(None)
    async def type_text(self, *_a, **_k): return ok(None)
    async def press_key(self, *_a, **_k): return ok(None)
    async def find(self, *_a, **_k): return ok(None)
    async def wait_for(self, *_a, **_k): return ok(None)


class _FakeState:
    async def get_selected_serial(self): return ok("EMU01")
    async def set_selected_serial(self, _s): return ok(None)


@pytest.mark.asyncio
async def test_full_use_case_round_trip():
    uc = ExtractUiGraph(_FakeUiRepo(_ANDROID_DUMP), _FakeState())
    res = await uc.execute(ExtractUiGraphParams())
    assert res.is_ok
    assert any(n.role == "button" for n in res.value.clickables)
    assert res.value.platform == "android"


@pytest.mark.asyncio
async def test_unparseable_dump_falls_back_gracefully():
    uc = ExtractUiGraph(_FakeUiRepo("not xml at all"), _FakeState())
    res = await uc.execute(ExtractUiGraphParams())
    assert res.is_ok
    assert res.value.platform == "unknown"
