"""start_wda_on_device — launch WDA on a PHYSICAL iPhone, wait over usbmux.

The device sibling of test_start_wda_on_simulator.py. Same shape, two real
differences it must pin:

  1. The launch argv targets the DEVICE destination (`platform=iOS,id=...`,
     NOT `platform=iOS Simulator,...`) and code-SIGNS the runner
     (DEVELOPMENT_TEAM + -allowProvisioningUpdates).
  2. Readiness is NOT a localhost-port probe — a device serves WDA over
     usbmux, so we poll `_wda_device_ready` (facebook-wda USBClient
     /status), which we patch here so tests never touch a real device.

Hermetic — we never invoke xcodebuild and never open usbmux.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_phone_controll.domain.usecases import wda_setup
from mcp_phone_controll.domain.usecases.wda_setup import (
    StartWdaOnDevice,
    StartWdaOnDeviceParams,
    _device_test_argv,
)


class _FakeCli:
    """Stands in for WdaSetupCli — only detect_is_simulator is used (the
    wrong-tool guard). Defaults to 'physical device' (False)."""

    def __init__(self, is_sim: bool = False) -> None:
        self._is_sim = is_sim

    async def detect_is_simulator(self, _udid, timeout_s: float = 15.0) -> bool:
        return self._is_sim


def _make_wda_dir(tmp_path: Path) -> Path:
    wda = tmp_path / "WebDriverAgent"
    wda.mkdir()
    (wda / "WebDriverAgent.xcodeproj").mkdir()
    return wda


# ---- the argv (device destination + signing) ---------------------------


def test_device_argv_targets_device_destination_not_simulator():
    argv = _device_test_argv("PHY-UDID", "WebDriverAgentRunner", 8100, None)
    dest = argv[argv.index("-destination") + 1]
    # Load-bearing: a real device, NOT a simulator destination.
    assert dest == "platform=iOS,id=PHY-UDID"
    assert " Simulator" not in dest
    assert "-allowProvisioningUpdates" in argv
    assert "USE_PORT=8100" in argv
    # No team → no DEVELOPMENT_TEAM (xcodebuild will use the project default).
    assert not any(a.startswith("DEVELOPMENT_TEAM=") for a in argv)


def test_device_argv_appends_team_when_provided():
    argv = _device_test_argv("PHY-UDID", "WebDriverAgentRunner", 8100, "ABCDE12345")
    assert "DEVELOPMENT_TEAM=ABCDE12345" in argv
    assert "CODE_SIGN_STYLE=Automatic" in argv


# ---- guards ------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejects_empty_udid():
    res = await StartWdaOnDevice(_FakeCli()).execute(StartWdaOnDeviceParams(udid=""))
    assert not res.is_ok
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_simulator_udid_routes_to_the_simulator_tool(tmp_path: Path):
    """A sim udid handed to the device tool is a wrong-tool call — route
    the agent to start_wda_on_simulator instead of trying to sign it."""
    wda = _make_wda_dir(tmp_path)
    res = await StartWdaOnDevice(_FakeCli(is_sim=True)).execute(
        StartWdaOnDeviceParams(udid="SIM-UDID", wda_dir=wda)
    )
    assert not res.is_ok
    assert res.failure.next_action == "start_wda_on_simulator"


@pytest.mark.asyncio
async def test_missing_wda_dir_returns_setup_action(tmp_path: Path):
    res = await StartWdaOnDevice(_FakeCli()).execute(
        StartWdaOnDeviceParams(udid="PHY-UDID", wda_dir=tmp_path / "nope")
    )
    assert not res.is_ok
    assert res.failure.next_action == "setup_webdriveragent"


@pytest.mark.asyncio
async def test_missing_xcodeproj_returns_setup_action(tmp_path: Path):
    wda = tmp_path / "WebDriverAgent"
    wda.mkdir()  # no .xcodeproj inside
    res = await StartWdaOnDevice(_FakeCli()).execute(
        StartWdaOnDeviceParams(udid="PHY-UDID", wda_dir=wda)
    )
    assert not res.is_ok
    assert res.failure.next_action == "setup_webdriveragent"


# ---- fast path: WDA already answering over usbmux ----------------------


@pytest.mark.asyncio
async def test_fast_path_when_wda_already_answering(tmp_path: Path):
    wda = _make_wda_dir(tmp_path)

    async def _ready_probe(_udid, _port=8100):
        return True

    with patch.object(wda_setup, "_wda_device_ready", _ready_probe):
        res = await StartWdaOnDevice(_FakeCli()).execute(
            StartWdaOnDeviceParams(udid="PHY-UDID", wda_dir=wda)
        )
    assert res.is_ok
    out = res.value
    assert out.ready is True
    assert out.pid == 0  # never spawned
    assert out.elapsed_s == 0.0


@pytest.mark.asyncio
async def test_probe_uses_the_requested_port(tmp_path: Path):
    """The launch binds WDA to params.port (USE_PORT); the readiness probe
    MUST query the same port or it would never see a runner that's up."""
    wda = _make_wda_dir(tmp_path)
    seen: dict = {}

    async def _capturing_probe(_udid, port=8100):
        seen["port"] = port
        return True

    with patch.object(wda_setup, "_wda_device_ready", _capturing_probe):
        res = await StartWdaOnDevice(_FakeCli()).execute(
            StartWdaOnDeviceParams(udid="PHY-UDID", wda_dir=wda, port=8200)
        )
    assert res.is_ok
    assert seen["port"] == 8200


@pytest.mark.asyncio
async def test_missing_facebook_wda_fails_fast_not_a_timeout(tmp_path: Path):
    """Without facebook-wda we can neither probe nor route input — surface
    that immediately instead of spawning xcodebuild and blaming a 90s
    signing timeout."""
    wda = _make_wda_dir(tmp_path)
    spawned = {"called": False}

    async def _should_not_spawn(*a, **k):
        spawned["called"] = True
        raise AssertionError("must not spawn xcodebuild when wda is missing")

    with (
        patch.object(wda_setup, "_wda_importable", lambda: False),
        patch.object(
            wda_setup.asyncio, "create_subprocess_exec", new=_should_not_spawn
        ),
    ):
        res = await StartWdaOnDevice(_FakeCli()).execute(
            StartWdaOnDeviceParams(udid="PHY-UDID", wda_dir=wda)
        )
    assert not res.is_ok
    assert res.failure.next_action == "install_dependencies"
    assert spawned["called"] is False


# ---- xcodebuild not installed -----------------------------------------


@pytest.mark.asyncio
async def test_xcodebuild_missing_returns_install_action(tmp_path: Path):
    wda = _make_wda_dir(tmp_path)

    async def _not_ready(_udid, _port=8100):
        return False

    async def _raise_fnf(*a, **k):
        raise FileNotFoundError("xcodebuild")

    with (
        patch.object(wda_setup, "_wda_device_ready", _not_ready),
        patch.object(
            wda_setup.asyncio, "create_subprocess_exec", new=_raise_fnf
        ),
    ):
        res = await StartWdaOnDevice(_FakeCli()).execute(
            StartWdaOnDeviceParams(udid="PHY-UDID", wda_dir=wda, ready_timeout_s=2.0)
        )
    assert not res.is_ok
    assert res.failure.next_action == "install_xcode_command_line_tools"


# ---- spawn-then-timeout ------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_then_timeout_kills_xcodebuild(tmp_path: Path):
    wda = _make_wda_dir(tmp_path)

    class _FakeProc:
        def __init__(self):
            self.pid = 4321
            self.returncode = None
            self.terminated = False

        def terminate(self):
            self.terminated = True
            self.returncode = -15

    proc = _FakeProc()

    async def _not_ready(_udid, _port=8100):
        return False

    async def _fake_spawn(*a, **k):
        return proc

    with (
        patch.object(wda_setup, "_wda_device_ready", _not_ready),
        patch.object(
            wda_setup.asyncio, "create_subprocess_exec", new=_fake_spawn
        ),
    ):
        res = await StartWdaOnDevice(_FakeCli()).execute(
            StartWdaOnDeviceParams(
                udid="PHY-UDID", wda_dir=wda, ready_timeout_s=1.0
            )
        )
    assert not res.is_ok
    assert res.failure.next_action == "check_xcode_signing"
    assert "elapsed_s" in res.failure.details
    assert proc.terminated is True


# ---- xcodebuild exits early: classify the returncode -------------------


@pytest.mark.asyncio
async def test_exit_code_65_routes_to_provide_team_id(tmp_path: Path):
    """65 is xcodebuild's signing/provisioning failure — the agent needs a
    team, not another build. Distinct next_action from a generic exit."""
    wda = _make_wda_dir(tmp_path)

    class _DeadProc:
        def __init__(self):
            self.pid = 4322
            self.returncode = 65

        def terminate(self):
            pass

    async def _not_ready(_udid, _port=8100):
        return False

    async def _fake_spawn(*a, **k):
        return _DeadProc()

    with (
        patch.object(wda_setup, "_wda_device_ready", _not_ready),
        patch.object(
            wda_setup.asyncio, "create_subprocess_exec", new=_fake_spawn
        ),
    ):
        res = await StartWdaOnDevice(_FakeCli()).execute(
            StartWdaOnDeviceParams(
                udid="PHY-UDID", wda_dir=wda, ready_timeout_s=3.0
            )
        )
    assert not res.is_ok
    assert res.failure.next_action == "provide_team_id"
    assert "returncode=65" in res.failure.message


@pytest.mark.asyncio
async def test_other_exit_code_routes_to_setup(tmp_path: Path):
    wda = _make_wda_dir(tmp_path)

    class _DeadProc:
        def __init__(self):
            self.pid = 4323
            self.returncode = 70

        def terminate(self):
            pass

    async def _not_ready(_udid, _port=8100):
        return False

    async def _fake_spawn(*a, **k):
        return _DeadProc()

    with (
        patch.object(wda_setup, "_wda_device_ready", _not_ready),
        patch.object(
            wda_setup.asyncio, "create_subprocess_exec", new=_fake_spawn
        ),
    ):
        res = await StartWdaOnDevice(_FakeCli()).execute(
            StartWdaOnDeviceParams(
                udid="PHY-UDID", wda_dir=wda, ready_timeout_s=3.0
            )
        )
    assert not res.is_ok
    assert res.failure.next_action == "setup_webdriveragent"


# ---- team_id falls back to the env var --------------------------------


@pytest.mark.asyncio
async def test_team_id_env_fallback_in_argv(tmp_path: Path, monkeypatch):
    """When no team_id param is passed, MCP_WDA_TEAM_ID is used for signing.
    We capture the argv the use case would spawn."""
    wda = _make_wda_dir(tmp_path)
    monkeypatch.setenv("MCP_WDA_TEAM_ID", "ENVTEAM999")

    captured: dict = {}

    class _DeadProc:
        def __init__(self):
            self.pid = 1
            self.returncode = 70  # bail immediately after capture

        def terminate(self):
            pass

    async def _not_ready(_udid, _port=8100):
        return False

    async def _fake_spawn(*argv, **k):
        captured["argv"] = list(argv)
        return _DeadProc()

    with (
        patch.object(wda_setup, "_wda_device_ready", _not_ready),
        patch.object(
            wda_setup.asyncio, "create_subprocess_exec", new=_fake_spawn
        ),
    ):
        await StartWdaOnDevice(_FakeCli()).execute(
            StartWdaOnDeviceParams(
                udid="PHY-UDID", wda_dir=wda, ready_timeout_s=3.0
            )
        )
    assert "DEVELOPMENT_TEAM=ENVTEAM999" in captured["argv"]
