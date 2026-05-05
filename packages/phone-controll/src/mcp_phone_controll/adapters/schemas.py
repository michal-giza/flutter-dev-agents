"""Convert MCP JSONSchema tool descriptors into OpenAI function-call schemas.

The two formats are very close — OpenAI wraps the JSONSchema in a
`{type: 'function', function: {name, description, parameters}}` envelope.
"""

from __future__ import annotations

from typing import Any

from ..presentation.tool_registry import ToolDescriptor


def to_openai_function(descriptor: ToolDescriptor) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": descriptor.name,
            "description": descriptor.description,
            "parameters": descriptor.input_schema,
        },
    }


def to_openai_functions(descriptors: list[ToolDescriptor]) -> list[dict[str, Any]]:
    return [to_openai_function(d) for d in descriptors]
