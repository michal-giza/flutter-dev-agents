"""mcp_server — the stdio adapter that the agent actually talks to.

Coverage gap caught in the code review (2026-05-17): this 37-LOC file
was 0% tested despite being the entry point for every real session.
A bug here breaks the agent before any tool runs.

Hermetic: we inject a fake `mcp.server.Server` so we don't need the
real `mcp` SDK or a real stdio connection. The fake captures the
registered handlers so we can call them directly and verify they
produce the right shape.
"""

from __future__ import annotations

import sys
import types
from typing import Any, ClassVar

import pytest

from mcp_phone_controll.presentation.mcp_server import serve_stdio
from mcp_phone_controll.presentation.tool_registry import (
    ToolDescriptor,
    ToolDispatcher,
)

# ---- fakes mimicking the mcp SDK surface --------------------------------


class _FakeServer:
    """Captures decorator-registered handlers so tests can invoke them
    without the real stdio loop. Mimics the slice of `mcp.server.Server`
    that `serve_stdio` touches."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._list_handler = None
        self._call_handler = None
        self.run_called = False

    def list_tools(self):
        def decorator(fn):
            self._list_handler = fn
            return fn
        return decorator

    def call_tool(self):
        def decorator(fn):
            self._call_handler = fn
            return fn
        return decorator

    def create_initialization_options(self):
        return {"fake": True}

    async def run(self, _read, _write, _opts):
        self.run_called = True


class _FakeTool:
    def __init__(self, name: str, description: str, inputSchema: dict) -> None:
        self.name = name
        self.description = description
        self.inputSchema = inputSchema


class _FakeTextContent:
    def __init__(self, type: str, text: str) -> None:
        self.type = type
        self.text = text


class _FakeCallToolResult:
    """Stand-in for a strict-SDK `mcp.types.CallToolResult`. Its presence
    plus a `structuredContent` model field is how `serve_stdio` probes
    whether the SDK supports MCP 2025-06-18 structured output."""

    model_fields: ClassVar[dict] = {"structuredContent": object(), "content": object()}


def _install_fake_mcp_sdk(monkeypatch, fake_server: _FakeServer, *, structured: bool = False):
    """Inject a fake `mcp.server` + `mcp.server.stdio` + `mcp.types`
    module hierarchy so `serve_stdio`'s local imports resolve to our
    fakes instead of the real SDK.

    `structured=True` adds a `CallToolResult` with a `structuredContent`
    model field, simulating a strict SDK (mcp >= ~1.9) so the call
    handler returns the `(content, envelope)` 2-tuple."""
    fake_server_mod = types.ModuleType("mcp.server")
    fake_server_mod.Server = lambda name: fake_server  # type: ignore[attr-defined]

    class _FakeStdioCtx:
        async def __aenter__(self):
            return (object(), object())  # (read_stream, write_stream)

        async def __aexit__(self, *a):
            return None

    fake_stdio_mod = types.ModuleType("mcp.server.stdio")
    fake_stdio_mod.stdio_server = lambda: _FakeStdioCtx()  # type: ignore[attr-defined]

    fake_types_mod = types.ModuleType("mcp.types")
    fake_types_mod.Tool = _FakeTool  # type: ignore[attr-defined]
    fake_types_mod.TextContent = _FakeTextContent  # type: ignore[attr-defined]
    if structured:
        fake_types_mod.CallToolResult = _FakeCallToolResult  # type: ignore[attr-defined]

    fake_root = types.ModuleType("mcp")

    monkeypatch.setitem(sys.modules, "mcp", fake_root)
    monkeypatch.setitem(sys.modules, "mcp.server", fake_server_mod)
    monkeypatch.setitem(sys.modules, "mcp.server.stdio", fake_stdio_mod)
    monkeypatch.setitem(sys.modules, "mcp.types", fake_types_mod)


def _two_tool_dispatcher() -> ToolDispatcher:
    """A minimal dispatcher with two tools — one happy, one that
    surfaces an unknown-tool path."""

    async def _ok_invoke(_args):
        from mcp_phone_controll.domain.result import ok

        return ok({"echo": "hello"})

    descriptors = [
        ToolDescriptor(
            name="ping_tool",
            description="reply with hello",
            input_schema={"type": "object", "properties": {}},
            build_params=lambda _args: None,
            invoke=_ok_invoke,
        ),
    ]
    return ToolDispatcher(descriptors)


# ---- tests --------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_returns_dispatcher_descriptors(monkeypatch):
    """The MCP `tools/list` handler must surface every descriptor in the
    dispatcher as a `Tool` with name + description + inputSchema."""
    fake_server = _FakeServer("phone-controll")
    _install_fake_mcp_sdk(monkeypatch, fake_server)

    dispatcher = _two_tool_dispatcher()
    await serve_stdio(dispatcher)

    assert fake_server._list_handler is not None
    tools = await fake_server._list_handler()

    assert len(tools) == 1
    t = tools[0]
    assert t.name == "ping_tool"
    assert t.description == "reply with hello"
    assert t.inputSchema == {"type": "object", "properties": {}}


@pytest.mark.asyncio
async def test_call_tool_returns_text_content_with_json_envelope(monkeypatch):
    """The MCP `tools/call` handler must wrap the dispatcher's envelope
    in a list of TextContent objects with JSON-encoded text — that's the
    contract the agent on the other side decodes."""
    import json

    fake_server = _FakeServer("phone-controll")
    _install_fake_mcp_sdk(monkeypatch, fake_server)
    dispatcher = _two_tool_dispatcher()
    await serve_stdio(dispatcher)

    assert fake_server._call_handler is not None
    result: list[Any] = await fake_server._call_handler("ping_tool", {})

    assert len(result) == 1
    tc = result[0]
    assert tc.type == "text"
    envelope = json.loads(tc.text)
    assert envelope == {"ok": True, "data": {"echo": "hello"}}


@pytest.mark.asyncio
async def test_call_tool_with_unknown_name_returns_structured_error(monkeypatch):
    """The dispatcher's UnknownTool envelope must round-trip through
    the MCP handler unchanged — agents rely on `next_action:
    "describe_capabilities"` to recover."""
    import json

    fake_server = _FakeServer("phone-controll")
    _install_fake_mcp_sdk(monkeypatch, fake_server)
    dispatcher = _two_tool_dispatcher()
    await serve_stdio(dispatcher)

    result = await fake_server._call_handler("does_not_exist", {})
    envelope = json.loads(result[0].text)

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "UnknownTool"
    assert envelope["error"]["next_action"] == "describe_capabilities"


@pytest.mark.asyncio
async def test_serve_stdio_invokes_server_run(monkeypatch):
    """End-to-end: serve_stdio must actually enter the stdio context
    manager AND call server.run() with the streams. A regression that
    short-circuits before run() would silently fail every session."""
    fake_server = _FakeServer("phone-controll")
    _install_fake_mcp_sdk(monkeypatch, fake_server)
    dispatcher = _two_tool_dispatcher()
    await serve_stdio(dispatcher)

    assert fake_server.run_called is True


@pytest.mark.asyncio
async def test_call_tool_with_none_arguments_is_handled(monkeypatch):
    """The MCP spec allows `arguments: null` on tools/call. The
    dispatcher's `_maybe_coerce_args(None, schema)` path must not
    explode. Regression test for a real MCP SDK quirk."""
    import json

    fake_server = _FakeServer("phone-controll")
    _install_fake_mcp_sdk(monkeypatch, fake_server)
    dispatcher = _two_tool_dispatcher()
    await serve_stdio(dispatcher)

    result = await fake_server._call_handler("ping_tool", None)
    envelope = json.loads(result[0].text)
    assert envelope == {"ok": True, "data": {"echo": "hello"}}


@pytest.mark.asyncio
async def test_call_tool_returns_structured_content_on_strict_sdk(monkeypatch):
    """REGRESSION (2026-06-06): on a strict MCP SDK (>= ~1.9), a tool that
    advertises `outputSchema` MUST also return `structuredContent` or the
    SDK rejects the call with "outputSchema defined but no structured
    output returned". The handler must therefore return a
    `(content, structuredContent)` 2-tuple where the structured payload IS
    the envelope. This broke `check_environment` / `mcp_ping` for users
    after an SDK upgrade."""
    import json

    fake_server = _FakeServer("phone-controll")
    _install_fake_mcp_sdk(monkeypatch, fake_server, structured=True)
    dispatcher = _two_tool_dispatcher()
    await serve_stdio(dispatcher)

    result = await fake_server._call_handler("ping_tool", {})

    # Strict path → 2-tuple: (content list, structured envelope dict).
    assert isinstance(result, tuple)
    assert len(result) == 2
    content, structured = result
    assert content[0].type == "text"
    # The unstructured text and the structured dict are the SAME envelope.
    assert json.loads(content[0].text) == structured
    assert structured == {"ok": True, "data": {"echo": "hello"}}


@pytest.mark.asyncio
async def test_call_tool_stays_content_only_on_legacy_sdk(monkeypatch):
    """The flip side: an SDK without `CallToolResult.structuredContent`
    (our >=1.2.0 floor) can't consume the 2-tuple, so the handler must
    fall back to content-only. Guards against breaking older hosts."""
    fake_server = _FakeServer("phone-controll")
    _install_fake_mcp_sdk(monkeypatch, fake_server, structured=False)
    dispatcher = _two_tool_dispatcher()
    await serve_stdio(dispatcher)

    result = await fake_server._call_handler("ping_tool", {})
    assert isinstance(result, list)
    assert result[0].type == "text"
