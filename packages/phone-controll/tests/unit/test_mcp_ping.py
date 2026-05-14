"""mcp_ping — version handshake to detect stale MCP subprocesses."""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.usecases.base import NoParams
from mcp_phone_controll.domain.usecases.mcp_ping import McpPing


@pytest.mark.asyncio
async def test_mcp_ping_returns_required_fields():
    uc = McpPing(n_tools_provider=lambda: 99)
    res = await uc.execute(NoParams())
    assert res.is_ok
    info = res.value
    # Every diagnostic field must be present (even if "unknown") so the
    # agent's stale-subprocess-detection logic can rely on them.
    assert isinstance(info.package_version, str)
    assert isinstance(info.git_sha, str)
    assert isinstance(info.git_branch, str)
    assert isinstance(info.git_dirty, bool)
    assert isinstance(info.started_at, str)
    assert info.uptime_s >= 0
    assert info.python_version.count(".") == 2
    assert info.pid > 0
    assert isinstance(info.image_backends, tuple)
    assert info.n_tools == 99


@pytest.mark.asyncio
async def test_mcp_ping_reports_image_backends_when_available():
    """At least one of cv2/PIL/sips should be available in the test env
    (sips on Mac, cv2 from the [ar] extra). The diagnostic must list it."""
    uc = McpPing(n_tools_provider=lambda: 0)
    res = await uc.execute(NoParams())
    assert res.is_ok
    backends = set(res.value.image_backends)
    # At least one must be present — otherwise the cap would silently
    # fail and the dispatcher seatbelt would refuse every screenshot.
    assert backends, "no image-cap backend detected — install cv2/PIL or run on macOS"
    assert backends.issubset({"cv2", "PIL", "sips"})


@pytest.mark.asyncio
async def test_describe_capabilities_includes_version_handshake():
    """The version SHA must ride along on describe_capabilities so an
    agent observing a missing feature can diagnose stale-subprocess
    without a second tool call."""
    from pathlib import Path

    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    dispatcher = _build_fake_dispatcher(Path("/tmp"))
    res = await dispatcher.dispatch("describe_capabilities", {"level": "basic"})
    assert res["ok"]
    data = res["data"]
    assert "mcp_version" in data
    assert "mcp_git_sha" in data
    # SHA should be 7-ish chars from `git rev-parse --short` OR the
    # literal "unknown" when not running in a git checkout.
    assert isinstance(data["mcp_git_sha"], str)
    assert len(data["mcp_git_sha"]) >= 4
