"""MCP 2025-06-18 outputSchema contract enforcement.

The spec requires every tool's `outputSchema` to be a JSON Schema
*object* — i.e. top-level `type: "object"`. A schema with top-level
`"array"` (or anything else) fails the spec's structuredContent
contract AND causes Claude Code's Zod validator to drop the ENTIRE
server during `tools/list`. The MCP appears connected but no tools
are visible.

That bug shipped twice in this codebase (commit `def7377` for
`list_devices` and `recall` — caused the May 18 incident where
Claude Desktop's Connectors panel showed "no tools available").
This test is the tripwire so it can't happen a third time.

Run separately so the failure message points at the *specific tool*
that drifted, not just "tests/unit fails".
"""

from __future__ import annotations

import pytest

from mcp_phone_controll.container import build_runtime


def _live_descriptors():
    """Build once; reused across the tests below."""
    _, dispatcher = build_runtime()
    return list(dispatcher.descriptors)


@pytest.fixture(scope="module")
def descriptors():
    return _live_descriptors()


def test_every_output_schema_has_top_level_object_type(descriptors):
    """The spec contract. Wrap list/array returns in an `{items: [...]}`
    envelope instead of declaring a bare-array outputSchema."""
    violations: list[tuple[str, str]] = []
    for d in descriptors:
        if d.output_schema is None:
            continue
        if not isinstance(d.output_schema, dict):
            violations.append((d.name, f"not a dict: {type(d.output_schema).__name__}"))
            continue
        top_type = d.output_schema.get("type")
        if top_type != "object":
            violations.append((d.name, f"top-level type={top_type!r}"))

    assert not violations, (
        f"{len(violations)} tool(s) have invalid outputSchema "
        f"(spec requires top-level type='object'):\n"
        + "\n".join(f"  - {name}: {detail}" for name, detail in violations)
        + "\n\nFix: wrap array returns in `{type: object, properties: "
          "{items: {type: array, items: ...}}, required: ['items']}`. "
          "See ToolDescriptor for `list_devices` in tool_registry.py "
          "for the canonical fix."
    )


def test_object_schemas_declare_their_properties(descriptors):
    """An outputSchema of `{type: object}` with no `properties` block
    is technically valid JSON Schema (matches any object) but useless
    — hosts can't validate `structuredContent` against it. Require an
    explicit properties block so the schema actually carries
    information."""
    issues: list[str] = []
    for d in descriptors:
        if d.output_schema is None:
            continue
        if d.output_schema.get("type") != "object":
            continue
        if "properties" not in d.output_schema:
            issues.append(d.name)
    assert not issues, (
        f"{len(issues)} tool(s) have outputSchema with type=object but "
        f"no properties — degenerate, won't validate anything: {issues}"
    )


def test_required_is_a_list_when_present(descriptors):
    """JSON Schema requires `required` to be an array of strings.
    Catch obvious typos like `required: "items"` instead of
    `required: ["items"]`."""
    bad: list[tuple[str, object]] = []
    for d in descriptors:
        if d.output_schema is None:
            continue
        if "required" not in d.output_schema:
            continue
        req = d.output_schema["required"]
        if not isinstance(req, list) or not all(isinstance(k, str) for k in req):
            bad.append((d.name, req))
    assert not bad, (
        f"{len(bad)} tool(s) have malformed `required` in outputSchema: {bad}"
    )


def test_input_schemas_are_objects(descriptors):
    """Same MCP-spec rule applies to input_schema: it's always an
    object since the `arguments` field of tools/call is always an
    object. Caught one of these earlier today; pin the invariant."""
    violations: list[tuple[str, str]] = []
    for d in descriptors:
        if not isinstance(d.input_schema, dict):
            violations.append((d.name, f"not a dict: {type(d.input_schema).__name__}"))
            continue
        if d.input_schema.get("type") != "object":
            violations.append((d.name, f"top-level type={d.input_schema.get('type')!r}"))

    assert not violations, (
        f"{len(violations)} tool(s) have invalid input_schema:\n"
        + "\n".join(f"  - {name}: {detail}" for name, detail in violations)
    )
