"""Strict-schema flag for the OpenAI function-call adapter."""

from __future__ import annotations

from mcp_phone_controll.adapters.schemas import (
    to_openai_function,
    to_openai_functions,
)
from mcp_phone_controll.presentation.tool_registry import ToolDescriptor

_DESC = ToolDescriptor(
    name="example",
    description="x",
    input_schema={"type": "object", "properties": {}, "required": []},
    build_params=lambda a: a,
    invoke=lambda a: a,
)


def test_default_omits_strict_flag():
    out = to_openai_function(_DESC, strict=False)
    assert "strict" not in out["function"]


def test_strict_true_emits_flag():
    out = to_openai_function(_DESC, strict=True)
    assert out["function"]["strict"] is True


def test_env_var_drives_default(monkeypatch):
    monkeypatch.setenv("MCP_STRICT_TOOLS", "true")
    out = to_openai_function(_DESC)  # strict=None → falls back to env
    assert out["function"]["strict"] is True


def test_env_var_off_by_default(monkeypatch):
    monkeypatch.delenv("MCP_STRICT_TOOLS", raising=False)
    out = to_openai_function(_DESC)
    assert "strict" not in out["function"]


def test_to_openai_functions_propagates_flag():
    arr = to_openai_functions([_DESC, _DESC], strict=True)
    assert all(f["function"]["strict"] is True for f in arr)
