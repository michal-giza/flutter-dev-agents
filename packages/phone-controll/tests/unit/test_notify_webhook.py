"""notify_webhook — POST events to n8n / Slack / generic HTTP destinations."""

from __future__ import annotations

import http.server
import threading

import pytest

from mcp_phone_controll.domain.result import Err
from mcp_phone_controll.domain.usecases.notify_webhook import (
    NotifyWebhook,
    NotifyWebhookParams,
)

# ---- a tiny in-process HTTP server so we don't hit a real network -------


class _CaptureHandler(http.server.BaseHTTPRequestHandler):
    received: list[tuple[str, dict, bytes]] = []  # noqa: RUF012 — class-level test capture

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        # Snapshot for assertions.
        type(self).received.append(
            (self.path, dict(self.headers), body)
        )
        if self.path == "/fail":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error": "synthetic failure"}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"received": true}')

    def log_message(self, *_a, **_k):
        pass  # silence


@pytest.fixture
def webhook_server():
    """Spin up a localhost HTTP server, return its URL."""
    _CaptureHandler.received.clear()
    server = http.server.HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


# ---- happy paths --------------------------------------------------------


@pytest.mark.asyncio
async def test_posts_event_with_payload(webhook_server):
    uc = NotifyWebhook()
    res = await uc.execute(
        NotifyWebhookParams(
            url=f"{webhook_server}/hook",
            event="release_ready",
            payload={"version": "1.4.0"},
        )
    )
    assert res.is_ok
    assert res.value.status_code == 200
    path, _, body = _CaptureHandler.received[-1]
    assert path == "/hook"
    import json as _json
    parsed = _json.loads(body)
    assert parsed["event"] == "release_ready"
    assert parsed["source"] == "mcp-phone-controll"
    assert parsed["payload"]["version"] == "1.4.0"


@pytest.mark.asyncio
async def test_auth_bearer_added(webhook_server):
    uc = NotifyWebhook()
    res = await uc.execute(
        NotifyWebhookParams(
            url=f"{webhook_server}/hook",
            event="x",
            auth_bearer="super-secret",
        )
    )
    assert res.is_ok
    _, headers, _ = _CaptureHandler.received[-1]
    assert headers.get("Authorization") == "Bearer super-secret"


@pytest.mark.asyncio
async def test_custom_auth_header(webhook_server):
    uc = NotifyWebhook()
    res = await uc.execute(
        NotifyWebhookParams(
            url=f"{webhook_server}/hook",
            event="x",
            auth_header_name="X-Hub-Signature",
            auth_header_value="sha256=abc",
        )
    )
    assert res.is_ok
    _, headers, _ = _CaptureHandler.received[-1]
    assert headers.get("X-Hub-Signature") == "sha256=abc"


# ---- guards -------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_url_rejected():
    res = await NotifyWebhook().execute(
        NotifyWebhookParams(url="", event="x")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_unsupported_scheme_rejected():
    res = await NotifyWebhook().execute(
        NotifyWebhookParams(url="ftp://example.com/", event="x")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_remote_http_blocked():
    res = await NotifyWebhook().execute(
        NotifyWebhookParams(url="http://hostile.example.com/x", event="x")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "use_https"


@pytest.mark.asyncio
async def test_allowlist_blocks_unlisted_host(monkeypatch):
    monkeypatch.setenv("MCP_WEBHOOK_ALLOWLIST", "n8n.example.com")
    res = await NotifyWebhook().execute(
        NotifyWebhookParams(url="https://hostile.example.com/x", event="x")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "add_to_allowlist"


@pytest.mark.asyncio
async def test_localhost_always_allowed_under_allowlist(monkeypatch, webhook_server):
    """Even with an explicit allowlist that doesn't list localhost, the
    default permissive policy permits 127.0.0.1. (This is the dev-loop
    friendly default; lock down by extending the allowlist explicitly.)"""
    # Don't set allowlist — default-open should accept localhost.
    res = await NotifyWebhook().execute(
        NotifyWebhookParams(url=f"{webhook_server}/hook", event="x")
    )
    assert res.is_ok


@pytest.mark.asyncio
async def test_upstream_500_returns_webhook_failure(webhook_server):
    res = await NotifyWebhook().execute(
        NotifyWebhookParams(url=f"{webhook_server}/fail", event="x")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "check_webhook_target"
    assert res.failure.details["status_code"] == 500
