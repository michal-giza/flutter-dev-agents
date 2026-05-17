"""dataclass_to_json_schema — Tier 1.4 infrastructure for MCP outputSchema.

The helper walks our use-case Result dataclasses and produces a JSON
Schema we can attach to `ToolDescriptor.output_schema`, which the
stdio adapter surfaces in `tools/list` and the agent host validates
`structuredContent` against (MCP 2025-06-18 spec).

These tests pin the helper's behaviour on every dataclass shape our
Result types actually use. The per-tool migration to populate
`output_schema` on every BASIC tool descriptor lands in a follow-up.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path

from mcp_phone_controll.presentation.descriptors._shared import (
    dataclass_to_json_schema,
)


def test_primitives_map_to_basic_json_types():
    @dataclass(frozen=True, slots=True)
    class _R:
        s: str
        i: int
        b: bool
        f: float

    schema = dataclass_to_json_schema(_R)
    assert schema["type"] == "object"
    assert schema["properties"]["s"] == {"type": "string"}
    assert schema["properties"]["i"] == {"type": "integer"}
    assert schema["properties"]["b"] == {"type": "boolean"}
    assert schema["properties"]["f"] == {"type": "number"}
    # All required because no defaults.
    assert set(schema["required"]) == {"s", "i", "b", "f"}
    assert schema["additionalProperties"] is False


def test_path_maps_to_string():
    @dataclass(frozen=True, slots=True)
    class _R:
        p: Path

    schema = dataclass_to_json_schema(_R)
    assert schema["properties"]["p"] == {"type": "string"}


def test_optional_makes_field_nullable_not_required():
    @dataclass(frozen=True, slots=True)
    class _R:
        required_value: str
        optional_value: str | None = None

    schema = dataclass_to_json_schema(_R)
    # Required field stays plain string.
    assert schema["properties"]["required_value"] == {"type": "string"}
    # Optional field allows null AND not in required.
    assert schema["properties"]["optional_value"]["type"] == ["string", "null"]
    assert "optional_value" not in schema["required"]
    assert "required_value" in schema["required"]


def test_list_and_tuple_become_array_with_item_schema():
    @dataclass(frozen=True, slots=True)
    class _R:
        tags: list[str]
        coords: tuple[int, ...]

    schema = dataclass_to_json_schema(_R)
    assert schema["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert schema["properties"]["coords"] == {
        "type": "array",
        "items": {"type": "integer"},
    }


@dataclass(frozen=True, slots=True)
class _WithDict:
    extra: dict


def test_dict_becomes_object_no_inner_schema():
    schema = dataclass_to_json_schema(_WithDict)
    assert schema["properties"]["extra"] == {"type": "object"}


class _Color(enum.Enum):
    RED = "red"
    GREEN = "green"


@dataclass(frozen=True, slots=True)
class _WithEnum:
    color: _Color


def test_enum_becomes_string_with_enum_values():
    schema = dataclass_to_json_schema(_WithEnum)
    assert schema["properties"]["color"]["type"] == "string"
    assert set(schema["properties"]["color"]["enum"]) == {"red", "green"}


@dataclass(frozen=True, slots=True)
class _NestedInner:
    name: str


@dataclass(frozen=True, slots=True)
class _NestedOuter:
    nested: _NestedInner


def test_nested_dataclass_recurses():
    schema = dataclass_to_json_schema(_NestedOuter)
    nested_schema = schema["properties"]["nested"]
    assert nested_schema["type"] == "object"
    assert nested_schema["properties"]["name"] == {"type": "string"}


def test_field_with_default_factory_not_required():
    @dataclass(frozen=True, slots=True)
    class _R:
        always: str
        sometimes: list[str] = field(default_factory=list)

    schema = dataclass_to_json_schema(_R)
    assert "always" in schema["required"]
    assert "sometimes" not in schema["required"]


def test_non_dataclass_returns_empty_schema():
    """Robust to misuse: passing a non-dataclass shouldn't raise."""
    assert dataclass_to_json_schema(str) == {}
    assert dataclass_to_json_schema(int) == {}


def test_real_result_dataclass_produces_usable_schema():
    """End-to-end with a real Result type to prove the helper isn't
    just toy-grade. Picks `McpPingResult` because it exercises every
    primitive plus tuple[str, ...]."""
    from mcp_phone_controll.domain.usecases.mcp_ping import McpPingResult

    schema = dataclass_to_json_schema(McpPingResult)
    assert schema["type"] == "object"
    # Spot-check a few load-bearing fields.
    props = schema["properties"]
    assert props["package_version"] == {"type": "string"}
    assert props["pid"] == {"type": "integer"}
    assert props["git_dirty"] == {"type": "boolean"}
    assert props["image_backends"]["type"] == "array"
    assert props["image_backends"]["items"] == {"type": "string"}
    assert props["image_cap_px"] == {"type": "integer"}
