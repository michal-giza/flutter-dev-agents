"""Lazy facebook-wda Client factory keyed by udid. Caches sessions.

Connection is over usbmux (no iproxy needed) — just `wda.USBClient(udid)`.
The WebDriverAgent app must already be built and installed on the device.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


class WdaFactory(Protocol):
    async def get(self, udid: str) -> Any: ...


class CachingWdaFactory:
    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get(self, udid: str) -> Any:
        async with self._lock:
            if udid in self._clients:
                return self._clients[udid]
            import wda  # local import — heavy + optional at test time

            client = await asyncio.to_thread(wda.USBClient, udid)
            session = await asyncio.to_thread(client.session)
            self._clients[udid] = session
            return session
