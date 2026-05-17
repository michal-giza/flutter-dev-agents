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

    from .descriptors._shared import default_annotations

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        # MCP 2025-06-18 annotations — surface flags from per-tool
        # overrides on the descriptor, falling back to the centralized
        # `default_annotations(name)` classifier so all 108 tools get
        # at least a best-effort annotation. Falls back gracefully on
        # older mcp SDKs that don't accept `annotations`.
        out: list[Tool] = []
        for d in dispatcher.descriptors:
            kwargs: dict[str, Any] = {
                "name": d.name,
                "description": d.description,
                "inputSchema": d.input_schema,
            }
            # MCP 2025-06-18 outputSchema — opportunistic. Tools without
            # one fall back to unstructured `content` only. As we
            # migrate the BASIC tier, more will populate.
            if d.output_schema is not None:
                kwargs["outputSchema"] = d.output_schema
            annotations: dict[str, bool] = dict(default_annotations(d.name))
            # Per-tool overrides win over the classifier defaults.
            if d.read_only is not None:
                annotations["readOnlyHint"] = d.read_only
            if d.destructive is not None:
                annotations["destructiveHint"] = d.destructive
            if d.idempotent is not None:
                annotations["idempotentHint"] = d.idempotent
            if d.open_world is not None:
                annotations["openWorldHint"] = d.open_world
            if annotations:
                kwargs["annotations"] = annotations
            try:
                out.append(Tool(**kwargs))
            except TypeError:
                # Older mcp SDKs may not accept `annotations` and/or
                # `outputSchema`. Strip them and retry.
                kwargs.pop("annotations", None)
                kwargs.pop("outputSchema", None)
                out.append(Tool(**kwargs))
        return out

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        envelope = await dispatcher.dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )
