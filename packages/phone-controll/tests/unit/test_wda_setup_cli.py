"""WdaSetupCli — the xcodebuild argv for device vs simulator.

REGRESSION (field report): WDA built for an iOS **simulator** used the
device destination `platform=iOS` and required code signing, so the build
failed ("Signing … requires a development team"). The simulator path must
target `platform=iOS Simulator` and disable signing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.infrastructure.process_runner import ProcessResult
from mcp_phone_controll.infrastructure.wda_setup_cli import WdaSetupCli


class _RecordingRunner:
    def __init__(self, stdout=""):
        self.argv = None
        self._stdout = stdout

    async def run(self, argv, cwd=None, timeout_s=None, env=None):
        self.argv = list(argv)
        return ProcessResult(returncode=0, stdout=self._stdout, stderr="")


@pytest.mark.asyncio
async def test_simulator_build_targets_sim_destination_no_signing(tmp_path: Path):
    runner = _RecordingRunner()
    cli = WdaSetupCli(runner)
    await cli.build_for_testing(
        wda_dir=tmp_path, udid="SIM-1", is_simulator=True, team_id="IGNORED123"
    )
    argv = runner.argv
    assert "build-for-testing" in argv
    dest = argv[argv.index("-destination") + 1]
    assert dest == "platform=iOS Simulator,id=SIM-1"
    assert "CODE_SIGNING_ALLOWED=NO" in argv
    assert "CODE_SIGNING_REQUIRED=NO" in argv
    # Simulators never sign — no team, even if one was passed.
    assert not any(a.startswith("DEVELOPMENT_TEAM=") for a in argv)


@pytest.mark.asyncio
async def test_device_build_targets_ios_destination_with_team(tmp_path: Path):
    runner = _RecordingRunner()
    cli = WdaSetupCli(runner)
    await cli.build_for_testing(
        wda_dir=tmp_path, udid="DEV-1", is_simulator=False, team_id="ABCDE12345"
    )
    argv = runner.argv
    dest = argv[argv.index("-destination") + 1]
    assert dest == "platform=iOS,id=DEV-1"
    assert "DEVELOPMENT_TEAM=ABCDE12345" in argv
    assert "CODE_SIGN_STYLE=Automatic" in argv
    assert "CODE_SIGNING_ALLOWED=NO" not in argv


@pytest.mark.asyncio
async def test_detect_is_simulator_from_simctl(tmp_path: Path):
    runner = _RecordingRunner(stdout="iPhone 17 (SIM-XYZ) (Booted)\n")
    cli = WdaSetupCli(runner)
    assert await cli.detect_is_simulator("SIM-XYZ") is True
    assert await cli.detect_is_simulator("00008030-NOTLISTED") is False
