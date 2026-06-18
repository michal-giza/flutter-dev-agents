"""CachingUiRepository — a short-TTL, action-invalidated cache for the
device UI hierarchy dump.

Why: an agent doing structured navigation often reads the hierarchy
several times on the *same* static screen (e.g. `extract_ui_graph` to
list elements, then again after reasoning). Each `dump_ui` is a real
device round-trip (`uiautomator dump` ~ 100-300ms). Caching the dump
within a stable screen removes that redundant cost.

**Safety — why a stale cache can never cause a wrong tap.** Only the
read-only `dump_ui` is cached. Every *action* (`tap`, `tap_text`,
`swipe`, `type_text`, `press_key`) invalidates the serial's entry, and
`find`/`wait_for` are passed straight through to the live device (they
query uiautomator2 selectors, not the cached XML). So:

  - taps by selector resolve against the LIVE tree, always — the cache
    is never consulted to decide where to tap;
  - the only thing the cache can serve stale is an *observation*
    (`dump_ui`/`extract_ui_graph`), and only for at most `ttl_ms`, and
    never across an action the agent just took.

**Off by default.** `ttl_ms <= 0` disables caching entirely (pure
pass-through), so default behaviour is unchanged. Enable with
`MCP_UI_CACHE_TTL_MS` (recommended small, e.g. 750). Intended for the
`navigation` discipline (speed over freshness on non-verification work);
leave off when you need guaranteed-fresh reads.
"""

from __future__ import annotations

import time

from ...domain.entities import UiElement
from ...domain.repositories import UiRepository
from ...domain.result import Result


class CachingUiRepository(UiRepository):
    def __init__(
        self,
        inner: UiRepository,
        ttl_ms: int = 0,
        clock=None,
    ) -> None:
        self._inner = inner
        self._ttl_s = max(0.0, ttl_ms / 1000.0)
        self._clock = clock or time.monotonic
        # serial -> (captured_at_monotonic, xml)
        self._cache: dict[str, tuple[float, str]] = {}

    @property
    def enabled(self) -> bool:
        return self._ttl_s > 0

    def _invalidate(self, serial: str) -> None:
        self._cache.pop(serial, None)

    # ---- cached read ---------------------------------------------------

    async def dump_ui(self, serial: str) -> Result[str]:
        if self._ttl_s > 0:
            hit = self._cache.get(serial)
            if hit is not None:
                captured_at, xml = hit
                if (self._clock() - captured_at) <= self._ttl_s:
                    from ...domain.result import ok

                    return ok(xml)
        res = await self._inner.dump_ui(serial)
        if self._ttl_s > 0 and res.is_ok:
            self._cache[serial] = (self._clock(), res.value)
        return res

    # ---- actions: pass through AND invalidate --------------------------

    async def tap(self, serial: str, x: int, y: int) -> Result[None]:
        self._invalidate(serial)
        return await self._inner.tap(serial, x, y)

    async def tap_text(
        self, serial: str, text: str, exact: bool = False
    ) -> Result[None]:
        self._invalidate(serial)
        return await self._inner.tap_text(serial, text, exact)

    async def swipe(
        self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> Result[None]:
        self._invalidate(serial)
        return await self._inner.swipe(serial, x1, y1, x2, y2, duration_ms)

    async def type_text(self, serial: str, text: str) -> Result[None]:
        self._invalidate(serial)
        return await self._inner.type_text(serial, text)

    async def press_key(self, serial: str, keycode: str) -> Result[None]:
        self._invalidate(serial)
        return await self._inner.press_key(serial, keycode)

    # ---- live reads: always pass through (never cached) ----------------

    async def find(
        self,
        serial: str,
        text: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        timeout_s: float = 5.0,
    ) -> Result[UiElement | None]:
        return await self._inner.find(
            serial,
            text=text,
            resource_id=resource_id,
            class_name=class_name,
            timeout_s=timeout_s,
        )

    async def wait_for(
        self,
        serial: str,
        text: str | None = None,
        resource_id: str | None = None,
        timeout_s: float = 10.0,
    ) -> Result[UiElement]:
        return await self._inner.wait_for(
            serial, text=text, resource_id=resource_id, timeout_s=timeout_s
        )
