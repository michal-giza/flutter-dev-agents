"""Lazy `uiautomator2.Device` factory keyed by serial. Caches connections."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


class UiAutomator2Factory(Protocol):
    async def get(self, serial: str) -> Any: ...


class CachingUiAutomator2Factory:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get(self, serial: str) -> Any:
        async with self._lock:
            if serial in self._cache:
                return self._cache[serial]
            import uiautomator2 as u2  # local import: heavy + optional at test time

            device = await asyncio.to_thread(u2.connect, serial)
            self._cache[serial] = device
            return device
