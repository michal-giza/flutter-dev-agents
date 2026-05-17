"""start_wda_on_simulator — spawn xcodebuild against a sim, wait for WDA.

Companion to test_wda_factory.py: K1 detects WDA-not-running, this tool
starts it. Hermetic — we never actually invoke xcodebuild. Tests cover:

  - missing wda_dir → setup_webdriveragent next_action
  - missing .xcodeproj → setup_webdriveragent next_action
  - WDA already listening (port open) → fast-path success, pid=0
  - xcodebuild not on PATH → install_xcode_command_line_tools

The "spawn and poll the port" success path is exercised by the
"already listening" test (which is structurally the same — we skip the
spawn and verify the result envelope shape). A true end-to-end spawn
test would require xcodebuild, which we can't assume in CI.
"""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_phone_controll.domain.usecases.wda_setup import (
    StartWdaOnSimulator,
    StartWdaOnSimulatorParams,
)


class _StubCli:
    """Doesn't matter for these tests — StartWdaOnSimulator currently
    spawns directly. Kept as a placeholder so the wiring matches
    container.py exactly."""


def _bind_listening_socket() -> tuple[int, socket.socket]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s.getsockname()[1], s


def _make_wda_dir(tmp_path: Path) -> Path:
    """Create a fake WDA checkout structure that passes both existence
    checks (wda_dir + wda_dir/WebDriverAgent.xcodeproj)."""
    wda = tmp_path / "WebDriverAgent"
    wda.mkdir()
    proj = wda / "WebDriverAgent.xcodeproj"
    proj.mkdir()
    return wda


# ---- guards ------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejects_empty_udid():
    res = await StartWdaOnSimulator(_StubCli()).execute(
        StartWdaOnSimulatorParams(udid="")
    )
    assert not res.is_ok
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_missing_wda_dir_returns_setup_action(tmp_path: Path):
    res = await StartWdaOnSimulator(_StubCli()).execute(
        StartWdaOnSimulatorParams(
            udid="SIM-UDID", wda_dir=tmp_path / "does-not-exist"
        )
    )
    assert not res.is_ok
    # Routing the agent to setup_webdriveragent is the load-bearing
    # contract here — without it, the agent has no recovery path.
    assert res.failure.next_action == "setup_webdriveragent"


@pytest.mark.asyncio
async def test_missing_xcodeproj_returns_setup_action(tmp_path: Path):
    wda = tmp_path / "WebDriverAgent"
    wda.mkdir()  # exists but doesn't have WebDriverAgent.xcodeproj inside
    res = await StartWdaOnSimulator(_StubCli()).execute(
        StartWdaOnSimulatorParams(udid="SIM-UDID", wda_dir=wda)
    )
    assert not res.is_ok
    assert res.failure.next_action == "setup_webdriveragent"


# ---- fast path: WDA already running -----------------------------------


@pytest.mark.asyncio
async def test_fast_path_when_wda_already_listening(tmp_path: Path):
    """If something already bound the WDA port (user started it
    manually, or a previous call's xcodebuild is still alive), we
    short-circuit: no spawn, pid=0, ready=True, elapsed_s=0."""
    wda = _make_wda_dir(tmp_path)
    port, sock = _bind_listening_socket()
    try:
        res = await StartWdaOnSimulator(_StubCli()).execute(
            StartWdaOnSimulatorParams(udid="SIM-UDID", wda_dir=wda, port=port)
        )
        assert res.is_ok
        out = res.value
        assert out.ready is True
        assert out.pid == 0  # didn't spawn
        assert out.port == port
        assert out.elapsed_s == 0.0
    finally:
        sock.close()


# ---- xcodebuild not installed -----------------------------------------


@pytest.mark.asyncio
async def test_xcodebuild_missing_returns_install_action(tmp_path: Path):
    wda = _make_wda_dir(tmp_path)

    async def _raise_fnf(*a, **k):
        raise FileNotFoundError("xcodebuild")

    # Patch asyncio.create_subprocess_exec inside the use case module.
    # Pick a port that's free so the fast path doesn't trigger.
    free_port = _pick_free_port()
    with patch(
        "mcp_phone_controll.domain.usecases.wda_setup.asyncio.create_subprocess_exec",
        new=_raise_fnf,
    ):
        res = await StartWdaOnSimulator(_StubCli()).execute(
            StartWdaOnSimulatorParams(
                udid="SIM-UDID", wda_dir=wda, port=free_port,
                ready_timeout_s=2.0,
            )
        )
    assert not res.is_ok
    assert res.failure.next_action == "install_xcode_command_line_tools"


# ---- spawn-then-timeout path -------------------------------------------


@pytest.mark.asyncio
async def test_spawn_then_timeout_kills_xcodebuild(tmp_path: Path):
    """When xcodebuild starts but WDA never comes up on the port, we
    must terminate the spawned process and return a structured failure
    with elapsed_s recorded so the agent can decide whether to retry
    or escalate."""
    wda = _make_wda_dir(tmp_path)
    free_port = _pick_free_port()

    class _FakeProc:
        def __init__(self):
            self.pid = 99999
            self.returncode = None
            self.terminated = False

        def terminate(self):
            self.terminated = True
            self.returncode = -15

    proc = _FakeProc()

    async def _fake_spawn(*a, **k):
        return proc

    with patch(
        "mcp_phone_controll.domain.usecases.wda_setup.asyncio.create_subprocess_exec",
        new=_fake_spawn,
    ):
        res = await StartWdaOnSimulator(_StubCli()).execute(
            StartWdaOnSimulatorParams(
                udid="SIM-UDID", wda_dir=wda, port=free_port,
                ready_timeout_s=1.0,  # quick timeout for test speed
            )
        )

    assert not res.is_ok
    assert res.failure.next_action == "check_xcode_signing"
    assert "elapsed_s" in res.failure.details
    assert proc.terminated is True  # we cleaned up the spawn


@pytest.mark.asyncio
async def test_spawn_xcodebuild_exits_early_with_returncode(tmp_path: Path):
    """If xcodebuild itself errors out before WDA comes up (e.g.
    signing failure), we should bail with the returncode in the
    failure message instead of waiting the full timeout."""
    wda = _make_wda_dir(tmp_path)
    free_port = _pick_free_port()

    class _DeadProc:
        def __init__(self):
            self.pid = 99998
            self.returncode = 65  # classic xcodebuild signing-failure code

        def terminate(self):
            pass

    async def _fake_spawn(*a, **k):
        return _DeadProc()

    with patch(
        "mcp_phone_controll.domain.usecases.wda_setup.asyncio.create_subprocess_exec",
        new=_fake_spawn,
    ):
        # Don't sleep too long — the use case sleeps 500ms between polls.
        # With timeout 3s + an immediate dead proc, we'll fail on the
        # first poll iteration.
        res = await asyncio.wait_for(
            StartWdaOnSimulator(_StubCli()).execute(
                StartWdaOnSimulatorParams(
                    udid="SIM-UDID", wda_dir=wda, port=free_port,
                    ready_timeout_s=3.0,
                )
            ),
            timeout=3.0,
        )

    assert not res.is_ok
    assert "returncode=65" in res.failure.message


def _pick_free_port() -> int:
    """Bind, get the port, immediately release. Good enough for tests —
    on a contended CI box another process could snag it before our
    code re-binds, but the failure mode of THAT is also test-friendly
    (the fast-path triggers, not the spawn path)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p
