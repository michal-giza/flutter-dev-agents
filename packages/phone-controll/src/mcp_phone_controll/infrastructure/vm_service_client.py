"""Minimal Dart VM service client.

Connects to the WebSocket exposed by `flutter run --machine` (`vm_service_uri`
on a DebugSession). Sends JSON-RPC 2.0 requests, awaits matching responses.
Used for DAP-lite ops: list isolates, evaluate expressions, get stack.

`websockets` is an optional extra. If not installed, the wrapper returns a
clear ImportError — the use-case layer surfaces that as a typed Failure with
`next_action: "install_debug_extras"`.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any


class VmServiceClient:
    def __init__(self, uri: str) -> None:
        self._uri = uri
        self._ws = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    async def connect(self, timeout_s: float = 10.0) -> None:
        try:
            import websockets
        except ImportError as e:
            raise ImportError(
                "websockets not installed; run `uv pip install -e \".[debug]\"`"
            ) from e
        # The flutter --machine `wsUri` already includes the auth token and
        # the `/ws` suffix — connect directly.
        self._ws = await asyncio.wait_for(
            websockets.connect(self._uri, ping_interval=20), timeout=timeout_s
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._ws is not None:
            await self._ws.close()

    async def call(
        self, method: str, params: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("VmServiceClient not connected")
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        await self._ws.send(json.dumps(payload))
        try:
            return await asyncio.wait_for(future, timeout=timeout_s)
        finally:
            self._pending.pop(request_id, None)

    # Convenience wrappers covering the DAP-lite surface.

    async def get_vm(self) -> dict[str, Any]:
        return await self.call("getVM")

    async def get_isolate(self, isolate_id: str) -> dict[str, Any]:
        return await self.call("getIsolate", {"isolateId": isolate_id})

    async def evaluate_in_frame(
        self, isolate_id: str, frame_index: int, expression: str
    ) -> dict[str, Any]:
        return await self.call(
            "evaluateInFrame",
            {
                "isolateId": isolate_id,
                "frameIndex": frame_index,
                "expression": expression,
            },
        )

    async def evaluate(
        self, isolate_id: str, target_id: str, expression: str
    ) -> dict[str, Any]:
        return await self.call(
            "evaluate",
            {
                "isolateId": isolate_id,
                "targetId": target_id,
                "expression": expression,
            },
        )

    async def get_stack(self, isolate_id: str) -> dict[str, Any]:
        return await self.call("getStack", {"isolateId": isolate_id})

    async def _read_loop(self) -> None:
        if self._ws is None:
            return
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                request_id = msg.get("id")
                if isinstance(request_id, int):
                    pending = self._pending.get(request_id)
                    if pending and not pending.done():
                        pending.set_result(msg)
        except asyncio.CancelledError:
            return
        except Exception:
            return
