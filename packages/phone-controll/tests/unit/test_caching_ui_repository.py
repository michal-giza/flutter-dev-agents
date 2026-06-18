"""CachingUiRepository — short-TTL, action-invalidated UI-dump cache (v0.13.0 #3)."""

from __future__ import annotations

import pytest

from mcp_phone_controll.data.repositories.caching_ui_repository import (
    CachingUiRepository,
)
from mcp_phone_controll.domain.entities import Bounds, UiElement
from mcp_phone_controll.domain.result import Ok


class _FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class _CountingUi:
    """Inner UiRepository that counts dump_ui calls and records actions."""

    def __init__(self) -> None:
        self.dump_calls = 0
        self.find_calls = 0
        self.actions: list[tuple] = []

    async def dump_ui(self, serial):
        self.dump_calls += 1
        from mcp_phone_controll.domain.result import ok

        return ok(f"<hierarchy gen={self.dump_calls}/>")

    async def tap(self, serial, x, y):
        from mcp_phone_controll.domain.result import ok

        self.actions.append(("tap", serial, x, y))
        return ok(None)

    async def tap_text(self, serial, text, exact=False):
        from mcp_phone_controll.domain.result import ok

        self.actions.append(("tap_text", serial, text))
        return ok(None)

    async def swipe(self, serial, x1, y1, x2, y2, duration_ms=300):
        from mcp_phone_controll.domain.result import ok

        self.actions.append(("swipe", serial))
        return ok(None)

    async def type_text(self, serial, text):
        from mcp_phone_controll.domain.result import ok

        self.actions.append(("type", serial))
        return ok(None)

    async def press_key(self, serial, keycode):
        from mcp_phone_controll.domain.result import ok

        self.actions.append(("key", serial))
        return ok(None)

    async def find(self, serial, text=None, resource_id=None, class_name=None, timeout_s=5.0):
        from mcp_phone_controll.domain.result import ok

        self.find_calls += 1
        return ok(
            UiElement(
                text="x", resource_id=resource_id, class_name=class_name,
                content_description=None, bounds=Bounds(0, 0, 10, 10),
                enabled=True, clickable=True,
            )
        )

    async def wait_for(self, serial, text=None, resource_id=None, timeout_s=10.0):
        return await self.find(serial, text=text, resource_id=resource_id)


_S = "dev1"


@pytest.mark.asyncio
async def test_disabled_by_default_passes_through():
    inner = _CountingUi()
    repo = CachingUiRepository(inner, ttl_ms=0)
    assert repo.enabled is False
    await repo.dump_ui(_S)
    await repo.dump_ui(_S)
    assert inner.dump_calls == 2  # no caching


@pytest.mark.asyncio
async def test_cache_hit_within_ttl():
    clock = _FakeClock()
    inner = _CountingUi()
    repo = CachingUiRepository(inner, ttl_ms=1000, clock=clock)
    r1 = await repo.dump_ui(_S)
    clock.advance(0.5)  # within 1s TTL
    r2 = await repo.dump_ui(_S)
    assert isinstance(r1, Ok) and isinstance(r2, Ok)
    assert r1.value == r2.value
    assert inner.dump_calls == 1  # served from cache


@pytest.mark.asyncio
async def test_cache_expires_after_ttl():
    clock = _FakeClock()
    inner = _CountingUi()
    repo = CachingUiRepository(inner, ttl_ms=1000, clock=clock)
    await repo.dump_ui(_S)
    clock.advance(1.5)  # past TTL
    await repo.dump_ui(_S)
    assert inner.dump_calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["tap", "tap_text", "swipe", "type_text", "press_key"])
async def test_action_invalidates_cache(action):
    clock = _FakeClock()
    inner = _CountingUi()
    repo = CachingUiRepository(inner, ttl_ms=5000, clock=clock)
    await repo.dump_ui(_S)  # populate
    # Perform the action — must clear the entry even within TTL.
    if action == "tap":
        await repo.tap(_S, 1, 2)
    elif action == "tap_text":
        await repo.tap_text(_S, "Go")
    elif action == "swipe":
        await repo.swipe(_S, 0, 0, 1, 1)
    elif action == "type_text":
        await repo.type_text(_S, "hi")
    elif action == "press_key":
        await repo.press_key(_S, "back")
    await repo.dump_ui(_S)
    assert inner.dump_calls == 2  # re-dumped after the action


@pytest.mark.asyncio
async def test_per_serial_isolation():
    clock = _FakeClock()
    inner = _CountingUi()
    repo = CachingUiRepository(inner, ttl_ms=5000, clock=clock)
    await repo.dump_ui("a")
    await repo.dump_ui("b")  # different serial → own entry
    await repo.dump_ui("a")  # cached
    assert inner.dump_calls == 2


@pytest.mark.asyncio
async def test_find_is_never_cached_always_live():
    """Safety: taps resolve via find, which must always hit the device."""
    inner = _CountingUi()
    repo = CachingUiRepository(inner, ttl_ms=5000)
    await repo.find(_S, resource_id="r")
    await repo.find(_S, resource_id="r")
    assert inner.find_calls == 2  # never served stale
