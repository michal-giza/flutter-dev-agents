"""HTTP-adapter auth — `MCP_HTTP_API_KEY` gates `/tools` + `/tools/{name}`."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mcp_phone_controll.adapters.openai_compat import _strip_bearer, create_app


def test_strip_bearer_handles_both_forms():
    assert _strip_bearer("Bearer abc123") == "abc123"
    assert _strip_bearer("bearer abc123") == "abc123"
    assert _strip_bearer("abc123") == "abc123"
    assert _strip_bearer("") == ""


class _FakeDispatcher:
    """Minimal dispatcher stub for adapter tests."""

    descriptors: list = []  # noqa: RUF012 — intentional class-level empty list for stubbing

    @staticmethod
    def has(_name: str) -> bool: return True

    @staticmethod
    async def dispatch(_name: str, _args):
        return {"ok": True, "data": "fake"}


def test_no_key_set_is_open(monkeypatch):
    """Default: MCP_HTTP_API_KEY unset → everyone can call."""
    monkeypatch.delenv("MCP_HTTP_API_KEY", raising=False)
    app = create_app(dispatcher=_FakeDispatcher())
    client = TestClient(app)
    r = client.post("/tools/some_tool", json={})
    assert r.status_code == 200


def test_set_key_rejects_missing_header(monkeypatch):
    monkeypatch.setenv("MCP_HTTP_API_KEY", "super-secret")
    app = create_app(dispatcher=_FakeDispatcher())
    client = TestClient(app)
    r = client.post("/tools/some_tool", json={})
    assert r.status_code == 401


def test_set_key_accepts_x_api_key_header(monkeypatch):
    monkeypatch.setenv("MCP_HTTP_API_KEY", "super-secret")
    app = create_app(dispatcher=_FakeDispatcher())
    client = TestClient(app)
    r = client.post(
        "/tools/some_tool", json={}, headers={"X-Api-Key": "super-secret"}
    )
    assert r.status_code == 200


def test_set_key_accepts_bearer_header(monkeypatch):
    monkeypatch.setenv("MCP_HTTP_API_KEY", "super-secret")
    app = create_app(dispatcher=_FakeDispatcher())
    client = TestClient(app)
    r = client.post(
        "/tools/some_tool", json={},
        headers={"Authorization": "Bearer super-secret"},
    )
    assert r.status_code == 200


def test_wrong_key_rejected(monkeypatch):
    monkeypatch.setenv("MCP_HTTP_API_KEY", "super-secret")
    app = create_app(dispatcher=_FakeDispatcher())
    client = TestClient(app)
    r = client.post(
        "/tools/some_tool", json={}, headers={"X-Api-Key": "wrong"}
    )
    assert r.status_code == 401


def test_list_tools_also_gated(monkeypatch):
    monkeypatch.setenv("MCP_HTTP_API_KEY", "super-secret")
    app = create_app(dispatcher=_FakeDispatcher())
    client = TestClient(app)
    r = client.get("/tools")
    assert r.status_code == 401
    r = client.get("/tools", headers={"X-Api-Key": "super-secret"})
    assert r.status_code == 200
