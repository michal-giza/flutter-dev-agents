"""Tests for the small-LLM argument coercion + corrected_example helpers.

These cover the failure modes a 4B model actually exhibits:
  - "true" instead of bool true
  - "5" instead of int 5
  - "5.5" instead of float 5.5
  - integer where string is expected (numeric serial)
  - bare string where one-element list is expected
"""

from __future__ import annotations

from mcp_phone_controll.presentation.argument_coercion import (
    coerce_args,
    corrected_example,
)


def test_coerce_bool_from_string():
    schema = {"type": "object", "properties": {"force": {"type": "boolean"}}}
    assert coerce_args({"force": "true"}, schema) == {"force": True}
    assert coerce_args({"force": "FALSE"}, schema) == {"force": False}
    assert coerce_args({"force": "1"}, schema) == {"force": True}
    assert coerce_args({"force": "0"}, schema) == {"force": False}
    assert coerce_args({"force": "yes"}, schema) == {"force": True}


def test_coerce_int_from_string():
    schema = {"type": "object", "properties": {"timeout_s": {"type": "integer"}}}
    assert coerce_args({"timeout_s": "5"}, schema) == {"timeout_s": 5}
    assert coerce_args({"timeout_s": "5.0"}, schema) == {"timeout_s": 5}


def test_coerce_float_from_string():
    schema = {"type": "object", "properties": {"tolerance": {"type": "number"}}}
    assert coerce_args({"tolerance": "0.95"}, schema) == {"tolerance": 0.95}


def test_coerce_string_from_int():
    schema = {"type": "object", "properties": {"serial": {"type": "string"}}}
    assert coerce_args({"serial": 5554}, schema) == {"serial": "5554"}


def test_coerce_array_from_bare_value():
    schema = {"type": "object", "properties": {"capture": {"type": "array"}}}
    assert coerce_args({"capture": "screenshot"}, schema) == {"capture": ["screenshot"]}
    assert coerce_args({"capture": None}, schema) == {"capture": []}


def test_coerce_passes_through_correct_types():
    schema = {
        "type": "object",
        "properties": {
            "force": {"type": "boolean"},
            "timeout_s": {"type": "integer"},
        },
    }
    assert coerce_args({"force": True, "timeout_s": 30}, schema) == {
        "force": True,
        "timeout_s": 30,
    }


def test_coerce_unknown_keys_pass_through():
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    out = coerce_args({"x": "5", "extra": "value"}, schema)
    assert out == {"x": 5, "extra": "value"}


def test_coerce_handles_invalid_string_int():
    """Garbage input passes through unchanged so the use case sees the original."""
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    assert coerce_args({"x": "not a number"}, schema) == {"x": "not a number"}


def test_coerce_no_op_when_schema_not_object():
    assert coerce_args({"x": 1}, {}) == {"x": 1}
    assert coerce_args({"x": 1}, {"type": "string"}) == {"x": 1}


# ----- corrected_example -------------------------------------------


def test_corrected_example_uses_required_only():
    schema = {
        "type": "object",
        "properties": {
            "serial": {"type": "string"},
            "force": {"type": "boolean"},
            "note": {"type": "string"},
        },
        "required": ["serial"],
    }
    assert corrected_example(schema) == {"serial": ""}


def test_corrected_example_picks_first_enum():
    schema = {
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["debug", "release"]}},
        "required": ["mode"],
    }
    assert corrected_example(schema) == {"mode": "debug"}


def test_corrected_example_handles_each_type():
    schema = {
        "type": "object",
        "properties": {
            "s": {"type": "string"},
            "i": {"type": "integer"},
            "f": {"type": "number"},
            "b": {"type": "boolean"},
            "a": {"type": "array"},
            "o": {"type": "object"},
        },
        "required": ["s", "i", "f", "b", "a", "o"],
    }
    out = corrected_example(schema)
    assert out["s"] == ""
    assert out["i"] == 0
    assert out["f"] == 0.0
    assert out["b"] is False
    assert out["a"] == []
    assert out["o"] == {}
