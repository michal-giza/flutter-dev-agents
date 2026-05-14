"""Observability — structured logging in text + JSON, quiet mode."""

from __future__ import annotations

import json


def test_quiet_mode_emits_nothing(monkeypatch, capsys):
    monkeypatch.setenv("MCP_QUIET", "1")
    monkeypatch.delenv("MCP_LOG_FORMAT", raising=False)
    # Force fresh module read since the format check runs per-call.
    from mcp_phone_controll import observability

    observability.info("test_event", k="v")
    captured = capsys.readouterr()
    assert captured.err == ""


def test_text_mode_human_readable(monkeypatch, capsys):
    monkeypatch.delenv("MCP_QUIET", raising=False)
    monkeypatch.delenv("MCP_LOG_FORMAT", raising=False)
    from mcp_phone_controll import observability

    observability.info("boot", version="0.1.0", n_tools=105)
    line = capsys.readouterr().err.strip()
    assert "[phone-controll INFO]" in line
    assert "boot" in line
    assert "version=0.1.0" in line
    assert "n_tools=105" in line


def test_json_mode_emits_valid_lines(monkeypatch, capsys):
    monkeypatch.delenv("MCP_QUIET", raising=False)
    monkeypatch.setenv("MCP_LOG_FORMAT", "json")
    from mcp_phone_controll import observability

    observability.warn("cap_failed", path="/a.png", reason="missing-backend")
    line = capsys.readouterr().err.strip()
    payload = json.loads(line)
    assert payload["event"] == "cap_failed"
    assert payload["level"] == "warn"
    assert payload["path"] == "/a.png"
    assert payload["reason"] == "missing-backend"
    assert "ts" in payload
    assert payload["pid"] > 0


def test_error_helper_uses_error_level(monkeypatch, capsys):
    monkeypatch.delenv("MCP_QUIET", raising=False)
    monkeypatch.setenv("MCP_LOG_FORMAT", "json")
    from mcp_phone_controll import observability

    observability.error("backend_unreachable", url="http://x")
    payload = json.loads(capsys.readouterr().err.strip())
    assert payload["level"] == "error"
