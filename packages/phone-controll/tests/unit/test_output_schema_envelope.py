"""MCP 2025-06-18 structured-output envelope contract.

REGRESSION (2026-06-06): tools advertising `outputSchema` returned no
`structuredContent`, so a strict MCP SDK (mcp >= ~1.9, which a user's
client pulled in on upgrade) rejected them with
"Output validation error: outputSchema defined but no structured output
returned". `list_devices` (no outputSchema) kept working; `mcp_ping` and
`check_environment` broke — exactly the reported symptom.

The fix has two halves, both pinned here:

  1. `_call_tool` now returns `structuredContent` = the dispatcher
     envelope (see test_mcp_server.py).
  2. Every advertised `outputSchema` is wrapped by
     `envelope_output_schema()` so it describes that envelope
     (`{ok, data, error}`), not the bare dataclass. A bare-dataclass
     schema (`additionalProperties: false` + dataclass `required`) can
     NEVER validate the envelope — that mismatch is the bug.

These tests assert the wrapped schema validates BOTH envelope shapes
(success and error) and that no live tool regresses to a bare schema.
"""

from __future__ import annotations

from dataclasses import dataclass

import jsonschema
import pytest

from mcp_phone_controll.container import build_runtime
from mcp_phone_controll.presentation.descriptors._shared import (
    envelope_output_schema,
)
from mcp_phone_controll.presentation.serialization import to_jsonable


@dataclass
class _Sample:
    name: str
    count: int
    note: str = "default"  # has a default → optional in the schema


def _live_schemas_with_output():
    _, dispatcher = build_runtime()
    return [d for d in dispatcher.descriptors if d.output_schema is not None]


# ---- the wrapper itself -------------------------------------------------


def test_wrapped_schema_validates_success_envelope():
    schema = envelope_output_schema(_Sample)
    envelope = {"ok": True, "data": to_jsonable(_Sample(name="x", count=3))}
    jsonschema.validate(instance=envelope, schema=schema)  # must not raise


def test_wrapped_schema_validates_error_envelope():
    """The error branch carries no `data` — it must still validate, or a
    tool failure would surface as a confusing SDK 'Output validation
    error' instead of our clean `{ok: false, error}` envelope."""
    schema = envelope_output_schema(_Sample)
    envelope = {
        "ok": False,
        "error": {
            "code": "BoomFailure",
            "message": "kaboom",
            "next_action": "retry",
            "details": {},
        },
    }
    jsonschema.validate(instance=envelope, schema=schema)  # must not raise


def test_wrapped_schema_tolerates_middleware_extra_fields():
    """Post-dispatch middleware (trace, seatbelt) may enrich the envelope.
    additionalProperties must stay open so that never false-fails."""
    schema = envelope_output_schema(_Sample)
    envelope = {
        "ok": True,
        "data": to_jsonable(_Sample(name="x", count=1)),
        "trace_id": "abc-123",  # middleware-added, not in the schema
    }
    jsonschema.validate(instance=envelope, schema=schema)


def test_wrapped_schema_requires_ok():
    schema = envelope_output_schema(_Sample)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance={"data": {}}, schema=schema)


def test_wrapped_schema_top_level_is_object_with_properties():
    """Mirrors the spec rules enforced in test_output_schema_validity.py —
    the wrapper must satisfy them too."""
    schema = envelope_output_schema(_Sample)
    assert schema["type"] == "object"
    assert "ok" in schema["properties"]
    assert "data" in schema["properties"]
    assert schema["required"] == ["ok"]


# ---- the live tool surface ---------------------------------------------


def test_live_output_schemas_are_envelope_wrapped():
    """Every tool that advertises an outputSchema must describe the
    ENVELOPE (top-level `ok` + `data`), not a bare dataclass. A bare
    dataclass schema is the exact shape that caused the strict-SDK
    rejection, so this is the tripwire against regressing."""
    offenders = []
    for d in _live_schemas_with_output():
        props = d.output_schema.get("properties", {})
        if "ok" not in props or "data" not in props:
            offenders.append(d.name)
    assert not offenders, (
        f"{len(offenders)} tool(s) advertise a non-envelope outputSchema "
        f"(missing top-level ok/data) — a strict MCP SDK will reject them "
        f"with 'outputSchema defined but no structured output returned': "
        f"{offenders}. Wrap with envelope_output_schema()."
    )


def test_every_live_output_schema_validates_the_error_envelope():
    """The universal error envelope must validate against EVERY advertised
    outputSchema — guarantees a tool *failure* never becomes an SDK output
    validation error on top of the real error."""
    err_envelope = {
        "ok": False,
        "error": {
            "code": "SomeFailure",
            "message": "x",
            "next_action": "y",
            "details": {},
        },
    }
    for d in _live_schemas_with_output():
        jsonschema.validate(instance=err_envelope, schema=d.output_schema)
