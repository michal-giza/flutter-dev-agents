"""Loose-but-safe argument coercion for small-LLM clients.

Small models (4B class) often produce slightly-off argument shapes:
  - "true" / "false" / "1" / "0" instead of bool
  - "5" / "5.0" instead of int / float
  - a bare string where a single-element list is expected
  - integers where a string is expected (numeric serial numbers)

This module coerces those into the type declared by the tool's JSONSchema.
On failure the dispatcher returns an InvalidArgumentFailure envelope that
includes a corrected_example field — the agent can copy it into its next
call without LLM re-reasoning about the schema.
"""

from __future__ import annotations

from typing import Any

_TRUE_STRINGS = frozenset({"true", "yes", "1", "on"})
_FALSE_STRINGS = frozenset({"false", "no", "0", "off", "null", "none", ""})


def coerce_args(args: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Best-effort coercion of args to match a JSONSchema 'object' definition.

    Returns a NEW dict; never mutates the caller's. Unknown keys pass through
    unchanged. If the schema is malformed or not an object schema, returns
    args unchanged.
    """
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return dict(args)
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return dict(args)
    out: dict[str, Any] = {}
    for key, value in args.items():
        prop = properties.get(key)
        if not isinstance(prop, dict):
            out[key] = value
            continue
        out[key] = _coerce_one(value, prop)
    return out


def _coerce_one(value: Any, prop: dict[str, Any]) -> Any:
    """Coerce one arg value to the type declared by its JSONSchema property."""
    target = prop.get("type")
    if target is None:
        return value
    if isinstance(target, list):
        # Multi-type fields — take the first non-null target.
        target = next((t for t in target if t != "null"), None)
    if target == "boolean":
        return _to_bool(value)
    if target == "integer":
        return _to_int(value)
    if target == "number":
        return _to_float(value)
    if target == "string":
        return _to_str(value)
    if target == "array":
        if isinstance(value, list):
            return value
        if value is None:
            return []
        # Promote a single value to a one-element list — common 4B mistake.
        return [value]
    return value


def _to_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
    return value


def _to_int(value: Any) -> Any:
    if isinstance(value, bool):
        # Don't silently coerce True → 1 unless the field is genuinely numeric.
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return int(stripped)
        except ValueError:
            try:
                return int(float(stripped))
            except ValueError:
                return value
    return value


def _to_float(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value
    return value


def _to_str(value: Any) -> Any:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value


def corrected_example(schema: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal example invocation from a tool's schema.

    Used in the InvalidArgumentFailure envelope so a small LLM has a concrete
    shape to copy. Picks a sensible default for each declared property.
    """
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    example: dict[str, Any] = {}
    for key, prop in properties.items():
        if key not in required:
            continue
        example[key] = _example_value(prop)
    return example


def _example_value(prop: dict[str, Any]) -> Any:
    if not isinstance(prop, dict):
        return None
    if prop.get("enum"):
        return prop["enum"][0]
    target = prop.get("type")
    if isinstance(target, list):
        target = next((t for t in target if t != "null"), "string")
    if target == "boolean":
        return False
    if target == "integer":
        return 0
    if target == "number":
        return 0.0
    if target == "array":
        return []
    if target == "object":
        return {}
    return ""
