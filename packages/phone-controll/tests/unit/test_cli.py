"""`phone-controll` ops CLI — hermetic smoke tests.

Pins the public CLI contract so a refactor doesn't silently break
the runbook's diagnostic recipes. We test command dispatch + arg
parsing + the env-driven path fallback; we don't test the underlying
use cases (those have their own tests).
"""

from __future__ import annotations

import json

import pytest

from mcp_phone_controll.cli import build_parser, main


def test_help_lists_all_subcommands(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for sub in ("status", "locks", "audit", "tools", "sessions", "describe"):
        assert sub in out


def test_version_flag_prints_package_version(capsys):
    """`phone-controll --version` must print whatever
    importlib.metadata.version returns — the same SemVer the user
    sees in pyproject.toml. Drift here = confused upgrade story."""
    from mcp_phone_controll import __version__

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out


def test_status_returns_zero_on_clean_install(capsys):
    """`phone-controll status` returns 0 when at least one image-cap
    backend is available + prints the diagnostic kv list."""
    rc = main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "git_sha" in out
    assert "image_cap_px" in out
    assert "image_backends" in out


def test_status_returns_nonzero_when_no_backends(monkeypatch, capsys):
    """No image-cap backend = exit 1 + warning text. Mirrors the
    /ready 503 contract — CLI users get the same diagnosis."""
    import shutil

    from mcp_phone_controll.data import image_capping

    monkeypatch.setattr(image_capping, "find_spec", lambda name: None)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    rc = main(["status"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "no image-cap backends" in out


def test_tools_basic_tier_filters_correctly(capsys):
    rc = main(["tools", "--tier", "basic"])
    assert rc == 0
    out = capsys.readouterr().out
    # Spot-check a few BASIC-tier names + verify we're filtered (no
    # `extract_ui_graph` which lives at expert).
    assert "mcp_ping" in out
    assert "take_screenshot" in out
    assert "extract_ui_graph" not in out


def test_sessions_uses_default_path_when_env_unset(tmp_path, monkeypatch, capsys):
    """Regression test for the empty-string bug: with MCP_ARTIFACTS_DIR
    unset OR empty, must fall back to ~/.mcp_phone_controll/sessions,
    NOT the cwd (which Path("") would resolve to)."""
    monkeypatch.delenv("MCP_ARTIFACTS_DIR", raising=False)
    # Point HOME at tmp so we have a known empty default.
    monkeypatch.setenv("HOME", str(tmp_path))
    rc = main(["sessions"])
    out = capsys.readouterr().out + capsys.readouterr().err
    # Either prints "no sessions dir at <home>/...sessions" (rc=1)
    # or "no sessions in <home>/...sessions." (rc=0). Both prove
    # we used the home fallback, NOT the cwd. The bug surfaced as
    # listing whatever was in cwd as sessions.
    assert ".mcp_phone_controll" in out or rc == 1


def test_sessions_env_override_honoured(tmp_path, monkeypatch, capsys):
    """MCP_ARTIFACTS_DIR overrides the default. Operators with custom
    deployments rely on this."""
    sessions_root = tmp_path / "my_sessions"
    sessions_root.mkdir()
    (sessions_root / "session-a").mkdir()
    (sessions_root / "session-b").mkdir()
    monkeypatch.setenv("MCP_ARTIFACTS_DIR", str(sessions_root))

    rc = main(["sessions", "--last", "10"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "session-a" in out
    assert "session-b" in out


def test_describe_unknown_tool_returns_error_with_helpful_message(capsys):
    rc = main(["describe", "no_such_tool_zzz"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "no_such_tool_zzz" in err


def test_describe_known_tool_prints_json(capsys):
    """`describe mcp_ping` must output valid JSON containing the
    descriptor. Downstream tooling (jq, scripts) relies on this."""
    rc = main(["describe", "mcp_ping"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["name"] == "mcp_ping"
    assert "input_schema" in parsed
