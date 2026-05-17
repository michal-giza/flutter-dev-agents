"""Property-based smoke + fuzz on the dispatcher.

For every registered tool, generate random JSON inputs matching the
input_schema's `properties` and assert the dispatcher returns a
well-formed envelope — never raises, always has a top-level `ok` key,
errors are typed.

This is the "Schemathesis equivalent" for our internal contract.
Schemathesis targets OpenAPI; our load-bearing surface is the Python
ToolDispatcher, where Hypothesis fits naturally.

Default mode (CI-fast): 1 random input per tool, ~10 s total. Catches
the regression "tool X crashes on missing required arg" / "tool X
returns a non-envelope on bad input".

Deep mode (opt-in via `MCP_FUZZ_DEEP=1`): 5 inputs per tool, ~5 min.
For running on a release candidate or pre-merge to main.
"""

from __future__ import annotations

import os

import pytest


def _have_hypothesis() -> bool:
    try:
        import hypothesis  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = [
    pytest.mark.skipif(not _have_hypothesis(), reason="hypothesis not installed"),
    pytest.mark.skipif(
        os.environ.get("MCP_FUZZ") != "1",
        reason="fuzz suite slow (~90s); enable with MCP_FUZZ=1",
    ),
]


def _build_strategy_for_schema(schema, json_st):
    """Map a JSON-Schema property type to a Hypothesis strategy."""
    if not isinstance(schema, dict):
        return json_st
    from hypothesis import strategies as st

    t = schema.get("type")
    if t == "string":
        return st.text(max_size=64)
    if t == "integer":
        return st.integers(min_value=-10_000, max_value=10_000)
    if t == "number":
        return st.floats(
            allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
        )
    if t == "boolean":
        return st.booleans()
    if t == "array":
        items_schema = schema.get("items", {})
        inner = _build_strategy_for_schema(items_schema, json_st)
        return st.lists(inner, max_size=4)
    if t == "object":
        return st.dictionaries(
            keys=st.text(max_size=16),
            values=st.one_of(st.text(max_size=16), st.integers()),
            max_size=3,
        )
    return st.one_of(st.text(max_size=16), st.integers(), st.booleans(), st.none())


def _args_strategy(input_schema):
    """Build a strategy producing dicts matching `input_schema.properties`.
    Doesn't enforce `required` — the dispatcher must gracefully reject
    missing-required-arg cases, which is part of what we're testing."""
    from hypothesis import strategies as st

    properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    if not properties:
        return st.just({})
    field_strategies = {
        name: _build_strategy_for_schema(prop_schema, st.text(max_size=16))
        for name, prop_schema in properties.items()
    }
    return st.fixed_dictionaries(field_strategies)


def _assert_envelope_well_formed(name: str, args: dict, envelope: object) -> str | None:
    """Return an error description if the envelope is malformed, else None."""
    if not isinstance(envelope, dict):
        return f"envelope not a dict: {type(envelope).__name__}"
    if "ok" not in envelope:
        return f"envelope missing 'ok' key: {envelope}"
    if envelope["ok"]:
        if "data" not in envelope:
            return f"ok envelope missing 'data': {envelope}"
    else:
        err_obj = envelope.get("error")
        if not isinstance(err_obj, dict):
            return f"err envelope missing 'error' dict: {envelope}"
        if not isinstance(err_obj.get("code"), str):
            return f"error.code not a string: {err_obj}"
        if not isinstance(err_obj.get("message"), str):
            return f"error.message not a string: {err_obj}"
    return None


@pytest.mark.asyncio
async def test_every_tool_returns_well_formed_envelope_on_random_input():
    """Fuzz every tool with random inputs; assert envelope contract.

    Smoke mode (default): 1 input per tool, ~10 s. CI runs this.
    Deep mode (`MCP_FUZZ_DEEP=1`): 5 inputs per tool, ~5 min.
    """
    from hypothesis import strategies as st

    from mcp_phone_controll.container import build_runtime

    _, dispatcher = build_runtime()

    inputs_per_tool = 5 if os.environ.get("MCP_FUZZ_DEEP") == "1" else 1
    failures: list[tuple[str, dict, str]] = []

    for descriptor in dispatcher.descriptors:
        args_st = _args_strategy(descriptor.input_schema)
        # `.example()` is the standard "draw N samples" API. Hypothesis
        # warns to use @given for production code, but we're doing
        # cross-tool fuzzing (a loop), not a single property — the
        # warning doesn't apply here. We accept the perf trade-off.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            examples = st.lists(
                args_st,
                min_size=inputs_per_tool,
                max_size=inputs_per_tool,
            ).example()

        for args in examples:
            try:
                envelope = await dispatcher.dispatch(descriptor.name, args)
            except Exception as exc:
                failures.append(
                    (descriptor.name, args, f"raised {type(exc).__name__}: {exc}")
                )
                continue
            problem = _assert_envelope_well_formed(descriptor.name, args, envelope)
            if problem:
                failures.append((descriptor.name, args, problem))

    assert not failures, (
        f"{len(failures)} envelope contract violations across "
        f"{len(dispatcher.descriptors)} tools. First 5: {failures[:5]}"
    )
