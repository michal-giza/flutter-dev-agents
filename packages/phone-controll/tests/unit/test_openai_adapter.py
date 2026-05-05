"""HTTP adapter tests via FastAPI TestClient."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from mcp_phone_controll.adapters.openai_compat import create_app
from mcp_phone_controll.adapters.schemas import to_openai_functions
from mcp_phone_controll.presentation.tool_registry import ToolDispatcher


# Reuse the integration dispatcher builder from the dispatcher test module
from tests.integration.test_tool_dispatcher import _build_fake_dispatcher


def _client(tmp_path):
    dispatcher: ToolDispatcher = _build_fake_dispatcher(tmp_path)
    app = create_app(dispatcher=dispatcher, allow_agent_proxy=False)
    return TestClient(app)


def test_health_endpoint(tmp_path):
    client = _client(tmp_path)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["tools"] > 30


def test_list_tools_returns_openai_function_schemas(tmp_path):
    client = _client(tmp_path)
    r = client.get("/tools")
    assert r.status_code == 200
    tools = r.json()
    assert len(tools) > 30
    for tool in tools:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn and "description" in fn and "parameters" in fn
        assert fn["parameters"].get("type") == "object"


def test_call_tool_returns_envelope(tmp_path):
    client = _client(tmp_path)
    r = client.post("/tools/list_devices", json={})
    assert r.status_code == 200
    envelope = r.json()
    assert envelope["ok"] is True
    assert isinstance(envelope["data"], list)


def test_unknown_tool_returns_404(tmp_path):
    client = _client(tmp_path)
    r = client.post("/tools/nonexistent", json={})
    assert r.status_code == 404


def test_invalid_arguments_returns_envelope_not_500(tmp_path):
    client = _client(tmp_path)
    # select_device requires `serial`
    r = client.post("/tools/select_device", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "InvalidArgumentFailure"
    assert body["error"]["next_action"] == "fix_arguments"


def test_openapi_schema_is_valid(tmp_path):
    client = _client(tmp_path)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["openapi"].startswith("3.")
    paths = spec["paths"]
    assert "/tools" in paths
    assert "/tools/{name}" in paths


def test_agent_proxy_disabled_when_flagged_off(tmp_path):
    client = _client(tmp_path)
    r = client.post("/agent/chat", json={"messages": []})
    assert r.status_code == 404


def test_schema_converter_round_trips(tmp_path):
    dispatcher = _build_fake_dispatcher(tmp_path)
    fns = to_openai_functions(dispatcher.descriptors)
    names = {f["function"]["name"] for f in fns}
    assert {"list_devices", "run_patrol_test", "compare_screenshot", "describe_capabilities"} <= names
