"""vm_service_client — drive the JSON-RPC client with a scripted fake WebSocket.

We don't depend on the real `websockets` library for this test. Instead we
inject a fake by patching `websockets.connect` in `sys.modules`, so the client
talks to an in-memory queue. This keeps the test hermetic and < 1 ms.

Coverage target: connect → call → response correlation → close → reader
shutdown — i.e. every branch in `VmServiceClient` except the optional-import
failure (covered separately).
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from collections import deque

import pytest

from mcp_phone_controll.infrastructure.vm_service_client import VmServiceClient

# ---- fake websockets module --------------------------------------------


class _FakeWS:
    """Minimal async-iterable websocket. Stores sends; yields scripted frames."""

    def __init__(self, scripted_frames: deque[str]) -> None:
        self._scripted = scripted_frames
        self.sent: list[str] = []
        self._closed = False
        self._frame_event = asyncio.Event()
        if scripted_frames:
            self._frame_event.set()

    async def send(self, payload: str) -> None:
        self.sent.append(payload)
        # On every send, auto-respond if a scripted frame is queued for that id.
        msg = json.loads(payload)
        request_id = msg["id"]
        # Inject a matching response into the scripted queue.
        self._scripted.append(json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"echo": msg["method"], "params": msg.get("params")},
        }))
        self._frame_event.set()

    async def close(self) -> None:
        self._closed = True
        self._frame_event.set()

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        while not self._scripted:
            if self._closed:
                raise StopAsyncIteration
            self._frame_event.clear()
            await self._frame_event.wait()
        return self._scripted.popleft()


def _install_fake_websockets(monkeypatch, fake_ws: _FakeWS) -> None:
    async def _connect(uri, ping_interval=None):
        return fake_ws

    fake_module = types.SimpleNamespace(connect=_connect)
    monkeypatch.setitem(sys.modules, "websockets", fake_module)


# ---- tests --------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_and_call_round_trip(monkeypatch):
    fake = _FakeWS(deque())
    _install_fake_websockets(monkeypatch, fake)

    client = VmServiceClient("ws://127.0.0.1:0/ws")
    await client.connect()
    try:
        result = await client.call("getVM")
        assert result["id"] == 1
        assert result["result"]["echo"] == "getVM"
        # Second call increments id.
        result2 = await client.call("getIsolate", {"isolateId": "isolates/1"})
        assert result2["id"] == 2
        assert result2["result"]["params"] == {"isolateId": "isolates/1"}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_convenience_wrappers_route_correctly(monkeypatch):
    fake = _FakeWS(deque())
    _install_fake_websockets(monkeypatch, fake)

    client = VmServiceClient("ws://x/ws")
    await client.connect()
    try:
        r_vm = await client.get_vm()
        r_iso = await client.get_isolate("isolates/2")
        r_eval_frame = await client.evaluate_in_frame("isolates/2", 0, "1+1")
        r_eval = await client.evaluate("isolates/2", "objects/3", "x.toString()")
        r_stack = await client.get_stack("isolates/2")
    finally:
        await client.close()

    methods = [json.loads(p)["method"] for p in fake.sent]
    assert methods == [
        "getVM", "getIsolate", "evaluateInFrame", "evaluate", "getStack",
    ]
    assert r_vm["result"]["echo"] == "getVM"
    assert r_iso["result"]["params"] == {"isolateId": "isolates/2"}
    assert r_eval_frame["result"]["params"]["frameIndex"] == 0
    assert r_eval["result"]["params"]["targetId"] == "objects/3"
    assert r_stack["result"]["params"] == {"isolateId": "isolates/2"}


@pytest.mark.asyncio
async def test_call_without_connect_raises():
    client = VmServiceClient("ws://x/ws")
    with pytest.raises(RuntimeError, match="not connected"):
        await client.call("getVM")


@pytest.mark.asyncio
async def test_missing_websockets_extra_raises_clear_import_error(monkeypatch):
    # Force the import inside connect() to fail.
    monkeypatch.setitem(sys.modules, "websockets", None)
    client = VmServiceClient("ws://x/ws")
    with pytest.raises(ImportError, match=r"\[debug\]"):
        await client.connect()


@pytest.mark.asyncio
async def test_call_times_out_when_no_response(monkeypatch):
    # A fake that silently swallows sends — no auto-response.
    class _SilentWS(_FakeWS):
        async def send(self, payload: str) -> None:
            self.sent.append(payload)  # don't enqueue a response

    fake = _SilentWS(deque())
    _install_fake_websockets(monkeypatch, fake)
    client = VmServiceClient("ws://x/ws")
    await client.connect()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await client.call("getVM", timeout_s=0.05)
        # Pending bucket must be cleaned up on timeout.
        assert client._pending == {}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_reader_ignores_malformed_frames(monkeypatch):
    fake = _FakeWS(deque(["not json {{{"]))
    _install_fake_websockets(monkeypatch, fake)
    client = VmServiceClient("ws://x/ws")
    await client.connect()
    try:
        # Reader should swallow the bad frame and still service a real call.
        result = await client.call("getVM", timeout_s=1.0)
        assert result["result"]["echo"] == "getVM"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_close_is_safe_without_connect():
    client = VmServiceClient("ws://x/ws")
    # No-op; must not raise.
    await client.close()
