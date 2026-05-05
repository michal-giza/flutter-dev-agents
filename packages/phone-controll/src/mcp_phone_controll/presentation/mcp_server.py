"""MCP server adapter — wires the ToolDispatcher to the Anthropic MCP SDK over stdio."""

from __future__ import annotations

import json
from typing import Any

from .tool_registry import ToolDispatcher


async def serve_stdio(dispatcher: ToolDispatcher, server_name: str = "phone-controll") -> None:
    # Local imports keep the package importable in environments without `mcp` installed
    # (e.g. when running unit tests that exercise only domain/data/presentation layers).
    from mcp.server import Server  # type: ignore[import-not-found]
    from mcp.server.stdio import stdio_server  # type: ignore[import-not-found]
    from mcp.types import TextContent, Tool  # type: ignore[import-not-found]

    server: Any = Server(server_name)

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(name=d.name, description=d.description, inputSchema=d.input_schema)
            for d in dispatcher.descriptors
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        envelope = await dispatcher.dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )
