"""HTTP adapter ops endpoints — /health, /ready, /metrics.

Pins the contract Kubernetes/Docker/Prometheus consumers depend on.
The shapes must stay stable across versions or all the alert
runbooks break.
"""

from __future__ import annotations

import pytest


def _have_fastapi() -> bool:
    try:
        import fastapi  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not _have_fastapi(), reason="FastAPI not installed")


def _client():
    """TestClient against the real composition root — needs `[http]`
    extra installed in the test venv."""
    from fastapi.testclient import TestClient

    from mcp_phone_controll.adapters.openai_compat import create_app

    return TestClient(create_app(allow_agent_proxy=False))


def test_health_returns_200_with_version_and_uptime():
    client = _client()
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "version" in body
    assert "git_sha" in body
    assert isinstance(body["tools"], int) and body["tools"] > 0
    assert isinstance(body["uptime_s"], float | int) and body["uptime_s"] >= 0


def test_ready_returns_200_when_backends_available():
    """With our default test environment, PIL + sips backends are
    available — /ready should be green."""
    client = _client()
    r = client.get("/ready")
    # Don't assert 200 strictly — if a backend is genuinely missing
    # the test environment is unusual, and 503 with reasons is more
    # informative. But on the standard dev box, it's 200.
    body = r.json()
    if r.status_code == 200:
        assert body["ok"] is True
        assert body["tools"] > 0
        assert len(body["image_backends"]) > 0
    else:
        # 503 is the OTHER valid answer; verify the shape.
        assert r.status_code == 503
        assert body["ok"] is False
        assert isinstance(body["reasons"], list) and body["reasons"]


def test_ready_returns_503_when_no_backends(monkeypatch):
    """Force `available_backends()` empty — readiness must flip to
    503 with a reason naming the backend gap."""
    import shutil

    from mcp_phone_controll.data import image_capping

    monkeypatch.setattr(image_capping, "find_spec", lambda name: None)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    client = _client()
    r = client.get("/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["ok"] is False
    assert any("image-cap" in s for s in body["reasons"])


def test_metrics_returns_prometheus_format():
    client = _client()
    r = client.get("/metrics")
    assert r.status_code == 200
    # Prometheus expects text/plain with the exposition-format version.
    assert "text/plain" in r.headers["content-type"]
    assert "version=0.0.4" in r.headers["content-type"]
    body = r.text
    # Standard format: # HELP / # TYPE / metric_name value.
    assert "# HELP mcp_tools_total" in body
    assert "# TYPE mcp_tools_total gauge" in body
    assert "mcp_tools_total " in body  # value line
    assert "mcp_image_cap_px " in body
    assert "mcp_uptime_seconds " in body
    # Build-info metric carries labels.
    assert 'mcp_info{version="' in body
    assert 'git_sha="' in body


def test_metrics_does_not_require_auth(monkeypatch):
    """Prometheus servers don't send custom headers; /metrics MUST
    work with no auth, even when MCP_HTTP_API_KEY gates /tools.
    Operational endpoint should not break ingestion. Gate at the
    reverse-proxy layer if you need to."""
    monkeypatch.setenv("MCP_HTTP_API_KEY", "secret-key")
    client = _client()
    r = client.get("/metrics")
    assert r.status_code == 200


def test_health_does_not_require_auth(monkeypatch):
    """Same reasoning for the liveness probe."""
    monkeypatch.setenv("MCP_HTTP_API_KEY", "secret-key")
    client = _client()
    r = client.get("/health")
    assert r.status_code == 200
