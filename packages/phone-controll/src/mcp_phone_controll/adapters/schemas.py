"""Convert MCP JSONSchema tool descriptors into OpenAI function-call schemas.

The two formats are very close — OpenAI wraps the JSONSchema in a
`{type: 'function', function: {name, description, parameters}}` envelope.

`strict=True` opts into OpenAI's structured-output mode, which constrains
the model's sampling to schema-valid arguments at generation time.
Backed by the same idea as Willard & Louf, 2023 ("Efficient guided
generation", arXiv:2307.09702): instead of validating arguments after
sampling, restrict the sampler so invalid tokens are zero-probability.

For local 4B models that follow the OpenAI tools contract (Ollama with
qwen2.5/llama-3.x, vLLM, llama.cpp + tool grammars), this is the
single biggest reliability win — no more "the model emitted
{\"timeout_s\": \"five\"} instead of 5".
"""

from __future__ import annotations

import os
from typing import Any

from ..presentation.tool_registry import ToolDescriptor


def _strict_default() -> bool:
    """Default for the `strict` flag — overridable via MCP_STRICT_TOOLS env."""
    raw = os.environ.get("MCP_STRICT_TOOLS", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def to_openai_function(
    descriptor: ToolDescriptor, strict: bool | None = None
) -> dict[str, Any]:
    if strict is None:
        strict = _strict_default()
    function: dict[str, Any] = {
        "name": descriptor.name,
        "description": descriptor.description,
        "parameters": descriptor.input_schema,
    }
    if strict:
        function["strict"] = True
    return {"type": "function", "function": function}


def to_openai_functions(
    descriptors: list[ToolDescriptor], strict: bool | None = None
) -> list[dict[str, Any]]:
    return [to_openai_function(d, strict=strict) for d in descriptors]
