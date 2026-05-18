"""MCP server adapter — wires the ToolDispatcher to the Anthropic MCP SDK over stdio.

`MCP_TOOL_TIER` env var (May 2026 hardening): some MCP hosts apply a
tool-count ceiling on `tools/list` — Cursor caps at 40; Claude
Desktop's UI silently drops the inventory when our 109-tool surface
arrives. Setting `MCP_TOOL_TIER=basic` (recommended for Claude
Desktop) advertises only the 24 BASIC tools and routes the long
tail through `describe_capabilities` for agents that need it.

Values:
  - `basic`        (default for Claude Desktop) — 24 tools
  - `intermediate` — BASIC + INTERMEDIATE
  - `expert` or unset — all 109 (original behaviour)

The full dispatcher is always wired; the filter only affects what's
advertised via `tools/list`. Calling a non-advertised tool by name
still works for clients that know it.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .tool_registry import ToolDispatcher


def _allowed_tool_names(all_names: list[str]) -> set[str] | None:
    """Return the set of tool names to advertise per `MCP_TOOL_TIER`.

    None = no filtering (advertise everything). Used by `_list_tools`
    below; importable so tests can pin the contract independently.
    """
    tier = os.environ.get("MCP_TOOL_TIER", "").strip().lower()
    if not tier or tier == "expert" or tier == "all":
        return None
    from ..domain.tool_levels import BASIC_TOOLS, INTERMEDIATE_TOOLS

    if tier == "basic":
        return set(BASIC_TOOLS)
    if tier == "intermediate":
        return set(BASIC_TOOLS) | set(INTERMEDIATE_TOOLS)
    # Unknown value — fail open (advertise everything) so a typo
    # doesn't accidentally remove tools.
    return None


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
        #
        # MCP_TOOL_TIER filter — hosts that drop oversized tool lists
        # (Claude Desktop UI silently dropped our 109-tool surface)
        # can scope down to BASIC (24) or BASIC+INTERMEDIATE.
        allowed = _allowed_tool_names([d.name for d in dispatcher.descriptors])
        out: list[Tool] = []
        for d in dispatcher.descriptors:
            if allowed is not None and d.name not in allowed:
                continue
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
