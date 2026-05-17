"""adapters/__main__.py — the HTTP adapter entry point (mcp-phone-controll-http).

Coverage gap caught in code-review-2026-05-18 §2 — was 0% covered
despite being the entry point for every HTTP deployment. A bug here
fails silently in CI just like the mcp_server.py gap we fixed earlier.

Hermetic: fakes `uvicorn.run` + `create_app` so we never actually
bind a socket.
"""

from __future__ import annotations

import sys
import types

import pytest


def _install_fake_uvicorn(monkeypatch, captured: list[dict]) -> None:
    """Inject a fake `uvicorn` module that records the call instead of
    binding a port. Replicates the install-fail path too."""

    def _fake_run(app, host: str, port: int, log_level: str = "info"):
        captured.append({"app": app, "host": host, "port": port, "log_level": log_level})

    fake_mod = types.ModuleType("uvicorn")
    fake_mod.run = _fake_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_mod)


def test_default_host_port_run(monkeypatch):
    """Calling `main()` with no args binds to 127.0.0.1:8765 — the
    safe localhost default. If anyone changes the default to 0.0.0.0
    without a security review, this test breaks."""
    captured: list[dict] = []
    _install_fake_uvicorn(monkeypatch, captured)
    monkeypatch.setattr(sys, "argv", ["mcp-phone-controll-http"])
    # Patch create_app so we don't build the real runtime (slow).
    fake_app = object()
    monkeypatch.setattr(
        "mcp_phone_controll.adapters.openai_compat.create_app",
        lambda **kw: fake_app,
    )

    from mcp_phone_controll.adapters.__main__ import main

    main()

    assert len(captured) == 1
    assert captured[0]["host"] == "127.0.0.1"
    assert captured[0]["port"] == 8765
    assert captured[0]["app"] is fake_app


def test_env_vars_override_defaults(monkeypatch):
    """MCP_HTTP_HOST + MCP_HTTP_PORT must be honoured — Docker/Kubernetes
    deployments rely on env-driven config."""
    captured: list[dict] = []
    _install_fake_uvicorn(monkeypatch, captured)
    monkeypatch.setenv("MCP_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_HTTP_PORT", "9000")
    monkeypatch.setattr(sys, "argv", ["mcp-phone-controll-http"])
    monkeypatch.setattr(
        "mcp_phone_controll.adapters.openai_compat.create_app",
        lambda **kw: object(),
    )

    from mcp_phone_controll.adapters.__main__ import main

    main()
    assert captured[0]["host"] == "0.0.0.0"
    assert captured[0]["port"] == 9000


def test_cli_args_override_env(monkeypatch):
    """Explicit `--host` / `--port` win over env vars — standard CLI
    precedence rule."""
    captured: list[dict] = []
    _install_fake_uvicorn(monkeypatch, captured)
    monkeypatch.setenv("MCP_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_HTTP_PORT", "9000")
    monkeypatch.setattr(
        sys, "argv",
        ["mcp-phone-controll-http", "--host", "192.168.1.10", "--port", "7777"],
    )
    monkeypatch.setattr(
        "mcp_phone_controll.adapters.openai_compat.create_app",
        lambda **kw: object(),
    )

    from mcp_phone_controll.adapters.__main__ import main

    main()
    assert captured[0]["host"] == "192.168.1.10"
    assert captured[0]["port"] == 7777


def test_no_agent_proxy_flag_propagates(monkeypatch):
    """--no-agent-proxy must pass allow_agent_proxy=False to create_app.
    Otherwise users who deliberately disable the LLM-proxy endpoint
    (e.g. on a hardened deployment) get it back anyway."""
    captured: list[dict] = []
    _install_fake_uvicorn(monkeypatch, captured)
    create_app_kwargs: dict = {}

    def _fake_create_app(**kw):
        create_app_kwargs.update(kw)
        return object()

    monkeypatch.setattr(sys, "argv", ["mcp-phone-controll-http", "--no-agent-proxy"])
    monkeypatch.setattr(
        "mcp_phone_controll.adapters.openai_compat.create_app",
        _fake_create_app,
    )

    from mcp_phone_controll.adapters.__main__ import main

    main()
    assert create_app_kwargs["allow_agent_proxy"] is False


def test_missing_uvicorn_exits_with_install_hint(monkeypatch):
    """If uvicorn isn't installed, the entry-point must SystemExit with
    a clear `uv pip install -e ".[http]"` hint — not a bare ImportError
    traceback that confuses users."""
    monkeypatch.setattr(sys, "argv", ["mcp-phone-controll-http"])
    # Wipe both uvicorn from sys.modules AND make the import fail
    # by setting it to None (Python's standard "block this import"
    # trick).
    monkeypatch.setitem(sys.modules, "uvicorn", None)

    from mcp_phone_controll.adapters.__main__ import main

    with pytest.raises(SystemExit) as excinfo:
        main()
    assert "uvicorn" in str(excinfo.value).lower()
    assert "[http]" in str(excinfo.value)
