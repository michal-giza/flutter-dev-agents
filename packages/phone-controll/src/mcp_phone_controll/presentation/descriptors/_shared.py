"""Shared primitives for tool descriptors: ToolDescriptor + schema helpers.

Kept tiny on purpose. Any change here ripples to every descriptor file —
treat additions like changes to a public API.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...domain.result import Result
from ...domain.usecases.base import NoParams

JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    """One MCP tool: name, JSON-schema, params builder, async invoker."""

    name: str
    description: str
    input_schema: JsonDict
    build_params: Callable[[JsonDict], Any]
    invoke: Callable[[JsonDict], Awaitable[Result[Any]]]


# ---- schema helpers ----------------------------------------------------


def _string(desc: str = "") -> JsonDict:
    return {"type": "string", "description": desc}


def _int(desc: str = "") -> JsonDict:
    return {"type": "integer", "description": desc}


def _number(desc: str = "") -> JsonDict:
    return {"type": "number", "description": desc}


def _bool(desc: str = "") -> JsonDict:
    return {"type": "boolean", "description": desc}


def _enum(values: list[str], desc: str = "") -> JsonDict:
    return {"type": "string", "enum": values, "description": desc}


def _schema(properties: JsonDict, required: list[str] | None = None) -> JsonDict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def _params_no(_: JsonDict) -> NoParams:
    """Builder for tools that take no arguments."""
    return NoParams()
