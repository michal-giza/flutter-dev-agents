"""iOS 17+ RSD endpoint resolution + developer-tier CLI routing.

Why this exists: on iOS 17+, every `pymobiledevice3 developer dvt …`
subcommand requires `--rsd HOST PORT`. The older `--tunnel UDID`
shortcut returns "Failed to start service" on the DVT path. Tunneld
publishes the per-device RSD coordinates as a JSON blob at
`http://127.0.0.1:49151/` keyed by UDID:

    {"<UDID>": [{"tunnel-address": "fd6a:...", "tunnel-port": N, ...}]}

If we get this routing wrong, every `screenshot`, `launch`, `kill`, and
`syslog live` call on a real iPhone fails silently. The previous shape
of the code used `--tunnel UDID` for screenshot AND the deprecated
`developer screenshot` subcommand (not `developer dvt screenshot`),
which is the bug we shipped before iOS 17+ devices hit production
testing.

Tests:
  - resolve_rsd happy path returns RsdEndpoint from a real-shaped reply.
  - resolve_rsd handles every plausible degenerate input (tunneld
    not running, UDID absent, malformed JSON, port not an int).
  - PyMobileDevice3Cli.screenshot uses `developer dvt screenshot` AND
    `--rsd HOST PORT` when RSD is resolvable.
  - PyMobileDevice3Cli.screenshot falls back to `--tunnel UDID` if RSD
    can't be resolved (preserves the iOS 16 happy path).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.infrastructure import tunneld_probe
from mcp_phone_controll.infrastructure.process_runner import ProcessResult
from mcp_phone_controll.infrastructure.pymobiledevice3_cli import (
    PyMobileDevice3Cli,
)
from mcp_phone_controll.infrastructure.tunneld_probe import (
    RsdEndpoint,
    resolve_rsd,
)

# --- resolve_rsd unit tests -------------------------------------------------


def _patch_http(monkeypatch, body: str | None, raises: type[Exception] | None = None):
    def fake(url: str) -> str:
        if raises is not None:
            raise raises("boom")
        assert body is not None
        return body

    monkeypatch.setattr(tunneld_probe, "_http_get", fake)


UDID = "00008120-001A42542E30201E"


@pytest.mark.asyncio
async def test_resolve_rsd_happy_path(monkeypatch):
    _patch_http(
        monkeypatch,
        body='{"' + UDID + '": [{"tunnel-address": "fd6a:ecf5:e00::1", '
        '"tunnel-port": 62152, "interface": "usbmux-…-USB"}]}',
    )
    rsd = await resolve_rsd(UDID)
    assert rsd == RsdEndpoint(host="fd6a:ecf5:e00::1", port=62152)


@pytest.mark.asyncio
async def test_resolve_rsd_tunneld_unreachable_returns_none(monkeypatch):
    _patch_http(monkeypatch, body=None, raises=OSError)
    assert await resolve_rsd(UDID) is None


@pytest.mark.asyncio
async def test_resolve_rsd_udid_not_advertised(monkeypatch):
    _patch_http(monkeypatch, body='{"some-other-udid": [{"tunnel-port": 1}]}')
    assert await resolve_rsd(UDID) is None


@pytest.mark.asyncio
async def test_resolve_rsd_malformed_json(monkeypatch):
    _patch_http(monkeypatch, body="not-json{")
    assert await resolve_rsd(UDID) is None


@pytest.mark.asyncio
async def test_resolve_rsd_port_not_int(monkeypatch):
    _patch_http(
        monkeypatch,
        body='{"' + UDID + '": [{"tunnel-address": "::1", "tunnel-port": "62152"}]}',
    )
    # tunnel-port must be int per tunneld's contract; string means
    # tunneld misbehaved and we'd rather fall back than guess.
    assert await resolve_rsd(UDID) is None


@pytest.mark.asyncio
async def test_resolve_rsd_empty_tunnel_list(monkeypatch):
    _patch_http(monkeypatch, body='{"' + UDID + '": []}')
    assert await resolve_rsd(UDID) is None


# --- CLI routing tests ------------------------------------------------------


class _RecordingRunner:
    """ProcessRunner stub that records the argv it was asked to run."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def run(self, cmd: list[str], timeout_s: float) -> ProcessResult:
        self.calls.append(cmd)
        return ProcessResult(returncode=0, stdout="", stderr="")

    async def stream(self, cmd: list[str]):  # pragma: no cover (unused here)
        raise NotImplementedError


@pytest.mark.asyncio
async def test_screenshot_uses_dvt_subcommand_and_rsd_when_resolvable(monkeypatch):
    """The bug we shipped: `developer screenshot --tunnel UDID` is the
    deprecated lockdown API. The right invocation is `developer dvt
    screenshot --rsd HOST PORT`."""
    _patch_http(
        monkeypatch,
        body='{"' + UDID + '": [{"tunnel-address": "fd6a::1", '
        '"tunnel-port": 9999}]}',
    )
    runner = _RecordingRunner()
    cli = PyMobileDevice3Cli(runner=runner, binary="pymobiledevice3")  # type: ignore[arg-type]
    await cli.screenshot(UDID, Path("/tmp/x.png"))

    cmd = runner.calls[0]
    assert cmd[:4] == ["pymobiledevice3", "developer", "dvt", "screenshot"]
    assert "--rsd" in cmd
    rsd_idx = cmd.index("--rsd")
    assert cmd[rsd_idx + 1 : rsd_idx + 3] == ["fd6a::1", "9999"]
    assert "--tunnel" not in cmd


@pytest.mark.asyncio
async def test_screenshot_falls_back_to_tunnel_when_rsd_unresolvable(monkeypatch):
    """iOS 16 + older pymobiledevice3 setups never had tunneld; the
    `--tunnel UDID` shortcut must still work."""
    _patch_http(monkeypatch, body=None, raises=OSError)
    runner = _RecordingRunner()
    cli = PyMobileDevice3Cli(runner=runner, binary="pymobiledevice3")  # type: ignore[arg-type]
    await cli.screenshot(UDID, Path("/tmp/x.png"))

    cmd = runner.calls[0]
    assert cmd[:4] == ["pymobiledevice3", "developer", "dvt", "screenshot"]
    assert "--rsd" not in cmd
    assert "--tunnel" in cmd
    assert cmd[cmd.index("--tunnel") + 1] == UDID


@pytest.mark.asyncio
async def test_launch_and_kill_also_use_rsd_when_available(monkeypatch):
    """Same RSD requirement applies to dvt launch + kill on iOS 17+ —
    if we got screenshot wrong, those were latently wrong too."""
    _patch_http(
        monkeypatch,
        body='{"' + UDID + '": [{"tunnel-address": "::1", "tunnel-port": 7}]}',
    )
    runner = _RecordingRunner()
    cli = PyMobileDevice3Cli(runner=runner, binary="pymobiledevice3")  # type: ignore[arg-type]
    await cli.launch(UDID, "com.example.App")
    await cli.kill(UDID, "com.example.App")

    for cmd in runner.calls:
        assert "--rsd" in cmd
        assert "--tunnel" not in cmd
